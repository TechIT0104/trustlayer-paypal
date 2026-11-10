"""Seller subscriptions kit: terms review, plan creation, subscriber dashboard, forgotten-trial chargeback risk."""

GOOD = {"name": "Lens Care Club", "description": "A cleaning kit and a lens check every month for your cameras.",
        "price": 9.0, "trial_days": 7}


def test_disclosure_is_written_by_code_and_states_the_terms(client):
    r = client.post("/api/sellers/maya/offerings/review", json=GOOD).json()
    assert "$9.00 per month after a 7-day free trial" in r["disclosure"]
    assert "Cancel any time in one confirmation" in r["disclosure"] and not r["blocking"]


def test_trap_terms_are_blocked_by_code(client, fake_paypal):
    bad = {**GOOD, "description": "Monthly kit. 6-month minimum commitment, call us to cancel, $15 cancellation fee."}
    review = client.post("/api/sellers/maya/offerings/review", json=bad).json()
    assert review["verdict"] == "fix_first" and len(review["blocking"]) == 3
    assert client.post("/api/sellers/maya/offerings", json=bad).status_code == 422
    assert not fake_paypal.named("create_plan")  # nothing reached PayPal


def test_ai_rewrite_that_keeps_a_trap_is_not_suggested(client, fake_llm, monkeypatch):
    from backend.app import llm, subscriptions
    real = fake_llm.complete_json

    def review_llm(system, user, temperature=0.1, use_cache=True, providers=None):
        if "review the terms" in system:
            return {"data": {"issues": [], "verdict": "fix_first",
                             "improved_description": "Darkroom access, 6-month minimum commitment, cancel online."},
                    "provider": "fake", "model": "fake", "latency_ms": 1, "cached": False}
        return real(system, user, temperature, use_cache, providers)
    monkeypatch.setattr(llm, "complete_json", review_llm)
    bad = {**GOOD, "description": "Darkroom access. 6-month minimum commitment."}
    r = subscriptions.review_terms(bad["name"], bad["description"], bad["price"], bad["trial_days"])
    assert r["improved_description"] == bad["description"] and r["blocking"]


def test_clean_offering_creates_a_paypal_plan_and_is_listed(client, fake_paypal):
    off = client.post("/api/sellers/maya/offerings", json=GOOD).json()
    assert off["plan_id"] == "P-TEST" and fake_paypal.named("create_plan")[-1][1:] == (9.0, 7)
    assert off["id"] in [o["id"] for o in client.get("/api/offerings").json()]


def test_subscribing_to_a_seller_offering(client, fake_paypal):
    sub = client.post("/api/subscriptions", json={"subscription_id": "I-FILM1", "offering_id": "maya-film-club"}).json()
    assert sub["offering"]["seller_id"] == "maya" and sub["in_trial"] and sub["price"] == 12.0
    assert [s["id"] for s in client.get("/api/subscriptions").json()] == ["I-FILM1"]


def test_unused_trial_near_charge_is_flagged_and_a_delivery_clears_it(client):
    sub = client.post("/api/subscriptions", json={"subscription_id": "I-FILM2", "offering_id": "maya-film-club"}).json()
    assert not sub["chargeback_risk"]  # 14 days to go
    sub = client.post(f"/api/subscriptions/{sub['id']}/simulate", json={"days": 12}).json()
    assert sub["chargeback_risk"] and sub["reminder_due"]
    dash = client.get("/api/sellers/maya/subscribers").json()
    assert dash["summary"]["at_risk"] == 1 and dash["summary"]["in_trial"] == 1
    titles = [f["title"] for f in client.get("/api/sellers/maya/health").json()["findings"]]
    assert any("about to be charged without using it" in t for t in titles)
    sub = client.post(f"/api/subscriptions/{sub['id']}/delivery").json()
    assert sub["usage"]["deliveries_received"] == 1 and not sub["chargeback_risk"]


def test_seller_subscriber_reminder_uses_seller_facts(client):
    sub = client.post("/api/subscriptions", json={"subscription_id": "I-FILM3", "offering_id": "maya-film-club"}).json()
    client.post(f"/api/subscriptions/{sub['id']}/simulate", json={"days": 12})
    rem = client.post(f"/api/subscriptions/{sub['id']}/reminder").json()["reminder"]
    assert "$12.00" in rem["fact"]


def test_generic_cancel_works_for_seller_offerings(client, fake_paypal):
    sub = client.post("/api/subscriptions", json={"subscription_id": "I-FILM4", "offering_id": "maya-film-club"}).json()
    done = client.post(f"/api/subscriptions/{sub['id']}/cancel", json={"reason": "moving"}).json()
    assert done["status"] == "CANCELLED" and fake_paypal.named("cancel_subscription")
