"""Order lifecycle on top of PayPal: hold -> (cooling-off) -> release + payout, or void.

    CREATED --buyer approves--> authorize --> HELD     (normal escrow, money on hold)
                                          \-> PAUSED   (risky: cooling-off + trusted contact)
    PAUSED --timer ends / contact says OK--> HELD
    PAUSED|HELD --buyer cancels / contact says scam--> void --> CANCELLED (nothing charged)
    HELD --buyer confirms delivery--> capture --> CAPTURED --> payout to seller --> PAID_OUT
"""
import json
import secrets
import time
import uuid

from . import config, db, ledger, paypal, scam


class OrderError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def listing_bundle(listing_id: str) -> tuple[dict, dict, list[dict]]:
    listing = db.one("SELECT * FROM listings WHERE id = ?", (listing_id,))
    if not listing:
        raise OrderError("listing not found", 404)
    seller = db.one("SELECT * FROM sellers WHERE id = ?", (listing["seller_id"],))
    messages = db.all("SELECT sender, text, ts FROM messages WHERE listing_id = ? ORDER BY id", (listing_id,))
    return listing, seller, messages


def assess_listing(listing_id: str) -> dict:
    listing, seller, messages = listing_bundle(listing_id)
    risk = scam.assess(listing, seller, messages)
    ledger.append("risk.assessed", {
        "listing_id": listing_id, "verdict": risk["verdict"], "score": risk["score"],
        "rules": [s["key"] for s in risk["signals"]],
        "ai_type": (risk["ai"] or {}).get("scam_type"), "provider": (risk["ai"] or {}).get("provider"),
    }, seller_id=seller["id"])
    return risk


def get(order_id: str) -> dict:
    o = db.one("SELECT * FROM orders WHERE id = ?", (order_id,))
    if not o:
        raise OrderError("order not found", 404)
    return _tick(o)


def _tick(o: dict) -> dict:
    """Cooling-off ends by itself: a PAUSED hold becomes a normal escrow HELD."""
    if o["status"] == "PAUSED" and o["hold_until"] and time.time() >= o["hold_until"] and o["contact_verdict"] != "scam":
        db.update("orders", "id", o["id"], status="HELD")
        ledger.append("pause.expired", {"note": "cooling-off ended without cancellation; funds stay in escrow"},
                      order_id=o["id"], seller_id=o["seller_id"])
        o = db.one("SELECT * FROM orders WHERE id = ?", (o["id"],))
    return o


def view(o: dict) -> dict:
    o = dict(o)
    o["risk"] = db.loads(o.pop("risk_json"), None)
    o["listing"] = db.one("SELECT id, title, emoji, price, seller_id FROM listings WHERE id = ?", (o["listing_id"],))
    s = db.one("SELECT id, name, handle FROM sellers WHERE id = ?", (o["seller_id"],))
    o["seller"] = s
    o["seconds_left"] = max(0, int((o["hold_until"] or 0) - time.time())) if o["status"] == "PAUSED" else 0
    o.pop("contact_token", None)
    issue = db.one("SELECT id, status FROM issues WHERE order_id = ? ORDER BY created_at DESC LIMIT 1", (o["id"],))
    o["issue"] = issue
    return o


def create(listing_id: str, acknowledged: bool, trusted_contact: str | None) -> dict:
    listing, seller, _ = listing_bundle(listing_id)
    risk = scam.assess(*listing_bundle(listing_id))  # cached LLM result if nothing changed
    if risk["verdict"] == "PAUSE" and not acknowledged:
        raise OrderError("This payment was paused for your safety. Review the warning first.", 409)
    oid = "TL-" + uuid.uuid4().hex[:8].upper()
    now = time.time()
    f = db.loads(listing.get("fulfil_json"), {}) or {}
    db.run(
        "INSERT INTO orders (id, listing_id, seller_id, amount, status, risk_json, trusted_contact, contact_token,"
        " shipped_days_ago, promised_days, delivered_days_ago, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (oid, listing_id, seller["id"], listing["price"], "CREATED", json.dumps(risk), trusted_contact or None,
         secrets.token_urlsafe(12) if risk["verdict"] == "PAUSE" else None,
         f.get("shipped_days_ago"), f.get("promised_days"), f.get("delivered_days_ago"), now, now),
    )
    pp = paypal.create_order(oid, listing["price"], f"{listing['title']} ({oid})")
    db.update("orders", "id", oid, paypal_order_id=pp["id"])
    ledger.append("order.created", {"paypal_order_id": pp["id"], "amount": listing["price"], "intent": "AUTHORIZE",
                                    "risk_verdict": risk["verdict"], "acknowledged_warning": acknowledged},
                  order_id=oid, seller_id=seller["id"])
    return {"order_id": oid, "paypal_order_id": pp["id"], "verdict": risk["verdict"],
            "approve_url": next((l["href"] for l in pp.get("links", []) if l["rel"] in ("payer-action", "approve")), None)}


