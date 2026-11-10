"""TrustLayer Plus: a membership sold with PayPal Subscriptions, built to the opposite of a subscription trap.

Research (BestMoney 2026, Self Financial 2026): about 7 in 10 US adults have been charged after forgetting a free
trial, and 20+ US states now require click-to-cancel. So:

- Free trial on PayPal (TRIAL billing cycle) and the server verifies every subscription with PayPal before granting it.
- Before the first charge, an AI-written reminder says exactly when and how much, and honestly whether the member
  has actually used it. Facts (date, amount, usage) come from our data; the LLM only writes the recommendation.
- Cancelling is one click, always visible. The assistant may offer one alternative (pause) only when the member has
  used the benefits, and it can never block or delay the cancellation.
- Lifecycle state is kept in sync with PayPal by webhooks (BILLING.SUBSCRIPTION.*, PAYMENT.SALE.COMPLETED).
"""
import json
import time

from . import config, db, ledger, llm, orders, paypal

PLAN_NAME = "TrustLayer Plus"
PRICE = 4.99
TRIAL_DAYS = 7
REMIND_BEFORE_DAYS = 2
BENEFITS = ["24-hour cooling-off on any payment you choose", "Trusted-contact alerts on every paused payment",
            "Priority resolution with the seller's assistant"]


def _kv(key: str) -> str | None:
    row = db.one("SELECT v FROM kv WHERE k = ?", (key,))
    return row["v"] if row else None


