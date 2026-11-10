"""TrustLayer API + static frontend.

Run locally:  .venv/Scripts/python -m uvicorn backend.app.main:app --port 8000
"""
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db, health, ledger, llm, localmodel, orders, paypal, resolution, seed, subscriptions, webhooks

@asynccontextmanager
async def lifespan(_: FastAPI):
    seed.run()  # seeds demo data on first start only
    yield


app = FastAPI(title="TrustLayer", version="1.0.0", lifespan=lifespan,
              description="A trust layer for both sides of a PayPal payment: Pay-pause scam interception, "
                          "pre-dispute resolution, and seller account health.")
FRONTEND = config.ROOT / "frontend"


@app.exception_handler(paypal.PayPalError)
def _paypal_error(_: Request, e: paypal.PayPalError):
    ledger.append("paypal.error", e.to_dict())
    return JSONResponse(status_code=502, content={"error": str(e), "paypal": e.to_dict()})


@app.exception_handler(orders.OrderError)
def _order_error(_: Request, e: orders.OrderError):
    return JSONResponse(status_code=e.status,
                        content={"error": str(e), "restart": isinstance(e, orders.RestartPayment)})


def _demo_only() -> None:
    if not config.DEMO_MODE:
        raise orders.OrderError("disabled outside demo mode", 403)


@app.exception_handler(llm.LLMUnavailable)
def _llm_error(_: Request, e: llm.LLMUnavailable):
    return JSONResponse(status_code=503, content={"error": "All AI providers are unavailable right now.", "detail": str(e)})


# ---------- config & status ----------

@app.get("/api/config")
def get_config():
    return {"paypal_client_id": config.PAYPAL_CLIENT_ID, "currency": config.CURRENCY,
            "cooling_off_seconds": config.COOLING_OFF_SECONDS, "platform_fee_pct": config.PLATFORM_FEE_PCT,
            "paypal_configured": paypal.configured(), "llm_providers": config.LLM_PROVIDERS,
            "local_model": localmodel.info(), "demo_mode": config.DEMO_MODE,
            "buyer_hint": "Use a PayPal sandbox personal account to approve payments."}


@app.get("/api/status")
def status():
    return {"llm": llm.stats, "ledger": ledger.verify(), "time": time.time()}


# ---------- marketplace ----------

@app.get("/api/listings")
def listings():
    rows = db.all("SELECT l.*, s.name AS seller_name, s.handle, s.rating, s.completed_sales, s.joined_days_ago "
                  "FROM listings l JOIN sellers s ON s.id = l.seller_id ORDER BY l.id")
    for r in rows:
        r.pop("fulfil_json", None)
    return rows


@app.get("/api/listings/{listing_id}")
def listing(listing_id: str):
    li, seller, messages = orders.listing_bundle(listing_id)
    li.pop("fulfil_json", None)
    seller.pop("paypal_email", None)
    return {"listing": li, "seller": seller, "messages": messages}


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    sender: str = "buyer"


@app.post("/api/listings/{listing_id}/messages")
def add_message(listing_id: str, body: MessageIn):
    orders.listing_bundle(listing_id)
    sender = body.sender if body.sender in ("buyer", "seller") else "buyer"
    db.run("INSERT INTO messages (listing_id, sender, text, ts) VALUES (?,?,?,?)",
           (listing_id, sender, body.text.strip(), time.time()))
    return listing(listing_id)


# ---------- Pay-pause ----------

class AssessIn(BaseModel):
    listing_id: str


@app.post("/api/assess")
def assess(body: AssessIn):
    return orders.assess_listing(body.listing_id)


class OrderIn(BaseModel):
    listing_id: str
    acknowledged: bool = False
    trusted_contact: str | None = None


@app.post("/api/orders")
def create_order(body: OrderIn):
    return orders.create(body.listing_id, body.acknowledged, body.trusted_contact)


@app.get("/api/orders")
def list_orders():
    return orders.list_all()


@app.get("/api/orders/{order_id}")
def get_order(order_id: str):
    o = orders.view(orders.get(order_id))
    o["events"] = ledger.recent(100, order_id=order_id)
    return o


@app.post("/api/orders/{order_id}/authorize")
def authorize(order_id: str):
    return orders.authorize(order_id)


@app.post("/api/orders/{order_id}/cancel")
def cancel(order_id: str):
    return orders.cancel(order_id)


@app.post("/api/orders/{order_id}/received")
def received(order_id: str):
    return orders.confirm_received(order_id)


@app.post("/api/orders/{order_id}/payout-status")
def payout_status(order_id: str):
    return orders.refresh_payout(order_id)


@app.post("/api/webhooks/paypal")
async def paypal_webhook(request: Request):
    event = await request.json()
    return webhooks.handle(event, dict(request.headers))


@app.get("/api/contact/{token}")
def contact_case(token: str):
    return orders.contact_case(token)


