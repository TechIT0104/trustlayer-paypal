"""Pre-dispute resolution agent.

A buyer with a problem talks to an agent acting for the seller *before* anyone files a
PayPal dispute. The LLM reads the order facts and the seller's policy and proposes an
outcome; deterministic code then enforces the policy (refund caps, when a full refund is
allowed) so the model can never promise money the seller did not authorize. Accepting an
offer executes it on PayPal immediately:
  - order still on hold  -> capture (price - refund) as final; PayPal releases the rest of the hold
  - order already captured -> partial refund via the Refunds API
"""
import json
import re
import time
import uuid

from . import db, ledger, llm, orders, paypal

DEFAULT_POLICY = {
    "max_partial_refund_pct": 20,       # agent may offer up to this share of the price on its own
    "late_goodwill_pct": 10,            # suggested goodwill for late delivery
    "damage_goodwill_pct": 20,          # suggested for minor damage / not-as-described
    "full_refund_not_received_days": 7, # full refund allowed only if this many days past the promise with no delivery
    "replacement_available": False,
    "tone": "warm, brief, no corporate jargon",
}

ISSUE_TYPES = ["late_delivery", "damaged", "not_as_described", "not_received", "changed_mind", "other"]
OFFER_TYPES = ["partial_refund", "full_refund", "replacement", "none", "escalate"]

SYSTEM = """You are the resolution assistant for a marketplace seller. A buyer has a problem with an order
paid through PayPal. Your goal: a fair, fast outcome that leaves the buyer satisfied so they do not need to
open a PayPal dispute, while respecting the seller's policy. Be honest; never invent facts not in ORDER FACTS.

Rules:
- Offer money only within the seller policy. Code will enforce limits, so stay inside them.
- Ask one clarifying question only if you truly cannot classify the problem.
- Late but delivered => apologise + modest goodwill partial refund. Damaged / not as described => partial
  refund scaled to severity, or escalate to the seller if severe. Not received => check the facts.
  Changed mind => no refund; explain politely.
- If the buyer rejects an offer, you may improve it once, still within policy.
- Money is only an OFFER until the buyer clicks "Accept". Never say a refund was issued, sent or processed;
  say "I can offer..." and tell them they can accept it below.

Return JSON only:
{"issue_type": one of [late_delivery, damaged, not_as_described, not_received, changed_mind, other],
 "severity": "low"|"medium"|"high",
 "buyer_sentiment": "calm"|"frustrated"|"angry",
 "dispute_risk": number 0..1 (chance the buyer opens a PayPal dispute if we do nothing),
 "reply": "message to the buyer, under 90 words",
 "offer": {"type": one of [partial_refund, full_refund, replacement, none, escalate],
           "amount": number in USD (0 if none), "reason": "short internal rationale"}}"""


def _policy(seller: dict) -> dict:
    return {**DEFAULT_POLICY, **(db.loads(seller.get("policy_json"), {}) or {})}


def _facts(o: dict, listing: dict) -> dict:
    late = None
    if o.get("promised_days") is not None and o.get("shipped_days_ago") is not None and o.get("delivered_days_ago") is not None:
        transit = o["shipped_days_ago"] - o["delivered_days_ago"]
        late = max(0, transit - o["promised_days"])
    return {
        "item": listing["title"], "condition_listed": listing.get("condition"),
        "description": listing.get("description"), "price_paid": o["amount"],
        "already_refunded": o.get("refunded_amount") or 0, "payment_status": o["status"],
        "shipped_days_ago": o.get("shipped_days_ago"), "delivery_promised_within_days": o.get("promised_days"),
        "delivered_days_ago": o.get("delivered_days_ago"), "days_late": late,
        "tracking": "delivered" if o.get("delivered_days_ago") is not None else "in transit",
    }


def _limits(price: float, policy: dict) -> dict:
    return {"max_refund_without_seller_usd": round(price * policy["max_partial_refund_pct"] / 100, 2),
            "suggested_late_goodwill_usd": round(price * policy["late_goodwill_pct"] / 100, 2),
            "suggested_damage_goodwill_usd": round(price * policy["damage_goodwill_pct"] / 100, 2)}


