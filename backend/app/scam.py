"""Pay-pause risk engine: decide CLEAR / CAUTION / PAUSE before a buyer's money moves.

Three layers, fused at the decision (not by averaging blindly):
1. Rules: explainable regex + structured signals (Friends & Family requests, off-platform
   payment, fees/deposits, payee changes, price anomaly, brand-new seller...). Fast, no AI.
2. LLM: reads the listing + chat, names the scam *tactic*, and must cite evidence as exact
   quotes from numbered chat lines.
3. Grounding check: every quote the LLM cites is verified against the real chat line.
   Ungrounded "evidence" is discarded and an LLM-only high score is capped. Research on
   LLM scam detectors (e.g. arXiv 2502.03964, 2606.01475) reports false positives and
   type confusion as the main failure modes; this is our guard against both.

PAUSE requires corroboration: a strong rule signal, or LLM risk backed by grounded quotes.
"""
import re
import time

from . import llm

SCAM_TYPES = [
    "protection_bypass",      # Friends & Family / "no G&S" / gift payment to a stranger
    "off_platform_payment",   # Zelle, gift cards, crypto, wire
    "advance_fee",            # deposits, holding fees, courier/insurance/customs fees
    "overpayment",            # pay extra / refund the difference
    "payee_switch",           # pay my cousin's account / this other email
    "impersonation",          # fake PayPal support, "account limited, pay to unlock"
    "phishing_link",          # seller's own "payment link" to a look-alike site
    "too_good_to_be_true",    # price far below market + pressure
    "none",
]

# (key, regex, weight, strong, human label). Applied to SELLER lines only.
RULES = [
    ("friends_family", r"friends?\s*(?:and|&|n|\+)\s*family|\bf\s*[&n-]\s*f\b|\bfnf\b|send (?:it )?as (?:a )?(?:gift|friend)|personal payment|family (?:option|payment)|(?:pay|send)(?: it| me)? (?:via|as|through) personal\b",
     0.55, True, "Asks you to pay as Friends & Family (no buyer protection)"),
    ("avoid_protection", r"(?:no|not|don'?t|avoid|without|skip)\b.{0,30}(?:goods\s*(?:and|&)\s*services|\bg\s*&\s*s\b|\bgns\b|buyer protection|invoice)",
     0.45, True, "Tells you to avoid Goods & Services / buyer protection"),
    ("off_platform", r"\b(?:zelle|cash ?app|wire (?:transfer|me|the (?:funds|money|payment))|bank transfer|direct deposit|personal check|cashier'?s check|money order|western union|moneygram|bitcoin|btc|crypto|usdt|gift ?cards?|itunes card|steam card|apple card code)\b",
     0.5, True, "Pushes a payment method with no protection (gift card / crypto / wire / Zelle)"),
    ("advance_fee", r"\b(?:deposit|holding fee|reservation fee|shipping (?:agent|company) fee|courier fee|insurance fee|customs (?:fee|charge)|release fee|clearance fee|verification fee)\b",
     0.45, True, "Asks for an up-front fee or deposit before the item"),
    ("overpayment", r"overpa(?:y|id|yment)|pay (?:you )?extra|send (?:me )?(?:back )?the (?:difference|extra|rest)|refund (?:me )?the (?:difference|extra)",
     0.5, True, "Overpayment / 'send back the difference' pattern"),
    ("payee_switch", r"(?:different|another|other|second|my (?:wife|husband|brother|sister|friend|cousin|partner|uncle|dad|mom)(?:'s)?)\s+(?:paypal|account|email|e-mail)|pay (?:it )?(?:to )?this (?:email|account|address)",
     0.45, True, "Wants payment sent to a different account than the seller's"),
    ("impersonation", r"paypal (?:support|team|agent|security|department)|account (?:is |was |has been )?(?:limited|suspended|locked|on hold)|verify your (?:account|paypal)|unlock (?:the|your) (?:funds|payment)",
     0.5, True, "Claims to be PayPal / says an account is 'limited' and needs payment"),
    ("lookalike_link", r"(?:https?://|www\.)\S*(?:paypa[1il]|pay-?pal-|pp-|secure-?pay|verify|checkout-|invoice-)\S*|\b[\w-]*paypa1[\w.-]*",
     0.5, True, "Sends a payment link to a look-alike website instead of the checkout"),
    ("external_link", r"https?://\S+|\bwww\.\S+",
     0.15, False, "Shares an outside link"),
    ("contact_switch", r"whats\s?app|telegram|signal app|text me|email me (?:at|on)|my (?:number|cell)|call me (?:at|on)|\+?\d[\d\s\-]{8,}\d|[\w.+-]+@[\w-]+\.[\w.]+",
     0.2, False, "Moves the conversation off the platform"),
    ("urgency", r"right now|asap|hurry|today only|first come|others? (?:are |is )?(?:waiting|interested|asking)|someone else (?:wants|is)|last chance|before (?:someone|anyone) else|within (?:\d+|an?|the next) (?:min|minute|hour)|(?:won'?t|will not) hold|no holds",
     0.2, False, "Pressure to pay quickly"),
]
_COMPILED = [(k, re.compile(p, re.I), w, s, label) for k, p, w, s, label in RULES]

