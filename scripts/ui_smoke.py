"""Headless UI smoke test: loads each page, records console errors, saves screenshots.

Usage: python scripts/ui_smoke.py [base_url] [out_dir]
"""
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

PAGES = [("market", "#/"), ("listing_scam", "#/listing/L2"), ("sellers", "#/sellers"),
         ("seller_gadgethub", "#/sellers/gadgethub"), ("orders", "#/orders"), ("ledger", "#/ledger")]

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    pg.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
    for name, frag in PAGES:
        pg.goto(f"{BASE}/{frag}")
        pg.wait_for_timeout(2500 if "seller" in name else 1200)
        if name == "listing_scam":
            pg.get_by_role("button", name="Continue to pay").click()
            pg.wait_for_selector(".verdict", timeout=60000)
            pg.wait_for_timeout(600)
        pg.screenshot(path=f"{OUT}/{name}.png", full_page=True)
        print(f"{name:18s} ok  title={pg.title()!r}  h1={pg.locator('h1').first.inner_text()[:60]!r}")
    # mobile check: no horizontal scroll
    m = b.new_page(viewport={"width": 390, "height": 844})
    m.goto(f"{BASE}/#/listing/L1")
    m.wait_for_timeout(1200)
    sw = m.evaluate("document.documentElement.scrollWidth")
    print("mobile scrollWidth:", sw, "(viewport 390)")
    m.screenshot(path=f"{OUT}/mobile_listing.png", full_page=True)
    b.close()
print("console errors/warnings:", len(errors))
for e in errors[:20]:
    print("  ", e[:300])