def enforce(offer: dict, issue_type: str, facts: dict, policy: dict) -> tuple[dict, list[str]]:
    """Clamp the model's offer to what the seller's policy actually allows."""
    notes: list[str] = []
    otype = offer.get("type") if offer.get("type") in OFFER_TYPES else "escalate"
    try:
        amount = round(float(offer.get("amount") or 0), 2)
    except (TypeError, ValueError):
        amount = 0.0
    price = float(facts["price_paid"])
    remaining = round(price - float(facts["already_refunded"] or 0), 2)
    cap = round(price * policy["max_partial_refund_pct"] / 100, 2)

    if otype == "full_refund":
        not_received_ok = (facts["tracking"] != "delivered" and (facts.get("days_late") or 0) >= policy["full_refund_not_received_days"])
        if not not_received_ok:
            otype, amount = "escalate", 0.0
            notes.append("Full refund is outside the agent's authority here; handed to the seller.")
        else:
            amount = remaining
    if otype == "replacement" and not policy["replacement_available"]:
        otype = "partial_refund"
        amount = round(price * policy["damage_goodwill_pct"] / 100, 2)
        notes.append("Seller has no replacements in stock; converted to a partial refund.")
    if otype == "partial_refund":
        if amount <= 0:
            amount = round(price * policy["late_goodwill_pct"] / 100, 2)
        if amount > cap:
            notes.append(f"Offer reduced from ${amount:.2f} to the policy cap of ${cap:.2f} ({policy['max_partial_refund_pct']}%).")
            amount = cap
        amount = min(amount, remaining)
        if amount < 1:
            otype, amount = "none", 0.0
    if issue_type == "changed_mind" and otype in ("partial_refund", "full_refund"):
        otype, amount = "none", 0.0
        notes.append("Policy: no refunds for change of mind.")
    if otype in ("none", "escalate"):
        amount = 0.0
    return {"type": otype, "amount": round(amount, 2), "reason": offer.get("reason", "")}, notes


def _turn(issue: dict, o: dict) -> dict:
    listing = db.one("SELECT * FROM listings WHERE id = ?", (o["listing_id"],))
    seller = db.one("SELECT * FROM sellers WHERE id = ?", (o["seller_id"],))
    policy = _policy(seller)
    facts = _facts(o, listing)
    transcript = db.loads(issue["transcript_json"], [])
    convo = "\n".join(f"{t['role'].upper()}: {t['text']}" for t in transcript[-12:])
    user = (f"SELLER: {seller['name']}\nSELLER POLICY: {json.dumps(policy)}\n"
            f"YOUR LIMITS: {json.dumps(_limits(float(o['amount']), policy))}\nORDER FACTS: {json.dumps(facts)}\n"
            f"CONVERSATION SO FAR:\n{convo}\n\nWrite the next assistant turn.")
    res = llm.complete_json(SYSTEM, user, temperature=0.3, use_cache=False)
    d = res["data"] if isinstance(res["data"], dict) else {}
    itype = d.get("issue_type") if d.get("issue_type") in ISSUE_TYPES else "other"
    offer, notes = enforce(d.get("offer") or {}, itype, facts, policy)
    try:
        dispute_risk = max(0.0, min(1.0, float(d.get("dispute_risk", 0.5))))
    except (TypeError, ValueError):
        dispute_risk = 0.5
    reply = (d.get("reply") or "").strip() or "Sorry about this. Let me get the seller to look at it."
    if notes and offer["type"] == "partial_refund":
        # the model's wording may quote its original number; make the text match what code will pay
        fixed = re.sub(r"\$\s?\d[\d,]*(?:\.\d{1,2})?", f"${offer['amount']:.2f}", reply)
        reply = fixed if fixed != reply else reply + f" I can offer a ${offer['amount']:.2f} refund right now."
    elif notes and offer["type"] == "escalate":
        reply += " I've passed this to the seller to decide; you'll hear back within 24 hours."
    turn = {"role": "agent", "text": reply, "offer": offer, "policy_notes": notes, "issue_type": itype,
            "severity": d.get("severity"), "sentiment": d.get("buyer_sentiment"), "dispute_risk": dispute_risk,
            "provider": res["provider"], "model": res["model"], "latency_ms": res["latency_ms"], "ts": time.time()}
    transcript.append(turn)
    status = ("OFFERED" if offer["type"] in ("partial_refund", "full_refund")
              else "ESCALATED" if offer["type"] in ("escalate", "replacement") else "OPEN")
    db.update("issues", "id", issue["id"], transcript_json=json.dumps(transcript), offer_json=json.dumps(offer),
              status=status)
    ledger.append("resolution.turn", {"issue_id": issue["id"], "issue_type": itype, "offer": offer,
                                      "policy_adjustments": notes, "dispute_risk": dispute_risk,
                                      "provider": res["provider"]}, order_id=o["id"], seller_id=o["seller_id"])
    if status == "ESCALATED" and issue["status"] != "ESCALATED":
        ledger.append("resolution.escalated", {"issue_id": issue["id"], "reason": offer.get("reason", "")},
                      order_id=o["id"], seller_id=o["seller_id"])
    return turn