SYSTEM = f"""You are a payment-safety analyst for a peer-to-peer marketplace whose payments run on PayPal.
Decide whether the BUYER is being manipulated into an unsafe or unrecoverable payment.

Be calibrated. Most marketplace chats are honest. Haggling, asking about shipping, a seller saying
another buyer is interested, or a good price are NOT scams by themselves. Raise risk only for concrete
manipulation tactics. Use one scam_type from: {", ".join(SCAM_TYPES)}.

Evidence rules: cite ONLY exact quotes copied character-for-character from the numbered chat lines,
with the line number. Never paraphrase inside "quote". If nothing is suspicious, return an empty list.

Return JSON only:
{{"risk": number 0..1,
  "scam_type": string,
  "evidence": [{{"line": int, "quote": string, "why": string}}],
  "explanation": "one plain sentence for the buyer",
  "spell_breaker": "2-3 calm sentences addressed to the buyer naming the specific tactic and what a real seller would do instead",
  "safe_next_step": "one short actionable instruction"}}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower().strip("\"'“”‘’")


def rule_signals(listing: dict, seller: dict, messages: list[dict]) -> list[dict]:
    hits: list[dict] = []
    seen = set()
    for i, m in enumerate(messages, start=1):
        if m["sender"] != "seller":
            continue
        for key, rx, w, strong, label in _COMPILED:
            mm = rx.search(m["text"])
            if mm and key not in seen:
                seen.add(key)
                hits.append({"key": key, "weight": w, "strong": strong, "label": label,
                             "line": i, "match": mm.group(0)})
    price, ref = float(listing.get("price") or 0), float(listing.get("ref_price") or 0)
    if ref > 0 and price < 0.6 * ref:
        pct = round(100 * (1 - price / ref))
        hits.append({"key": "price_anomaly", "weight": 0.3, "strong": False,
                     "label": f"Price is {pct}% below what this item usually sells for (${ref:,.0f})"})
    if (seller.get("joined_days_ago") or 0) < 14 and (seller.get("completed_sales") or 0) == 0:
        hits.append({"key": "new_seller", "weight": 0.2, "strong": False,
                     "label": f"Seller account is {seller.get('joined_days_ago')} days old with no completed sales"})
    return hits


def _combine(weights: list[float]) -> float:
    p = 1.0
    for w in weights:
        p *= (1 - w)
    return 1 - p


def _chat_block(messages: list[dict]) -> str:
    return "\n".join(f"[{i}] {m['sender'].upper()}: {m['text']}" for i, m in enumerate(messages, start=1))


def llm_assess(listing: dict, seller: dict, messages: list[dict]) -> dict:
    user = (
        f"LISTING: {listing['title']} | category {listing.get('category')} | asking ${listing['price']:.2f} "
        f"(typical resale ${listing.get('ref_price') or 0:.0f}) | condition {listing.get('condition')}\n"
        f"DESCRIPTION: {listing.get('description', '')}\n"
        f"SELLER: '{seller.get('handle')}' joined {seller.get('joined_days_ago')} days ago, "
        f"{seller.get('completed_sales')} completed sales, rating {seller.get('rating')}\n"
        f"CHAT (numbered):\n{_chat_block(messages)}\n\n"
        "The buyer is about to pay through PayPal on this marketplace. Assess the risk."
    )
    res = llm.complete_json(SYSTEM, user, temperature=0.0)
    d = res["data"] if isinstance(res["data"], dict) else {}
    lines = {i: m["text"] for i, m in enumerate(messages, start=1)}
    grounded, dropped = [], []
    for ev in d.get("evidence") or []:
        try:
            line = int(ev.get("line"))
        except (TypeError, ValueError):
            line = -1
        q = _norm(ev.get("quote", ""))
        src = _norm(lines.get(line, ""))
        if q and len(q) >= 4 and q in src:
            grounded.append({"line": line, "quote": ev.get("quote", "").strip(), "why": ev.get("why", "")})
        else:
            # allow a correct quote with a wrong line number, but record that we fixed it
            match = next((n for n, t in lines.items() if q and len(q) >= 4 and q in _norm(t)), None)
            if match:
                grounded.append({"line": match, "quote": ev.get("quote", "").strip(), "why": ev.get("why", ""),
                                 "line_corrected": True})
            else:
                dropped.append(ev)
    try:
        risk = max(0.0, min(1.0, float(d.get("risk", 0))))
    except (TypeError, ValueError):
        risk = 0.0
    stype = d.get("scam_type") if d.get("scam_type") in SCAM_TYPES else "none"
    return {
        "risk": risk, "scam_type": stype, "evidence": grounded, "dropped_evidence": len(dropped),
        "explanation": d.get("explanation", ""), "spell_breaker": d.get("spell_breaker", ""),
        "safe_next_step": d.get("safe_next_step", ""),
        "provider": res["provider"], "model": res["model"], "latency_ms": res["latency_ms"],
        "cached": res["cached"],
    }


PAUSE_AT = 0.65
CAUTION_AT = 0.35


def assess(listing: dict, seller: dict, messages: list[dict], mode: str = "fused") -> dict:
    """mode: 'fused' (product), 'rules' or 'llm' (used by the evaluation harness)."""
    t0 = time.time()
    rules = rule_signals(listing, seller, messages)
    rule_score = _combine([h["weight"] for h in rules])
    strong = any(h["strong"] for h in rules)

    ai, ai_error = None, None
    if mode in ("fused", "llm"):
        try:
            ai = llm_assess(listing, seller, messages)
        except llm.LLMUnavailable as e:
            ai_error = str(e)

    if mode == "rules" or ai is None:
        score = rule_score
        corroborated = strong
    else:
        llm_risk = ai["risk"]
        if not ai["evidence"] and llm_risk > 0.6:
            llm_risk = 0.6  # no grounded quote => the model may not go above "caution" on its own
        grounded = len(ai["evidence"]) >= 1
        if mode == "llm":
            score, corroborated = llm_risk, grounded
        else:
            # Either independent layer can carry the decision when it is backed by evidence:
            # a strong rule hit, or an LLM judgement with at least one verified quote from the chat.
            # Ungrounded LLM opinions only blend in (and were already capped at 0.6 above).
            if strong or grounded:
                score = max(llm_risk, rule_score)
            else:
                score = 0.65 * llm_risk + 0.35 * rule_score
            if strong and llm_risk >= 0.5:  # agreement bonus: both layers point the same way
                score = min(1.0, score + 0.1)
            corroborated = strong or grounded

    if score >= PAUSE_AT and corroborated:
        verdict = "PAUSE"
    elif score >= CAUTION_AT:
        verdict = "CAUTION"
    else:
        verdict = "CLEAR"

    reasons = [h["label"] for h in sorted(rules, key=lambda h: -h["weight"])]
    return {
        "verdict": verdict, "score": round(score, 3), "rule_score": round(rule_score, 3),
        "signals": rules, "reasons": reasons, "ai": ai, "ai_error": ai_error, "mode": mode,
        "thresholds": {"pause": PAUSE_AT, "caution": CAUTION_AT},
        "elapsed_ms": int((time.time() - t0) * 1000),
    }
