"""End-to-end API flows against a fake PayPal: every state transition and every money call."""
import time

from backend.app import config, db, ledger, paypal

SCAM_AI = {"risk": 0.9, "scam_type": "protection_bypass", "explanation": "bypass", "spell_breaker": "stop",
           "safe_next_step": "use checkout", "evidence": [{"line": 4, "quote": "friends and family", "why": "bypass"}]}


def buy(client, listing="L1", **extra):
    r = client.post("/api/orders", json={"listing_id": listing, **extra})
    assert r.status_code == 200, r.text
    oid = r.json()["order_id"]
    a = client.post(f"/api/orders/{oid}/authorize")
    assert a.status_code == 200, a.text
    return oid, a.json()


def test_happy_path_hold_capture_payout(client, fake_paypal):
    oid, o = buy(client)
    assert o["status"] == "HELD" and o["seller_protection"] == "ELIGIBLE" and o["auth_expires"]
    done = client.post(f"/api/orders/{oid}/received").json()
    assert done["status"] == "PAID_OUT"
    assert fake_paypal.named("capture")[0][2:] == (180.0, True)
    assert done["fee"] == 9.0 and done["payout_amount"] == 171.0
    assert fake_paypal.named("payout")[0][2] == 171.0
    assert ledger.verify()["ok"]


def test_authorize_is_idempotent(client, fake_paypal):
    oid, _ = buy(client)
    again = client.post(f"/api/orders/{oid}/authorize").json()
    assert again["status"] == "HELD" and len(fake_paypal.named("authorize_order")) == 1


def test_paused_payment_requires_acknowledgement(client, fake_llm):
    fake_llm.scam = SCAM_AI
    r = client.post("/api/orders", json={"listing_id": "L2"})
    assert r.status_code == 409


def test_trusted_contact_can_stop_a_paused_payment(client, fake_llm, fake_paypal):
    fake_llm.scam = SCAM_AI
    oid, o = buy(client, "L2", acknowledged=True, trusted_contact="Mom")
    assert o["status"] == "PAUSED" and 0 < o["seconds_left"] <= config.COOLING_OFF_SECONDS
    token = client.get(f"/api/orders/{oid}/contact-link").json()["token"]
    res = client.post(f"/api/contact/{token}", json={"verdict": "scam"}).json()
    assert res["order"]["status"] == "CANCELLED" and fake_paypal.named("void")
    assert not fake_paypal.named("capture")


def test_cooling_off_expiry_moves_to_escrow_and_blocks_early_release(client, fake_llm):
    fake_llm.scam = SCAM_AI
    oid, _ = buy(client, "L2", acknowledged=True, trusted_contact="Mom")
    assert client.post(f"/api/orders/{oid}/received").status_code == 400
    db.update("orders", "id", oid, hold_until=time.time() - 1)
    assert client.get(f"/api/orders/{oid}").json()["status"] == "HELD"


def test_buyer_can_cancel_a_held_order(client, fake_paypal):
    oid, _ = buy(client)
    assert client.post(f"/api/orders/{oid}/cancel").json()["status"] == "CANCELLED"
    assert client.post(f"/api/orders/{oid}/cancel").status_code == 400


def test_resolution_on_held_order_captures_less_instead_of_refunding(client, fake_llm, fake_paypal):
    fake_llm.resolution["offer"] = {"type": "partial_refund", "amount": 60, "reason": "late"}  # above the 20% cap
    oid, _ = buy(client)
    issue = client.post(f"/api/orders/{oid}/issue", json={"text": "It came 4 days late"}).json()
    assert issue["status"] == "OFFERED" and issue["offer"]["amount"] == 36.0
    assert issue["transcript"][-1]["policy_notes"]
    settled = client.post(f"/api/issues/{issue['id']}/accept").json()
    assert settled["status"] == "RESOLVED"
    assert fake_paypal.named("capture")[0][2] == 144.0 and not fake_paypal.named("refund")
    paid = client.post(f"/api/orders/{oid}/received").json()
    assert paid["payout_amount"] == round(144 * 0.95, 2)


def test_resolution_after_payout_uses_the_refunds_api(client, fake_llm, fake_paypal):
    oid, _ = buy(client)
    client.post(f"/api/orders/{oid}/received")
    issue = client.post(f"/api/orders/{oid}/issue", json={"text": "small scratch"}).json()
    client.post(f"/api/issues/{issue['id']}/accept")
    assert fake_paypal.named("refund")[0][2] == 18.0
    assert client.get(f"/api/orders/{oid}").json()["refunded_amount"] == 18.0