def message(order_id: str, text: str) -> dict:
    o = orders.get(order_id)
    if o["status"] not in ("HELD", "CAPTURED", "PAID_OUT"):
        raise orders.OrderError(f"no problem can be reported for an order that is {o['status']}")
    issue = db.one("SELECT * FROM issues WHERE order_id = ? AND status IN ('OPEN','OFFERED','ESCALATED') "
                   "ORDER BY created_at DESC LIMIT 1", (order_id,))
    now = time.time()
    if not issue:
        iid = "IS-" + uuid.uuid4().hex[:6].upper()
        db.run("INSERT INTO issues (id, order_id, status, transcript_json, created_at, updated_at) VALUES (?,?,?,?,?,?)",
               (iid, order_id, "OPEN", "[]", now, now))
        ledger.append("resolution.opened", {"issue_id": iid}, order_id=order_id, seller_id=o["seller_id"])
        issue = db.one("SELECT * FROM issues WHERE id = ?", (iid,))
    transcript = db.loads(issue["transcript_json"], [])
    transcript.append({"role": "buyer", "text": text.strip()[:1000], "ts": now})
    db.update("issues", "id", issue["id"], transcript_json=json.dumps(transcript))
    issue = db.one("SELECT * FROM issues WHERE id = ?", (issue["id"],))
    try:
        _turn(issue, o)
    except llm.LLMUnavailable:
        transcript.append({"role": "agent", "text": "Our assistant is busy right now. Your message has been sent to the seller.",
                           "offer": {"type": "escalate", "amount": 0}, "ts": time.time()})
        db.update("issues", "id", issue["id"], transcript_json=json.dumps(transcript))
    return get_issue(issue["id"])


def seller_issues(seller_id: str) -> list[dict]:
    rows = db.all("SELECT i.id FROM issues i JOIN orders o ON o.id = i.order_id WHERE o.seller_id = ? "
                  "ORDER BY i.updated_at DESC", (seller_id,))
    return [get_issue(r["id"]) for r in rows]


def get_issue(issue_id: str) -> dict:
    issue = db.one("SELECT * FROM issues WHERE id = ?", (issue_id,))
    if not issue:
        raise orders.OrderError("issue not found", 404)
    issue["transcript"] = db.loads(issue.pop("transcript_json"), [])
    issue["offer"] = db.loads(issue.pop("offer_json"), None)
    issue["outcome"] = db.loads(issue.pop("outcome_json"), None)
    issue["order"] = orders.view(orders.get(issue["order_id"]))
    return issue


def accept(issue_id: str) -> dict:
    issue = db.one("SELECT * FROM issues WHERE id = ?", (issue_id,))
    if not issue:
        raise orders.OrderError("issue not found", 404)
    if issue["status"] == "RESOLVED":
        return get_issue(issue_id)
    offer = db.loads(issue["offer_json"], {}) or {}
    if issue["status"] != "OFFERED" or offer.get("type") not in ("partial_refund", "full_refund") or offer.get("amount", 0) <= 0:
        raise orders.OrderError("there is no money offer to accept")
    return _settle(issue, round(float(offer["amount"]), 2), by="buyer_accepted_offer")


