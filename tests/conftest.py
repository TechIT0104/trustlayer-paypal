"""Test harness: an isolated SQLite file, a fake PayPal, and a scriptable fake LLM.

Nothing here touches the network, so the suite is fast and deterministic.
"""
import os
import pathlib
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="trustlayer-test-")
os.environ["DB_PATH"] = str(pathlib.Path(_TMP) / "test.db")
os.environ["COOLING_OFF_SECONDS"] = "120"
os.environ["PAYPAL_WEBHOOK_ID"] = ""
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from backend.app import config, db, llm, paypal, seed  # noqa: E402


class FakePayPal:
    """Records every call and returns PayPal-shaped responses."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.fail: dict[str, paypal.PayPalError] = {}

    def _maybe_fail(self, name):
        if name in self.fail:
            raise self.fail.pop(name)

    def create_order(self, ref, amount, desc):
        self.calls.append(("create_order", ref, amount))
        return {"id": f"PP{ref}", "links": [{"rel": "payer-action", "href": f"https://sandbox.paypal.test/{ref}"}]}

    def authorize_order(self, pp_id, ref):
        self.calls.append(("authorize_order", pp_id))
        self._maybe_fail("authorize_order")
        return {"payer": {"email_address": "buyer@example.com"},
                "purchase_units": [{"payments": {"authorizations": [{
                    "id": f"AUTH-{ref}", "status": "CREATED", "amount": {"value": "0"},
                    "seller_protection": {"status": "ELIGIBLE"}, "expiration_time": "2026-12-09T00:00:00Z"}]}}]}

    def capture_authorization(self, auth_id, amount, ref, final=True, note=""):
        self.calls.append(("capture", auth_id, amount, final))
        self._maybe_fail("capture")
        return {"id": f"CAP-{ref}", "status": "COMPLETED", "seller_protection": {"status": "ELIGIBLE"},
                "seller_receivable_breakdown": {"paypal_fee": {"value": "1.00"}}}

    def void_authorization(self, auth_id, ref):
        self.calls.append(("void", auth_id))
        return {}

    def reauthorize(self, auth_id, amount, ref):
        self.calls.append(("reauthorize", auth_id, amount))
        return {"id": f"AUTH2-{ref}", "expiration_time": "2026-12-30T00:00:00Z"}

    def refund_capture(self, capture_id, amount, ref, note=""):
        self.calls.append(("refund", capture_id, amount))
        return {"id": f"REF-{ref}", "status": "COMPLETED"}

    def create_payout(self, email, amount, ref, note):
        self.calls.append(("payout", email, amount))
        return {"batch_header": {"payout_batch_id": f"B-{ref}", "batch_status": "PENDING"}}

    def get_payout(self, batch_id):
        self.calls.append(("get_payout", batch_id))
        return {"batch_header": {"batch_status": "SUCCESS"}, "items": [{"transaction_status": "SUCCESS"}]}

    def verify_webhook(self, headers, event, webhook_id):
        return headers.get("x-test-valid") == "1"

    def named(self, name):
        return [c for c in self.calls if c[0] == name]


class FakeLLM:
    """Scripted answers keyed by which prompt is calling (scam analyst / resolution / health)."""

    def __init__(self):
        self.scam = {"risk": 0.0, "scam_type": "none", "evidence": [], "explanation": "Looks normal.",
                     "spell_breaker": "", "safe_next_step": ""}
        self.resolution = {"issue_type": "late_delivery", "severity": "low", "buyer_sentiment": "frustrated",
                           "dispute_risk": 0.6, "reply": "Sorry! I can offer $18 back.",
                           "offer": {"type": "partial_refund", "amount": 18, "reason": "late"}}
        self.down = False
        self.prompts: list[str] = []

    def complete_json(self, system, user, temperature=0.1, use_cache=True, providers=None):
        if self.down:
            raise llm.LLMUnavailable("all providers down (test)")
        self.prompts.append(user)
        if "payment-safety analyst" in system:
            data = self.scam
        elif "resolution assistant" in system:
            data = self.resolution
        else:
            data = {"headline": "ok", "summary": "ok", "actions": ["a", "b", "c"]}
        return {"data": data, "provider": "fake", "model": "fake-model", "latency_ms": 1, "cached": False}


@pytest.fixture()
def fake_paypal(monkeypatch):
    fp = FakePayPal()
    for name in ("create_order", "authorize_order", "capture_authorization", "void_authorization", "reauthorize",
                 "refund_capture", "create_payout", "get_payout", "verify_webhook"):
        monkeypatch.setattr(paypal, name, getattr(fp, name))
    return fp


@pytest.fixture()
def fake_llm(monkeypatch):
    fl = FakeLLM()
    monkeypatch.setattr(llm, "complete_json", fl.complete_json)
    return fl


@pytest.fixture()
def fresh_db():
    seed.run(force=True)
    yield
    config.PAYPAL_WEBHOOK_ID = ""
    config.DEMO_MODE = True


@pytest.fixture()
def client(fresh_db, fake_paypal, fake_llm):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    with TestClient(app) as c:
        yield c
