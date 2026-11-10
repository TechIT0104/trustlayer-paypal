"""Headless UI smoke test: loads each page, records console errors, saves screenshots.

Usage: python scripts/ui_smoke.py [base_url] [out_dir]
"""
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = sys.argv[2] if len(sys.argv) > 2 else "."

for _ in range(40):
    try:
        urllib.request.urlopen(BASE + "/api/config", timeout=2)
        break
    except Exception:
        time.sleep(0.5)

orders = json.load(urllib.request.urlopen(BASE + "/api/orders"))
pages = [("market", "#/", None), ("listing_clear", "#/listing/L1", "check"), ("listing_scam", "#/listing/L2", "check"),
         ("sellers", "#/sellers", None), ("seller_gadgethub", "#/sellers/gadgethub", None),
         ("orders", "#/orders", None), ("subscriptions", "#/subscriptions", None), ("seller_maya_kit", "#/sellers/maya", None), ("ledger", "#/ledger", None)]
for o in orders[:2]:
    pages.append((f"order_{o['status'].lower()}", f"#/order/{o['id']}", None))

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1366, "height": 900})
    errors = []
    pg.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
    for name, frag, action in pages:
        pg.goto(f"{BASE}/{frag}")
        pg.wait_for_timeout(2500 if "seller" in name else 1300)
        if action == "check":
            pg.get_by_role("button", name="Continue to payment").click()
            pg.wait_for_selector(".modal, .status-card", timeout=60000)
            pg.wait_for_timeout(1500)
        pg.screenshot(path=f"{OUT}/{name}.png", full_page=True)
        print(f"{name:18s} ok  h1={pg.locator('h1, h2').first.inner_text()[:60]!r}")
    m = b.new_page(viewport={"width": 390, "height": 844})
    for name, frag in (("mobile_market", "#/"), ("mobile_listing", "#/listing/L1")):
        m.goto(f"{BASE}/{frag}")
        m.wait_for_timeout(1300)
        print(f"{name:18s} scrollWidth={m.evaluate('document.documentElement.scrollWidth')} (viewport 390)")
        m.screenshot(path=f"{OUT}/{name}.png", full_page=True)
    b.close()
print("console errors/warnings:", len(errors))
for e in errors[:20]:
    print("  ", e[:300])