def seller_decision(issue_id: str, action: str, amount: float = 0.0) -> dict:
    """The seller resolves an escalated case: send a refund of their choosing, or decline."""
    issue = db.one("SELECT * FROM issues WHERE id = ?", (issue_id,))
    if not issue:
        raise orders.OrderError("issue not found", 404)
    if issue["status"] != "ESCALATED":
        raise orders.OrderError(f"case is {issue['status'].lower()}, not waiting for the seller")
    o = orders.get(issue["order_id"])
    transcript = db.loads(issue["transcript_json"], [])
    if action == "decline":
        transcript.append({"role": "seller", "text": "The seller reviewed your case and declined a refund. "
                           "You can still contact PayPal if you disagree.", "ts": time.time()})
        db.update("issues", "id", issue_id, status="DECLINED", transcript_json=json.dumps(transcript))
        ledger.append("resolution.declined", {"issue_id": issue_id}, order_id=o["id"], seller_id=o["seller_id"])
        return get_issue(issue_id)
    if action != "refund":
        raise orders.OrderError("action must be refund or decline")
    remaining = round(o["amount"] - (o["refunded_amount"] or 0), 2)
    amount = round(float(amount), 2)
    if not 0 < amount <= remaining:
        raise orders.OrderError(f"refund must be between $0.01 and ${remaining:.2f}")
    transcript.append({"role": "seller", "text": f"I've reviewed this and sent you ${amount:.2f}. Sorry for the trouble.",
                       "ts": time.time()})
    db.update("issues", "id", issue_id, transcript_json=json.dumps(transcript))
    return _settle(db.one("SELECT * FROM issues WHERE id = ?", (issue_id,)), amount, by="seller_decision")


def _settle(issue: dict, amount: float, by: str) -> dict:
    issue_id = issue["id"]
    o = orders.get(issue["order_id"])
    if o["status"] == "HELD":
        keep = round(o["amount"] - amount, 2)
        if keep <= 0:
            orders.cancel(o["id"], reason="resolved_full_refund")
            method = "void (nothing captured)"
        else:
            o = orders.capture_remaining(o, keep, f"Resolved: ${amount:.2f} of your hold was released back to you.")
            db.update("orders", "id", o["id"], refunded_amount=0)
            method = f"captured ${keep:.2f}, released ${amount:.2f} of the hold"
        ref_id = None
    elif o["status"] in ("CAPTURED", "PAID_OUT"):
        res = paypal.refund_capture(o["capture_id"], amount, o["id"], note="Resolved with the seller via TrustLayer")
        ref_id = res.get("id")
        db.update("orders", "id", o["id"], refunded_amount=round((o["refunded_amount"] or 0) + amount, 2))
        ledger.append("payment.refunded", {"refund_id": ref_id, "amount": amount, "status": res.get("status"),
                                           "capture_id": o["capture_id"]}, order_id=o["id"], seller_id=o["seller_id"])
        method = f"PayPal refund {ref_id}"
    else:
        raise orders.OrderError(f"cannot settle an order that is {o['status']}")
    outcome = {"amount": amount, "method": method, "refund_id": ref_id, "dispute_avoided": True,
               "settled_by": by, "ts": time.time()}
    db.update("issues", "id", issue_id, status="RESOLVED", outcome_json=json.dumps(outcome))
    day = 0
    db.run("INSERT INTO seller_daily (seller_id, day, orders, disputes, refunds, gross, prevented) VALUES (?,?,0,0,1,0,1)"
           " ON CONFLICT(seller_id, day) DO UPDATE SET prevented = prevented + 1, refunds = refunds + 1",
           (o["seller_id"], day))
    ledger.append("resolution.settled", outcome | {"issue_id": issue_id}, order_id=o["id"], seller_id=o["seller_id"])
    return get_issue(issue_id)