def _set_kv(key: str, value: str) -> None:
    db.run("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (key, value))


def ensure_plan() -> dict:
    """Create (once) the PayPal catalog product and ACTIVE billing plan; ids are cached in the kv table."""
    plan_id = config.PLUS_PLAN_ID or _kv("plus_plan_id")  # env pin survives hosts with ephemeral disks
    if plan_id:
        return {"plan_id": plan_id, "product_id": _kv("plus_product_id")}
    ref = config.PAYPAL_CLIENT_ID[-8:] or "local"
    product = paypal.create_product(PLAN_NAME, "Extra protection for marketplace payments", ref)
    plan = paypal.create_plan(product["id"], PLAN_NAME, PRICE, TRIAL_DAYS, ref)
    _set_kv("plus_product_id", product["id"])
    _set_kv("plus_plan_id", plan["id"])
    ledger.append("subscription.plan_created", {"product_id": product["id"], "plan_id": plan["id"],
                                                "price": PRICE, "trial_days": TRIAL_DAYS})
    return {"plan_id": plan["id"], "product_id": product["id"]}


def _now(sub: dict) -> float:
    return time.time() + (sub.get("clock_offset") or 0)


def _usage() -> dict:
    """What the member actually got out of it (single demo buyer: all marketplace orders)."""
    rows = db.all("SELECT * FROM orders")
    paused = [o for o in rows if (db.loads(o["risk_json"], {}) or {}).get("verdict") == "PAUSE"]
    voided = sum(o["amount"] for o in rows if o["status"] == "CANCELLED")
    released = sum(max(0, o["amount"] - (o["captured_amount"] or 0)) for o in rows if o["captured_amount"])
    resolved = db.one("SELECT COUNT(*) AS n FROM issues WHERE status = 'RESOLVED'")["n"]
    return {"payments_protected": len(rows), "payments_paused": len(paused), "problems_resolved": resolved,
            "money_kept_safe": round(voided + released, 2)}


def view(sub: dict | None) -> dict:
    base = {"plan": {"name": PLAN_NAME, "price": PRICE, "trial_days": TRIAL_DAYS, "benefits": BENEFITS},
            "subscription": None}
    try:
        base["plan"]["plan_id"] = ensure_plan()["plan_id"]
    except paypal.PayPalError as e:
        base["plan"]["error"] = str(e)
    if not sub:
        return base
    now = _now(sub)
    in_trial = sub["status"] in ("ACTIVE", "APPROVED") and now < (sub["trial_ends_at"] or 0)
    base["subscription"] = {
        "id": sub["id"], "status": sub["status"], "in_trial": in_trial,
        "trial_ends_at": sub["trial_ends_at"], "next_billing_at": sub["next_billing_at"], "price": sub["price"],
        "days_until_charge": max(0, round(((sub["next_billing_at"] or now) - now) / 86400, 1)),
        "reminder_due": in_trial and now >= (sub["trial_ends_at"] or 0) - REMIND_BEFORE_DAYS * 86400,
        "simulated_days": round((sub.get("clock_offset") or 0) / 86400, 1),
        "reminder": db.loads(sub["reminder_json"], None), "cancel_reason": sub["cancel_reason"],
        "cancelled_at": sub["cancelled_at"], "usage": _usage(),
    }
    return base


def current() -> dict | None:
    return db.one("SELECT * FROM subscriptions ORDER BY created_at DESC LIMIT 1")


def get(sub_id: str) -> dict:
    sub = db.one("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
    if not sub:
        raise orders.OrderError("subscription not found", 404)
    return sub


def _sync(sub_id: str, remote: dict) -> None:
    status = remote.get("status")
    bi = remote.get("billing_info") or {}
    nxt = bi.get("next_billing_time")
    fields = {"status": status, "paypal_json": json.dumps({k: remote.get(k) for k in ("status", "start_time", "plan_id")})}
    if nxt:
        fields["next_billing_at"] = time.mktime(time.strptime(nxt[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
    db.update("subscriptions", "id", sub_id, **fields)


def register(subscription_id: str) -> dict:
    """Called after the buyer approves in PayPal. Never trust the browser: verify with PayPal first."""
    plan_id = ensure_plan()["plan_id"]
    remote = paypal.get_subscription(subscription_id)
    if remote.get("plan_id") != plan_id:
        raise orders.OrderError("subscription is for a different plan", 400)
    if remote.get("status") not in ("ACTIVE", "APPROVED"):
        raise orders.OrderError(f"PayPal reports this subscription as {remote.get('status')}", 409)
    now = time.time()
    if not db.one("SELECT 1 AS x FROM subscriptions WHERE id = ?", (subscription_id,)):
        db.run("INSERT INTO subscriptions (id, plan_id, status, started_at, trial_ends_at, next_billing_at, price, "
               "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (subscription_id, plan_id, remote["status"], now, now + TRIAL_DAYS * 86400,
                now + TRIAL_DAYS * 86400, PRICE, now, now))
    _sync(subscription_id, remote)
    ledger.append("subscription.started", {"subscription_id": subscription_id, "status": remote["status"],
                                           "trial_days": TRIAL_DAYS, "price": PRICE, "verified_with_paypal": True})
    return view(get(subscription_id))


def simulate_days(sub_id: str, days: float) -> dict:
    """Demo only: move this subscription's clock forward to show the pre-charge reminder."""
    if not config.DEMO_MODE:
        raise orders.OrderError("disabled outside demo mode", 403)
    sub = get(sub_id)
    db.update("subscriptions", "id", sub_id, clock_offset=(sub["clock_offset"] or 0) + days * 86400, reminder_json=None)
    return view(get(sub_id))


REMINDER_SYSTEM = """You write the reminder a subscription service sends before a free trial turns into a paid charge.
Be radically honest: the goal is that nobody is charged for something they forgot or don't use.
Use ONLY the facts given. If the member barely used the benefits, say so and suggest cancelling.
Return JSON only: {"headline": "max 12 words", "body": "2-3 short sentences", "recommendation": "keep"|"cancel"|"either",
"why": "one sentence grounded in the usage numbers"}"""


def reminder(sub_id: str) -> dict:
    sub = get(sub_id)
    v = view(sub)["subscription"]
    facts = {"product": PLAN_NAME, "charge_amount_usd": sub["price"], "days_until_charge": v["days_until_charge"],
             "benefits": BENEFITS, "usage_during_trial": v["usage"]}
    try:
        res = llm.complete_json(REMINDER_SYSTEM, json.dumps(facts), temperature=0.2)
        d = res["data"] if isinstance(res["data"], dict) else {}
        rec = {"headline": d.get("headline", ""), "body": d.get("body", ""), "why": d.get("why", ""),
               "recommendation": d.get("recommendation") if d.get("recommendation") in ("keep", "cancel", "either") else "either",
               "model": res["model"]}
    except llm.LLMUnavailable:
        rec = {"headline": f"Your trial ends in {v['days_until_charge']:g} days",
               "body": "Cancel any time before then and you won't be charged.", "why": "", "recommendation": "either",
               "model": None}
    # The facts that matter are stated by code, not by the model.
    rec["fact"] = (f"You will be charged ${sub['price']:.2f} on "
                   f"{time.strftime('%b %d, %Y', time.localtime(sub['next_billing_at'] or time.time()))} unless you cancel.")
    db.update("subscriptions", "id", sub_id, reminder_json=json.dumps(rec))
    ledger.append("subscription.reminder", {"subscription_id": sub_id, "recommendation": rec["recommendation"],
                                            "days_until_charge": v["days_until_charge"], "model": rec["model"]})
    return view(get(sub_id))


CANCEL_SYSTEM = """A member is cancelling a subscription. Write one short, warm sentence confirming it is easy and
immediate. Only if usage shows they got real value, you may mention ONE alternative: pausing instead. Never argue,
never guilt-trip, never hide the cancel option.
Return JSON only: {"message": "max 30 words", "offer_pause": true|false}"""


def cancel_assist(sub_id: str) -> dict:
    v = view(get(sub_id))["subscription"]
    used = v["usage"]["payments_protected"] > 0 or v["usage"]["problems_resolved"] > 0
    try:
        res = llm.complete_json(CANCEL_SYSTEM, json.dumps({"usage": v["usage"]}), temperature=0.2)
        d = res["data"] if isinstance(res["data"], dict) else {}
        msg, offer = d.get("message") or "Cancelling takes one click.", bool(d.get("offer_pause"))
    except llm.LLMUnavailable:
        msg, offer = "Cancelling takes one click and is effective immediately.", False
    return {"message": msg, "offer_pause": offer and used and v["status"] == "ACTIVE"}  # code has the final say


def cancel(sub_id: str, reason: str) -> dict:
    sub = get(sub_id)
    if sub["status"] in ("CANCELLED", "EXPIRED"):
        return view(sub)
    paypal.cancel_subscription(sub_id, reason or "Cancelled by subscriber in one click")
    db.update("subscriptions", "id", sub_id, status="CANCELLED", cancel_reason=reason or None, cancelled_at=time.time())
    ledger.append("subscription.cancelled", {"subscription_id": sub_id, "reason": reason, "clicks_to_cancel": 1,
                                             "charged": False if view(sub)["subscription"]["in_trial"] else None})
    return view(get(sub_id))


def pause(sub_id: str) -> dict:
    paypal.suspend_subscription(sub_id, "Paused by subscriber")
    db.update("subscriptions", "id", sub_id, status="SUSPENDED")
    ledger.append("subscription.paused", {"subscription_id": sub_id})
    return view(get(sub_id))


def resume(sub_id: str) -> dict:
    paypal.activate_subscription(sub_id)
    db.update("subscriptions", "id", sub_id, status="ACTIVE")
    ledger.append("subscription.resumed", {"subscription_id": sub_id})
    return view(get(sub_id))


def on_webhook(event_type: str, resource: dict) -> str | None:
    """Apply BILLING.SUBSCRIPTION.* / PAYMENT.SALE.COMPLETED to our record. Returns the subscription id if matched."""
    sub_id = resource.get("id") if event_type.startswith("BILLING.SUBSCRIPTION.") else resource.get("billing_agreement_id")
    if not sub_id or not db.one("SELECT 1 AS x FROM subscriptions WHERE id = ?", (sub_id,)):
        return None
    if event_type.startswith("BILLING.SUBSCRIPTION."):
        status = {"ACTIVATED": "ACTIVE", "CANCELLED": "CANCELLED", "SUSPENDED": "SUSPENDED",
                  "EXPIRED": "EXPIRED"}.get(event_type.rsplit(".", 1)[-1])
        if status:
            db.update("subscriptions", "id", sub_id, status=status)
    ledger.append("subscription.webhook", {"subscription_id": sub_id, "event_type": event_type})
    return sub_id
