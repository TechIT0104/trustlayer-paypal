"""PayPal webhook receiver.

PayPal is the source of truth for money state. Our API calls update orders synchronously,
and webhooks reconcile anything that changes later or elsewhere: a payout that ends up
UNCLAIMED, an authorization voided from the PayPal dashboard, a refund issued by hand.

- Signature: verified with PayPal's verify-webhook-signature API when PAYPAL_WEBHOOK_ID is set.
- Idempotency: PayPal retries deliveries, so each event id is processed once.
"""
from . import config, db, ledger, orders, paypal


def _order_by(field: str, value: str | None) -> dict | None:
    if not value:
        return None
    return db.one(f"SELECT * FROM orders WHERE {field} = ?", (value,))


def _seen(event_id: str) -> bool:
    return bool(db.one("SELECT 1 AS x FROM events WHERE type = 'webhook.received' "
                       "AND json_extract(data_json, '$.event_id') = ? LIMIT 1", (event_id,)))


def handle(event: dict, headers: dict) -> dict:
    event_id = event.get("id") or ""
    etype = event.get("event_type") or ""
    res = event.get("resource") or {}

    verified = None
    if config.PAYPAL_WEBHOOK_ID:
        try:
            verified = paypal.verify_webhook(headers, event, config.PAYPAL_WEBHOOK_ID)
        except paypal.PayPalError:
            verified = False
        if not verified:
            ledger.append("webhook.rejected", {"event_id": event_id, "event_type": etype})
            raise orders.OrderError("webhook signature verification failed", 401)

    if event_id and _seen(event_id):
        return {"ok": True, "duplicate": True}

    o = None
    if etype.startswith("PAYMENT.AUTHORIZATION."):
        o = _order_by("authorization_id", res.get("id"))
        if o and etype.endswith("VOIDED") and o["status"] in ("HELD", "PAUSED"):
            db.update("orders", "id", o["id"], status="CANCELLED")
    elif etype.startswith("PAYMENT.CAPTURE."):
        o = _order_by("capture_id", res.get("id"))
        if not o:  # refunds reference the capture through links
            up = next((l.get("href", "") for l in res.get("links", []) if l.get("rel") == "up"), "")
            o = _order_by("capture_id", up.rstrip("/").rsplit("/", 1)[-1] if up else None)
    elif etype.startswith("PAYMENT.PAYOUTS-ITEM."):
        o = _order_by("payout_batch_id", res.get("payout_batch_id")) or \
            _order_by("id", (res.get("payout_item") or {}).get("sender_item_id"))
        status = res.get("transaction_status") or etype.rsplit(".", 1)[-1]
        if o and status != o["payout_status"]:
            orders.set_payout_status(o, status, "webhook")
    elif etype.startswith("PAYMENT.PAYOUTSBATCH."):
        o = _order_by("payout_batch_id", (res.get("batch_header") or {}).get("payout_batch_id"))
    elif etype.startswith("CHECKOUT.ORDER."):
        o = _order_by("paypal_order_id", res.get("id"))

    ledger.append("webhook.received", {"event_id": event_id, "event_type": etype, "verified": bool(verified),
                                       "resource_id": res.get("id"), "matched_order": o["id"] if o else None},
                  order_id=o["id"] if o else None, seller_id=o["seller_id"] if o else None)
    return {"ok": True, "matched_order": o["id"] if o else None}