def test_escalation_reaches_the_seller_inbox_and_seller_can_refund(client, fake_llm, fake_paypal):
    fake_llm.resolution["offer"] = {"type": "full_refund", "amount": 180, "reason": "angry"}  # not allowed: delivered
    oid, _ = buy(client)
    issue = client.post(f"/api/orders/{oid}/issue", json={"text": "I want everything back"}).json()
    assert issue["status"] == "ESCALATED"
    inbox = client.get("/api/sellers/maya/issues").json()
    assert inbox[0]["id"] == issue["id"]
    assert client.post(f"/api/issues/{issue['id']}/accept").status_code == 400
    bad = client.post(f"/api/issues/{issue['id']}/seller-decision", json={"action": "refund", "amount": 999})
    assert bad.status_code == 400
    ok = client.post(f"/api/issues/{issue['id']}/seller-decision", json={"action": "refund", "amount": 50}).json()
    assert ok["status"] == "RESOLVED" and fake_paypal.named("capture")[0][2] == 130.0


def test_seller_can_decline_an_escalated_case(client, fake_llm):
    fake_llm.resolution["offer"] = {"type": "escalate", "amount": 0, "reason": "severe"}
    oid, _ = buy(client)
    issue = client.post(f"/api/orders/{oid}/issue", json={"text": "broken"}).json()
    res = client.post(f"/api/issues/{issue['id']}/seller-decision", json={"action": "decline"}).json()
    assert res["status"] == "DECLINED"


def test_declined_funding_source_asks_the_buyer_to_restart(client, fake_paypal):
    fake_paypal.fail["authorize_order"] = paypal.PayPalError(
        422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "INSTRUMENT_DECLINED"}]}, "authorize_order")
    oid = client.post("/api/orders", json={"listing_id": "L1"}).json()["order_id"]
    r = client.post(f"/api/orders/{oid}/authorize")
    assert r.status_code == 422 and r.json()["restart"] is True


def test_expired_authorization_is_reauthorized_before_capture(client, fake_paypal):
    oid, _ = buy(client)
    fake_paypal.fail["capture"] = paypal.PayPalError(
        422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "AUTHORIZATION_EXPIRED"}]}, "capture")
    done = client.post(f"/api/orders/{oid}/received").json()
    assert done["status"] == "PAID_OUT" and fake_paypal.named("reauthorize")
    assert fake_paypal.named("capture")[-1][1].startswith("AUTH2-")


def test_payout_status_is_reconciled(client, fake_paypal):
    oid, _ = buy(client)
    client.post(f"/api/orders/{oid}/received")
    assert client.post(f"/api/orders/{oid}/payout-status").json()["payout_status"] == "SUCCESS"


def test_webhook_updates_payout_status_once(client):
    oid, _ = buy(client)
    client.post(f"/api/orders/{oid}/received")
    event = {"id": "WH-1", "event_type": "PAYMENT.PAYOUTS-ITEM.UNCLAIMED",
             "resource": {"payout_batch_id": f"B-{oid}", "transaction_status": "UNCLAIMED",
                          "payout_item": {"sender_item_id": oid}}}
    assert client.post("/api/webhooks/paypal", json=event).json()["matched_order"] == oid
    assert client.get(f"/api/orders/{oid}").json()["payout_status"] == "UNCLAIMED"
    assert client.post("/api/webhooks/paypal", json=event).json()["duplicate"] is True


def test_webhook_void_from_paypal_dashboard_cancels_order(client):
    oid, o = buy(client)
    event = {"id": "WH-2", "event_type": "PAYMENT.AUTHORIZATION.VOIDED", "resource": {"id": o["authorization_id"]}}
    client.post("/api/webhooks/paypal", json=event)
    assert client.get(f"/api/orders/{oid}").json()["status"] == "CANCELLED"


def test_webhook_signature_is_enforced_when_configured(client):
    config.PAYPAL_WEBHOOK_ID = "WH-CONFIGURED"
    event = {"id": "WH-3", "event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "X"}}
    assert client.post("/api/webhooks/paypal", json=event).status_code == 401
    assert client.post("/api/webhooks/paypal", json=event, headers={"x-test-valid": "1"}).status_code == 200


def test_demo_endpoints_are_disabled_outside_demo_mode(client):
    config.DEMO_MODE = False
    assert client.post("/api/admin/reset").status_code == 403
    assert client.post("/api/ledger/tamper").status_code == 403


def test_seller_health_counts_paused_listings_once(client, fake_llm):
    fake_llm.scam = SCAM_AI
    for _ in range(3):
        client.post("/api/assess", json={"listing_id": "L2"})
    h = client.get("/api/sellers/quickdeals/health").json()
    assert h["kpis"]["paused_payments"] == 1 and h["status"] == "At risk"