def authorize(order_id: str) -> dict:
    o = get(order_id)
    if o["status"] != "CREATED":
        return view(o)  # idempotent: already authorized
    res = paypal.authorize_order(o["paypal_order_id"], o["id"])
    auth = res["purchase_units"][0]["payments"]["authorizations"][0]
    risk = db.loads(o["risk_json"], {}) or {}
    paused = risk.get("verdict") == "PAUSE"
    status = "PAUSED" if paused else "HELD"
    db.update("orders", "id", o["id"], status=status, authorization_id=auth["id"],
              seller_protection=(auth.get("seller_protection") or {}).get("status"),
              hold_until=(time.time() + config.COOLING_OFF_SECONDS) if paused else None)
    ledger.append("payment.authorized", {
        "authorization_id": auth["id"], "amount": auth["amount"]["value"], "status": auth["status"],
        "expires": auth.get("expiration_time"), "mode": "cooling_off" if paused else "escrow_hold",
        "payer": (res.get("payer") or {}).get("email_address"),
    }, order_id=o["id"], seller_id=o["seller_id"])
    return view(get(order_id))


def cancel(order_id: str, reason: str = "buyer_cancelled") -> dict:
    o = get(order_id)
    if o["status"] not in ("PAUSED", "HELD"):
        raise OrderError(f"cannot cancel an order that is {o['status']}")
    paypal.void_authorization(o["authorization_id"], o["id"])
    db.update("orders", "id", o["id"], status="CANCELLED")
    ledger.append("payment.voided", {"authorization_id": o["authorization_id"], "reason": reason,
                                     "buyer_charged": 0}, order_id=o["id"], seller_id=o["seller_id"])
    return view(get(order_id))


def contact_case(token: str) -> dict:
    o = db.one("SELECT * FROM orders WHERE contact_token = ?", (token,))
    if not o:
        raise OrderError("link not found", 404)
    o = _tick(o)
    return {"order": view(o), "risk": db.loads(o["risk_json"], {})}


def contact_verdict(token: str, verdict: str) -> dict:
    o = db.one("SELECT * FROM orders WHERE contact_token = ?", (token,))
    if not o:
        raise OrderError("link not found", 404)
    if verdict not in ("safe", "scam"):
        raise OrderError("verdict must be safe or scam")
    db.update("orders", "id", o["id"], contact_verdict=verdict)
    ledger.append("contact.verdict", {"verdict": verdict, "contact": o["trusted_contact"]},
                  order_id=o["id"], seller_id=o["seller_id"])
    if verdict == "scam" and o["status"] in ("PAUSED", "HELD"):
        return {"order": cancel(o["id"], reason="trusted_contact_flagged_scam")}
    if verdict == "safe" and o["status"] == "PAUSED":
        db.update("orders", "id", o["id"], status="HELD", hold_until=time.time())
        ledger.append("pause.released", {"by": "trusted_contact"}, order_id=o["id"], seller_id=o["seller_id"])
    return {"order": view(get(o["id"]))}


def _payout(o: dict) -> dict:
    seller = db.one("SELECT * FROM sellers WHERE id = ?", (o["seller_id"],))
    net_sale = round((o["captured_amount"] or 0) - (o["refunded_amount"] or 0), 2)
    fee = round(net_sale * config.PLATFORM_FEE_PCT / 100, 2)
    amount = round(net_sale - fee, 2)
    if amount <= 0:
        db.update("orders", "id", o["id"], status="CLOSED", fee=fee)
        return view(get(o["id"]))
    res = paypal.create_payout(seller["paypal_email"], amount, o["id"],
                               f"Payout for order {o['id']} (sale ${net_sale:.2f} minus {config.PLATFORM_FEE_PCT:g}% platform fee)")
    batch = res["batch_header"]["payout_batch_id"]
    db.update("orders", "id", o["id"], status="PAID_OUT", payout_batch_id=batch, payout_amount=amount, fee=fee)
    ledger.append("payout.sent", {"payout_batch_id": batch, "receiver": seller["paypal_email"], "amount": amount,
                                  "platform_fee": fee, "batch_status": res["batch_header"].get("batch_status")},
                  order_id=o["id"], seller_id=o["seller_id"])
    return view(get(o["id"]))


def capture_remaining(o: dict, keep_amount: float, note: str) -> dict:
    """Capture `keep_amount` of the authorization as final; PayPal releases the rest of the hold."""
    res = paypal.capture_authorization(o["authorization_id"], keep_amount, o["id"], final=True, note=note)
    sp = (res.get("seller_protection") or {}).get("status") or o["seller_protection"]
    db.update("orders", "id", o["id"], status="CAPTURED", capture_id=res["id"], captured_amount=keep_amount,
              seller_protection=sp)
    bd = res.get("seller_receivable_breakdown") or {}
    ledger.append("payment.captured", {
        "capture_id": res["id"], "amount": keep_amount, "released_to_buyer": round(o["amount"] - keep_amount, 2),
        "paypal_fee": (bd.get("paypal_fee") or {}).get("value"), "seller_protection": sp,
    }, order_id=o["id"], seller_id=o["seller_id"])
    return get(o["id"])


def confirm_received(order_id: str) -> dict:
    o = get(order_id)
    if o["status"] == "PAUSED":
        raise OrderError("This payment is still in its cooling-off period.")
    if o["status"] == "HELD":
        o = capture_remaining(o, o["amount"], "Thanks! Your TrustLayer order is complete.")
    if o["status"] == "CAPTURED":
        return _payout(o)
    raise OrderError(f"cannot release an order that is {o['status']}")


def list_all() -> list[dict]:
    return [view(_tick(o)) for o in db.all("SELECT * FROM orders ORDER BY created_at DESC")]
