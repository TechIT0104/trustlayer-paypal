from backend.app.resolution import DEFAULT_POLICY, enforce

POLICY = {**DEFAULT_POLICY, "max_partial_refund_pct": 20}


def facts(delivered=True, days_late=0, refunded=0.0, price=180.0):
    return {"price_paid": price, "already_refunded": refunded, "days_late": days_late,
            "tracking": "delivered" if delivered else "in transit"}


def test_partial_refund_is_capped_at_policy_limit():
    offer, notes = enforce({"type": "partial_refund", "amount": 90}, "damaged", facts(), POLICY)
    assert offer == {"type": "partial_refund", "amount": 36.0, "reason": ""} and notes


def test_full_refund_on_a_delivered_item_goes_to_the_seller():
    offer, notes = enforce({"type": "full_refund", "amount": 180}, "late_delivery", facts(), POLICY)
    assert offer["type"] == "escalate" and offer["amount"] == 0 and notes


def test_full_refund_allowed_when_never_delivered_and_long_overdue():
    offer, _ = enforce({"type": "full_refund", "amount": 5}, "not_received", facts(delivered=False, days_late=9), POLICY)
    assert offer["type"] == "full_refund" and offer["amount"] == 180.0


def test_full_refund_not_yet_allowed_when_only_slightly_late():
    offer, _ = enforce({"type": "full_refund"}, "not_received", facts(delivered=False, days_late=2), POLICY)
    assert offer["type"] == "escalate"


def test_change_of_mind_gets_no_money():
    offer, notes = enforce({"type": "partial_refund", "amount": 10}, "changed_mind", facts(), POLICY)
    assert offer["type"] == "none" and offer["amount"] == 0 and notes


def test_replacement_without_stock_becomes_partial_refund():
    offer, notes = enforce({"type": "replacement"}, "damaged", facts(), POLICY)
    assert offer["type"] == "partial_refund" and offer["amount"] == 36.0 and notes


def test_offer_never_exceeds_what_is_left_to_refund():
    offer, _ = enforce({"type": "partial_refund", "amount": 30}, "damaged", facts(refunded=170.0), POLICY)
    assert offer["amount"] == 10.0


def test_missing_amount_uses_goodwill_default_and_unknown_type_escalates():
    offer, _ = enforce({"type": "partial_refund"}, "late_delivery", facts(), POLICY)
    assert offer["amount"] == 18.0
    offer, _ = enforce({"type": "teleport", "amount": 50}, "other", facts(), POLICY)
    assert offer["type"] == "escalate" and offer["amount"] == 0
