"""Seller account-health monitor.

Sellers on PayPal and Stripe most often complain that holds and limitations arrive with no
warning and no explanation. We cannot see PayPal's internal risk models, so this does not
pretend to predict them. It watches the publicly documented signals that commonly trigger
reviews (dispute ratio vs card-network monitoring thresholds such as Visa's 1.5% VAMP line,
refund rate, sudden volume spikes, new accounts selling fast) on the seller's own data, and
explains them in plain language with concrete next steps.
"""
import json

from . import db, llm

DISPUTE_LINE = 1.5     # % - card-network excessive-dispute threshold (Visa VAMP, most regions, Apr 2026)
DISPUTE_EARLY = 1.0    # % - our early-warning line
REFUND_WATCH = 6.0     # %
SPIKE_WATCH = 2.0      # x the seller's own baseline


def _series(seller_id: str) -> list[dict]:
    rows = db.all("SELECT * FROM seller_daily WHERE seller_id = ? AND day > -30 ORDER BY day", (seller_id,))
    by_day = {r["day"]: r for r in rows}
    return [by_day.get(d, {"day": d, "orders": 0, "disputes": 0, "refunds": 0, "gross": 0, "prevented": 0})
            for d in range(-29, 1)]


def metrics(seller_id: str) -> dict:
    seller = db.one("SELECT * FROM sellers WHERE id = ?", (seller_id,))
    if not seller:
        return {}
    series = _series(seller_id)
    live = db.all("SELECT * FROM orders WHERE seller_id = ?", (seller_id,))
    live_done = [o for o in live if o["status"] in ("CAPTURED", "PAID_OUT", "CLOSED", "HELD", "PAUSED")]
    tx = sum(r["orders"] for r in series) + len(live_done)
    disputes = sum(r["disputes"] for r in series)
    refunds = sum(r["refunds"] for r in series)
    prevented = sum(r["prevented"] for r in series)
    gross = sum(r["gross"] for r in series) + sum(o["amount"] for o in live_done)
    dispute_rate = 100 * disputes / tx if tx else 0.0
    refund_rate = 100 * refunds / tx if tx else 0.0
    would_be = 100 * (disputes + prevented) / tx if tx else 0.0
    last7 = sum(r["orders"] for r in series[-7:]) / 7
    prior = sum(r["orders"] for r in series[:-7]) / 23
    spike = (last7 / prior) if prior > 0 else (float("inf") if last7 > 0 else 1.0)
    paused = db.one("SELECT COUNT(DISTINCT json_extract(data_json, '$.listing_id')) AS n FROM events "
                    "WHERE seller_id = ? AND type = 'risk.assessed' AND json_extract(data_json, '$.verdict') = 'PAUSE'",
                    (seller_id,))["n"]
    caps = [o for o in live if o["seller_protection"]]
    protected = sum(1 for o in caps if o["seller_protection"] == "ELIGIBLE")

    findings, score = [], 100
    if dispute_rate >= DISPUTE_LINE:
        score -= 40
        findings.append({"level": "high", "title": f"Dispute rate {dispute_rate:.2f}% is over the {DISPUTE_LINE}% line",
                         "detail": "Card networks put merchants above this ratio into monitoring programs; processors often add reserves or reviews."})
    elif dispute_rate >= DISPUTE_EARLY:
        score -= 20
        findings.append({"level": "medium", "title": f"Dispute rate {dispute_rate:.2f}% is approaching {DISPUTE_LINE}%",
                         "detail": f"{max(0, int(tx * DISPUTE_LINE / 100) - disputes)} more disputes this month would cross the line."})
    if prevented:
        findings.append({"level": "good", "title": f"{prevented} disputes avoided by early resolution",
                         "detail": f"Without them your dispute rate would be {would_be:.2f}% instead of {dispute_rate:.2f}%."})
    if refund_rate >= REFUND_WATCH:
        score -= 10
        findings.append({"level": "medium", "title": f"Refund rate {refund_rate:.1f}%",
                         "detail": "High refund rates are a common review trigger; check listing accuracy and packaging."})
    if spike != float("inf") and spike >= SPIKE_WATCH:
        score -= 15 if spike < 3 else 25
        findings.append({"level": "medium" if spike < 3 else "high",
                         "title": f"Sales jumped {spike:.1f}x this week",
                         "detail": "Sudden volume spikes are a classic hold trigger. Keep tracking numbers on every order and expect longer payout holds."})
    if seller["joined_days_ago"] < 30 and tx >= 20:
        score -= 10
        findings.append({"level": "medium", "title": "New account selling fast",
                         "detail": "New accounts with fast growth get extra scrutiny; verify your identity and business details early."})
    if paused:
        score -= 50
        findings.append({"level": "high",
                         "title": f"{paused} listing{'s' if paused > 1 else ''} had buyer payments paused as likely scams",
                         "detail": "Chats on these listings pushed buyers toward unprotected or off-platform payment."})
    if caps:
        findings.append({"level": "info", "title": f"{protected}/{len(caps)} recent sales covered by PayPal Seller Protection",
                         "detail": "Seller Protection (item-not-received, unauthorized) requires tracking to the buyer's address."})
    score = max(0, min(100, score))
    status = "Healthy" if score >= 80 else "Watch" if score >= 60 else "At risk"
    return {
        "seller": {k: seller[k] for k in ("id", "name", "handle", "joined_days_ago", "completed_sales", "rating", "location")},
        "score": score, "status": status, "findings": findings,
        "kpis": {"transactions_30d": tx, "disputes_30d": disputes, "dispute_rate": round(dispute_rate, 2),
                 "dispute_rate_without_prevention": round(would_be, 2), "refund_rate": round(refund_rate, 2),
                 "prevented_30d": prevented, "gross_30d": round(gross, 2),
                 "volume_spike_x": None if spike == float("inf") else round(spike, 2), "paused_payments": paused},
        "thresholds": {"dispute_line": DISPUTE_LINE, "dispute_early": DISPUTE_EARLY},
        "series": series,
    }


SYSTEM = """You are an account-health coach for small online sellers who get paid through PayPal.
Explain the seller's situation in plain, calm language a non-expert understands. Never claim to know
PayPal's internal risk model; talk about the public signals shown. Be specific with the numbers given.
Return JSON only:
{"headline": "one sentence, max 16 words",
 "summary": "2-3 sentences: what is happening and why it matters for their payouts",
 "actions": ["3 concrete actions, each under 18 words, most important first"]}"""


def explain(seller_id: str) -> dict:
    m = metrics(seller_id)
    if not m:
        return {}
    payload = {k: m[k] for k in ("seller", "score", "status", "kpis", "findings")}
    try:
        res = llm.complete_json(SYSTEM, json.dumps(payload), temperature=0.2)
        d = res["data"] if isinstance(res["data"], dict) else {}
        return {"headline": d.get("headline", ""), "summary": d.get("summary", ""),
                "actions": (d.get("actions") or [])[:3], "provider": res["provider"], "model": res["model"]}
    except llm.LLMUnavailable as e:
        top = m["findings"][0]["title"] if m["findings"] else "No issues detected"
        return {"headline": top, "summary": "AI explanation unavailable right now; showing the raw signals.",
                "actions": [], "error": str(e)}
