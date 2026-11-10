from backend.app import db, ledger


def test_chain_verifies_after_appends(fresh_db):
    before = ledger.verify()["count"]
    for i in range(5):
        ledger.append("test.event", {"i": i}, order_id="TL-X")
    v = ledger.verify()
    assert v["ok"] and v["count"] == before + 5


def test_editing_a_record_is_detected_at_that_record(fresh_db):
    ledger.append("payment.captured", {"amount": 100})
    target = ledger.append("payment.captured", {"amount": 200})["seq"]
    ledger.append("payout.sent", {"amount": 190})
    db.run("UPDATE events SET data_json = ? WHERE seq = ?", ('{"amount": 2}', target))
    v = ledger.verify()
    assert not v["ok"] and v["broken_at"] == target


def test_deleting_a_record_breaks_the_chain(fresh_db):
    a = ledger.append("a", {})["seq"]
    ledger.append("b", {})
    db.run("DELETE FROM events WHERE seq = ?", (a,))
    assert not ledger.verify()["ok"]
