"""End-to-end test of the real PayPal sandbox money flows through the TrustLayer API.

A headless browser plays the buyer and approves each PayPal order with the sandbox buyer
account from .env. Everything else goes through our API exactly as the UI does.

  Flow A (honest):  L1 -> CLEAR -> approve -> HELD -> resolution agent offer -> accept
                    (partial capture) -> received -> seller payout
  Flow B (scam):    L2 -> PAUSE -> acknowledged + trusted contact -> approve -> PAUSED
                    -> trusted contact says "scam" -> authorization voided

Usage: python scripts/e2e_paypal.py [base_url]
"""
import os
import pathlib
import sys
import time

import httpx
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
BUYER, PWD = os.environ["SANDBOX_BUYER_EMAIL"], os.environ["SANDBOX_BUYER_PASSWORD"]
SHOTS = pathlib.Path(os.environ.get("E2E_SHOTS", ROOT / "scripts" / "e2e_shots"))
SHOTS.mkdir(parents=True, exist_ok=True)
api = httpx.Client(base_url=BASE, timeout=120)


def call(method: str, path: str, **kw) -> dict:
    r = api.request(method, path, **kw)
    if r.status_code >= 400:
        raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json()


def approve(page, url: str, tag: str) -> None:
    page.goto(url)
    page.wait_for_load_state("domcontentloaded")
    t0 = time.time()
    def tap(selector_or_locator) -> None:
        # PayPal shows a transitional spinner overlay; never block on it, just try again next loop
        try:
            if isinstance(selector_or_locator, str):
                page.click(selector_or_locator, timeout=4000)
            else:
                selector_or_locator.click(timeout=4000)
        except Exception:
            pass

    while time.time() - t0 < 120:
        if page.locator("#email").is_visible() and not page.locator("#password").is_visible():
            if page.input_value("#email") != BUYER:
                page.fill("#email", BUYER)
            if page.locator("#btnNext").is_visible():
                tap("#btnNext")
                page.wait_for_timeout(2500)
        if page.locator("#password").is_visible():
            page.fill("#password", PWD)
            tap("#btnLogin")
            page.wait_for_timeout(4000)
        for label in ("Continue", "Continue to Review Order", "Pay Now", "Complete Purchase", "Agree & Continue", "Agree and Continue"):
            btn = page.get_by_role("button", name=label, exact=True)
            if btn.count() and btn.first.is_visible():
                tap(btn.first)
                page.wait_for_timeout(3500)
                break
        if "example.com" in page.url:
            print(f"   [{tag}] buyer approved in PayPal ({time.time() - t0:.0f}s)")
            return
        page.wait_for_timeout(1500)
    page.screenshot(path=str(SHOTS / f"{tag}_stuck.png"), full_page=True)
    raise SystemExit(f"[{tag}] approval did not finish; screenshot saved; url={page.url}")


def main() -> None:
    call("POST", "/api/admin/reset")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        print("Flow A: honest purchase with an AI-settled late delivery")
        risk = call("POST", "/api/assess", json={"listing_id": "L1"})
        print("   verdict:", risk["verdict"], risk["score"])
        o = call("POST", "/api/orders", json={"listing_id": "L1"})
        approve(page, o["approve_url"], "A")
        order = call("POST", f"/api/orders/{o['order_id']}/authorize")
        print("   status:", order["status"], "| authorization:", order["authorization_id"], "| seller protection:", order["seller_protection"])
        issue = call("POST", f"/api/orders/{o['order_id']}/issue",
                     json={"text": "It finally arrived but 4 days late, I needed it for a trip. Not happy."})
        last = issue["transcript"][-1]
        print("   agent:", last["text"][:160].encode("ascii", "replace").decode())
        print("   offer:", last["offer"])
        if last["offer"]["type"] in ("partial_refund", "full_refund"):
            settled = call("POST", f"/api/issues/{issue['id']}/accept")
            print("   settled:", settled["outcome"]["method"], "| order status:", settled["order"]["status"])
        done = call("POST", f"/api/orders/{o['order_id']}/received")
        print("   final:", done["status"], "| captured", done["captured_amount"], "| payout", done["payout_amount"],
              "batch", done["payout_batch_id"], "| fee", done["fee"])

        print("Flow B: scam listing, paused, trusted contact stops it")
        risk = call("POST", "/api/assess", json={"listing_id": "L2"})
        print("   verdict:", risk["verdict"], risk["score"], (risk.get("ai") or {}).get("scam_type"))
        o = call("POST", "/api/orders", json={"listing_id": "L2", "acknowledged": True, "trusted_contact": "Mom"})
        approve(page, o["approve_url"], "B")
        order = call("POST", f"/api/orders/{o['order_id']}/authorize")
        print("   status:", order["status"], "| seconds left:", order["seconds_left"])
        token = call("GET", f"/api/orders/{o['order_id']}/contact-link")["token"]
        res = call("POST", f"/api/contact/{token}", json={"verdict": "scam"})
        print("   after contact verdict:", res["order"]["status"])
        browser.close()
    v = call("GET", "/api/ledger")["verify"]
    print("Ledger:", "intact" if v["ok"] else "BROKEN", v["count"], "records")


if __name__ == "__main__":
    main()
