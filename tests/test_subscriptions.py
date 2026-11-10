"""TrustLayer Plus: honest-subscription behaviour against a fake PayPal."""


def start(client, sub_id="I-SUB1"):
    r = client.post("/api/plus/subscriptions", json={"subscription_id": sub_id})
    assert r.status_code == 200, r.text
    return r.json()["subscription"]


def test_plan_is_created_once_with_a_free_trial(client, fake_paypal):
    client.get("/api/plus")
    client.get("/api/plus")
    assert len(fake_paypal.named("create_plan")) == 1
    assert fake_paypal.named("create_plan")[0][1:] == (4.99, 7)


def test_subscription_is_verified_with_paypal_before_access(client, fake_paypal):
    sub = start(client)
    assert fake_paypal.named("get_subscription") and sub["status"] == "ACTIVE" and sub["in_trial"]


def test_subscription_for_another_plan_is_rejected(client, fake_paypal):
    fake_paypal.sub_plan = "P-SOMEONE-ELSE"
    assert client.post("/api/plus/subscriptions", json={"subscription_id": "I-SUB2"}).status_code == 400


def test_unapproved_subscription_is_rejected(client, fake_paypal):
    fake_paypal.sub_status = "APPROVAL_PENDING"
    assert client.post("/api/plus/subscriptions", json={"subscription_id": "I-SUB3"}).status_code == 409


def test_reminder_becomes_due_before_the_first_charge_and_states_facts_by_code(client, fake_llm):
    sub = start(client)
    assert not sub["reminder_due"]
    sub = client.post(f"/api/plus/{sub['id']}/simulate", json={"days": 5}).json()["subscription"]
    assert sub["reminder_due"] and sub["in_trial"]
    rem = client.post(f"/api/plus/{sub['id']}/reminder").json()["subscription"]["reminder"]
    assert "$4.99" in rem["fact"] and "unless you cancel" in rem["fact"]


def test_cancel_is_one_call_and_never_offers_pause_without_usage(client, fake_paypal):
    sub = start(client)
    assist = client.get(f"/api/plus/{sub['id']}/cancel-assist").json()
    assert assist["offer_pause"] is False  # no orders yet = no real value, so no retention offer
    done = client.post(f"/api/plus/{sub['id']}/cancel", json={"reason": "not needed"}).json()["subscription"]
    assert done["status"] == "CANCELLED" and fake_paypal.named("cancel_subscription")


def test_pause_and_resume(client, fake_paypal):
    sub = start(client)
    assert client.post(f"/api/plus/{sub['id']}/pause").json()["subscription"]["status"] == "SUSPENDED"
    assert client.post(f"/api/plus/{sub['id']}/resume").json()["subscription"]["status"] == "ACTIVE"


def test_subscription_webhook_updates_status(client):
    sub = start(client)
    event = {"id": "WH-SUB-1", "event_type": "BILLING.SUBSCRIPTION.CANCELLED", "resource": {"id": sub["id"]}}
    assert client.post("/api/webhooks/paypal", json=event).json()["matched_subscription"] == sub["id"]
    assert client.get("/api/plus").json()["subscription"]["status"] == "CANCELLED"
