"""PayPal REST client (sandbox): Orders v2, Payments v2 (authorize/capture/void/refund), Payouts v1.

Design notes
- Every state-changing call sends a PayPal-Request-Id derived from our own order/action
  ids, so retries (network blips, double clicks) can never charge or pay out twice.
- The OAuth token is cached until shortly before it expires.
"""
import base64
import threading
import time

import httpx

from . import config


class PayPalError(Exception):
    def __init__(self, status: int, body: dict | str, action: str):
        self.status, self.body, self.action = status, body, action
        name = body.get("name") if isinstance(body, dict) else None
        msg = body.get("message") if isinstance(body, dict) else str(body)[:200]
        super().__init__(f"PayPal {action} failed ({status} {name}): {msg}")

    def to_dict(self) -> dict:
        return {"action": self.action, "status": self.status, "body": self.body}


_token: dict = {"value": None, "exp": 0.0}
_tlock = threading.Lock()
_http = httpx.Client(base_url=config.PAYPAL_BASE_URL, timeout=httpx.Timeout(40.0, connect=10.0))


def configured() -> bool:
    return bool(config.PAYPAL_CLIENT_ID and config.PAYPAL_CLIENT_SECRET)


def _access_token() -> str:
    with _tlock:
        if _token["value"] and time.time() < _token["exp"] - 120:
            return _token["value"]
        creds = base64.b64encode(f"{config.PAYPAL_CLIENT_ID}:{config.PAYPAL_CLIENT_SECRET}".encode()).decode()
        r = _http.post(
            "/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {creds}"},
        )
        if r.status_code != 200:
            raise PayPalError(r.status_code, _json(r), "oauth")
        body = r.json()
        _token.update(value=body["access_token"], exp=time.time() + body.get("expires_in", 3600))
        return _token["value"]


def _json(r: httpx.Response):
    try:
        return r.json() if r.content else {}
    except ValueError:
        return r.text[:500]


def _call(method: str, path: str, action: str, body: dict | None = None, request_id: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json",
               "Prefer": "return=representation"}
    if request_id:
        headers["PayPal-Request-Id"] = request_id
    for attempt in range(3):
        try:
            r = _http.request(method, path, json=body, headers=headers)
        except httpx.TransportError:
            if attempt == 2:
                raise
            time.sleep(0.8 * (attempt + 1))
            continue
        if r.status_code >= 500 and attempt < 2:  # transient: safe to retry thanks to PayPal-Request-Id
            time.sleep(0.8 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise PayPalError(r.status_code, _json(r), action)
        return _json(r)
    raise PayPalError(599, "retries exhausted", action)


def _money(value: float) -> dict:
    return {"currency_code": config.CURRENCY, "value": f"{value:.2f}"}


# ---------- Orders v2 ----------

def create_order(order_ref: str, amount: float, description: str) -> dict:
    """Intent AUTHORIZE: the buyer approves, we place a hold, and nothing is taken until we capture."""
    return _call("POST", "/v2/checkout/orders", "create_order", {
        "intent": "AUTHORIZE",
        "purchase_units": [{
            "reference_id": order_ref,
            "custom_id": order_ref,
            "description": description[:127],
            "soft_descriptor": "TRUSTLAYER",
            "amount": _money(amount),
        }],
        "payment_source": {"paypal": {"experience_context": {
            "brand_name": "TrustLayer Market",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "CONTINUE",
            "return_url": "https://example.com/return",
            "cancel_url": "https://example.com/cancel",
        }}},
    }, request_id=f"{order_ref}-create")


def get_order(paypal_order_id: str) -> dict:
    return _call("GET", f"/v2/checkout/orders/{paypal_order_id}", "get_order")


def authorize_order(paypal_order_id: str, order_ref: str) -> dict:
    return _call("POST", f"/v2/checkout/orders/{paypal_order_id}/authorize", "authorize_order", {},
                 request_id=f"{order_ref}-authorize")


# ---------- Payments v2 ----------

def capture_authorization(authorization_id: str, amount: float, order_ref: str, final: bool = True,
                          note: str = "") -> dict:
    body = {"amount": _money(amount), "final_capture": final}
    if note:
        body["note_to_payer"] = note[:255]
    return _call("POST", f"/v2/payments/authorizations/{authorization_id}/capture", "capture",
                 body, request_id=f"{order_ref}-capture-{amount:.2f}")


def void_authorization(authorization_id: str, order_ref: str) -> dict:
    return _call("POST", f"/v2/payments/authorizations/{authorization_id}/void", "void", None,
                 request_id=f"{order_ref}-void")


def get_authorization(authorization_id: str) -> dict:
    return _call("GET", f"/v2/payments/authorizations/{authorization_id}", "get_authorization")


def refund_capture(capture_id: str, amount: float, order_ref: str, note: str = "") -> dict:
    body = {"amount": _money(amount)}
    if note:
        body["note_to_payer"] = note[:255]
    return _call("POST", f"/v2/payments/captures/{capture_id}/refund", "refund", body,
                 request_id=f"{order_ref}-refund-{amount:.2f}")


# ---------- Payouts v1 ----------

def create_payout(receiver_email: str, amount: float, order_ref: str, note: str) -> dict:
    return _call("POST", "/v1/payments/payouts", "payout", {
        "sender_batch_header": {
            "sender_batch_id": f"tl-{order_ref}",  # PayPal rejects a reused batch id: built-in double-payout guard
            "email_subject": "You've been paid for your TrustLayer Market sale",
            "email_message": note[:255],
        },
        "items": [{
            "recipient_type": "EMAIL", "receiver": receiver_email, "amount": _money(amount),
            "note": note[:255], "sender_item_id": order_ref,
        }],
    }, request_id=f"{order_ref}-payout")


def get_payout(batch_id: str) -> dict:
    return _call("GET", f"/v1/payments/payouts/{batch_id}", "get_payout")