class VerdictIn(BaseModel):
    verdict: str


@app.post("/api/contact/{token}")
def contact_verdict(token: str, body: VerdictIn):
    return orders.contact_verdict(token, body.verdict)


@app.get("/api/orders/{order_id}/contact-link")
def contact_link(order_id: str):
    o = orders.get(order_id)
    if not o["contact_token"]:
        raise orders.OrderError("this order has no trusted-contact check", 404)
    return {"token": o["contact_token"], "contact": o["trusted_contact"]}


# ---------- resolution agent ----------

class IssueIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@app.post("/api/orders/{order_id}/issue")
def issue_message(order_id: str, body: IssueIn):
    return resolution.message(order_id, body.text)


@app.get("/api/issues/{issue_id}")
def get_issue(issue_id: str):
    return resolution.get_issue(issue_id)


@app.post("/api/issues/{issue_id}/accept")
def accept_offer(issue_id: str):
    return resolution.accept(issue_id)


class DecisionIn(BaseModel):
    action: str
    amount: float = 0.0


@app.post("/api/issues/{issue_id}/seller-decision")
def seller_decision(issue_id: str, body: DecisionIn):
    return resolution.seller_decision(issue_id, body.action, body.amount)


@app.get("/api/sellers/{seller_id}/issues")
def seller_issues(seller_id: str):
    return resolution.seller_issues(seller_id)


# ---------- TrustLayer Plus (PayPal Subscriptions) ----------

@app.get("/api/plus")
def plus():
    return subscriptions.view(subscriptions.current())


class SubIn(BaseModel):
    subscription_id: str = Field(min_length=6, max_length=64)


@app.post("/api/plus/subscriptions")
def plus_register(body: SubIn):
    return subscriptions.register(body.subscription_id)


class DaysIn(BaseModel):
    days: float = Field(gt=0, le=30)


@app.post("/api/plus/{sub_id}/simulate")
def plus_simulate(sub_id: str, body: DaysIn):
    return subscriptions.simulate_days(sub_id, body.days)


@app.post("/api/plus/{sub_id}/reminder")
def plus_reminder(sub_id: str):
    return subscriptions.reminder(sub_id)


@app.get("/api/plus/{sub_id}/cancel-assist")
def plus_cancel_assist(sub_id: str):
    return subscriptions.cancel_assist(sub_id)


class CancelIn(BaseModel):
    reason: str = Field(default="", max_length=200)


@app.post("/api/plus/{sub_id}/cancel")
def plus_cancel(sub_id: str, body: CancelIn):
    return subscriptions.cancel(sub_id, body.reason)


@app.post("/api/plus/{sub_id}/pause")
def plus_pause(sub_id: str):
    return subscriptions.pause(sub_id)


@app.post("/api/plus/{sub_id}/resume")
def plus_resume(sub_id: str):
    return subscriptions.resume(sub_id)


# ---------- seller health ----------

@app.get("/api/sellers")
def sellers():
    out = []
    for s in db.all("SELECT id FROM sellers ORDER BY completed_sales DESC"):
        m = health.metrics(s["id"])
        m["series"] = None
        m["open_cases"] = db.one("SELECT COUNT(*) AS n FROM issues i JOIN orders o ON o.id = i.order_id "
                                 "WHERE o.seller_id = ? AND i.status = 'ESCALATED'", (s["id"],))["n"]
        out.append(m)
    return out


@app.get("/api/sellers/{seller_id}/health")
def seller_health(seller_id: str):
    m = health.metrics(seller_id)
    if not m:
        raise orders.OrderError("seller not found", 404)
    return m


@app.get("/api/sellers/{seller_id}/explain")
def seller_explain(seller_id: str):
    return health.explain(seller_id)


# ---------- ledger ----------

@app.get("/api/ledger")
def get_ledger(limit: int = 200):
    return {"events": ledger.recent(limit), "verify": ledger.verify()}


@app.post("/api/ledger/tamper")
def tamper():
    """Demo only: silently edit one past record so 'Verify' can show the chain detecting it."""
    _demo_only()
    row = db.one("SELECT seq, data_json FROM events WHERE type LIKE 'payment.%' OR type LIKE 'payout.%' "
                 "ORDER BY seq DESC LIMIT 1") or db.one("SELECT seq, data_json FROM events ORDER BY seq LIMIT 1")
    if not row:
        raise orders.OrderError("ledger is empty", 404)
    db.run("UPDATE events SET data_json = ? WHERE seq = ?", (row["data_json"].replace('"', "'", 2) + " ", row["seq"]))
    return {"tampered_seq": row["seq"], "verify": ledger.verify()}


@app.post("/api/admin/reset")
def reset():
    _demo_only()
    seed.run(force=True)
    return {"ok": True}


# ---------- frontend ----------

app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")
