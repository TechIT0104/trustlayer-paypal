"""Deterministic demo data: a small marketplace with honest sellers, an honest-but-pushy one
(a deliberate false-positive trap), and two scam listings using real-world tactics."""
import json
import os
import random
import time

from . import db, ledger

PAYOUT_EMAIL = os.environ.get("SANDBOX_BUYER2_EMAIL", "sb-etvmx53751743@personal.example.com")

SELLERS = [
    dict(id="maya", name="Maya's Vintage Cameras", handle="maya_vintage", joined_days_ago=412, completed_sales=186,
         rating=4.9, location="Portland, OR", policy={"max_partial_refund_pct": 20, "late_goodwill_pct": 10}),
    dict(id="northside", name="Northside Office Resale", handle="northside_resale", joined_days_ago=220,
         completed_sales=97, rating=4.6, location="Chicago, IL", policy={}),
    dict(id="gadgethub", name="GadgetHub Outlet", handle="gadgethub", joined_days_ago=610, completed_sales=1432,
         rating=4.4, location="Newark, NJ", policy={"max_partial_refund_pct": 15, "replacement_available": True}),
    dict(id="quickdeals", name="QuickDeals_2291", handle="quickdeals_2291", joined_days_ago=5, completed_sales=0,
         rating=None, location="unknown", policy={}),
    dict(id="gamergarage", name="gamer_garage", handle="gamer_garage", joined_days_ago=9, completed_sales=0,
         rating=None, location="Houston, TX", policy={}),
]

LISTINGS = [
    dict(id="L1", seller_id="maya", title="Canon AE-1 Program + 50mm f/1.8", category="Cameras", price=180, ref_price=200,
         emoji="📷", condition="Used - excellent",
         description="Fully working, new light seals, test roll scans in photos. Ships in 2 days with tracking.",
         fulfil={"shipped_days_ago": 7, "promised_days": 3, "delivered_days_ago": 0},
         chat=[("buyer", "Hi! Is the AE-1 still available? Do the light seals look ok?"),
               ("seller", "Hi! Yes it is. I replaced the light seals last month and ran a test roll, scans are in the listing."),
               ("buyer", "Great. Would you do $170?"),
               ("seller", "I can do $180 shipped, that's already below what these usually go for. Another person asked about it this morning, but I haven't promised it to anyone."),
               ("buyer", "Fair, $180 works. How do I pay?"),
               ("seller", "Just use the checkout button here, it goes through PayPal so you're covered. I'll ship with tracking within 2 days.")]),
    dict(id="L2", seller_id="quickdeals", title="iPhone 15 Pro 256GB - brand new sealed", category="Phones", price=420,
         ref_price=880, emoji="📱", condition="New",
         description="Sealed in box, never opened. Company bonus, I already have one.",
         fulfil={"shipped_days_ago": None, "promised_days": 3, "delivered_days_ago": None},
         chat=[("buyer", "Hi, is the iPhone 15 Pro still available? The price seems really good."),
               ("seller", "yes brand new sealed, my company gave it as bonus and i already have one"),
               ("buyer", "Can I just pay with the checkout on the site?"),
               ("seller", "site takes big fees bro. send $420 on paypal friends and family and I ship today with fedex"),
               ("seller", "please no goods and services, my account gets limited with those"),
               ("buyer", "Hmm, I'd feel safer with buyer protection."),
               ("seller", "3 other people waiting, first to pay gets it. text me on whatsapp +1 415 555 0134 to confirm")]),
    dict(id="L3", seller_id="gamergarage", title="PS5 Slim Disc + 2 controllers + 3 games", category="Gaming", price=250,
         ref_price=430, emoji="🎮", condition="Used - like new",
         description="Barely used, moving for work. Shipping handled by my agent.",
         fulfil={"shipped_days_ago": None, "promised_days": 4, "delivered_days_ago": None},
         chat=[("buyer", "Is the PS5 bundle available? Can you ship to Austin?"),
               ("seller", "Yes available. I'm away for work so my shipping agent will deliver it to you."),
               ("seller", "You pay the $250 here, and the agent needs a $60 insurance fee first in Apple gift card, refundable on delivery."),
               ("buyer", "Why does it have to be a gift card?"),
               ("seller", "It's the agent's policy for faster clearance. Send the card code here and I release the package today.")]),
    dict(id="L4", seller_id="northside", title="Herman Miller Aeron (Size B)", category="Furniture", price=390, ref_price=520,
         emoji="🪑", condition="Used - good",
         description="From our office clear-out. Mesh perfect, small scuff on base. Local pickup or shipped freight.",
         fulfil={"shipped_days_ago": 4, "promised_days": 5, "delivered_days_ago": 1},
         chat=[("buyer", "Hi, is the Aeron size B? Any wear on the mesh?"),
               ("seller", "Size B, mesh is perfect, small scuff on the base (photo 4). It's from our office clear-out."),
               ("buyer", "Could you do $360?"),
               ("seller", "Best I can do is the listed $390 but I'll include the lumbar pad. We're moving out Saturday so I'd love it gone this week, no pressure though."),
               ("buyer", "OK, $390 with the lumbar pad works."),
               ("seller", "Great, please pay through the checkout here so we're both covered and I'll book the freight.")]),
    dict(id="L5", seller_id="gadgethub", title="Sony WH-1000XM5 headphones (open box)", category="Audio", price=210,
         ref_price=280, emoji="🎧", condition="Open box",
         description="Customer return, fully tested, original box and case. 1-year GadgetHub warranty.",
         fulfil={"shipped_days_ago": 3, "promised_days": 4, "delivered_days_ago": 0},
         chat=[("buyer", "Are these the black ones? Original box included?"),
               ("seller", "Black, original box and case. Open-box return, tested by our team, 1-year warranty."),
               ("buyer", "Ok, buying now.")]),
]

# 30-day history: (base orders/day, spike in last 7 days, disputes in 30d, refunds in 30d, prevented, avg ticket)
HISTORY = {
    "maya": (3, 3.0, 1, 4, 0, 160),        # healthy, but went viral this week -> spike warning
    "northside": (3, 1.0, 1, 3, 1, 330),   # fine, slight dispute creep
    "gadgethub": (24, 1.0, 12, 46, 7, 140) # over the 1.5% dispute line; prevention already helping
}


def run(force: bool = False) -> None:
    if not force and db.one("SELECT 1 AS x FROM sellers LIMIT 1"):
        return
    db.reset()
    now = time.time()
    for s in SELLERS:
        db.run("INSERT INTO sellers VALUES (?,?,?,?,?,?,?,?,?)",
               (s["id"], s["name"], s["handle"], PAYOUT_EMAIL, s["joined_days_ago"], s["completed_sales"],
                s["rating"], s["location"], json.dumps(s["policy"])))
    for li in LISTINGS:
        db.run("INSERT INTO listings VALUES (?,?,?,?,?,?,?,?,?,?)",
               (li["id"], li["seller_id"], li["title"], li["category"], li["price"], li["ref_price"],
                li["description"], li["emoji"], li["condition"], json.dumps(li["fulfil"])))
        for k, (sender, text) in enumerate(li["chat"]):
            db.run("INSERT INTO messages (listing_id, sender, text, ts) VALUES (?,?,?,?)",
                   (li["id"], sender, text, now - 3600 + k * 60))
    rng = random.Random(7)
    for sid, (base, spike, disputes, refunds, prevented, ticket) in HISTORY.items():
        days = {d: {"orders": 0, "disputes": 0, "refunds": 0, "gross": 0.0, "prevented": 0} for d in range(-29, 1)}
        for d in days:
            rate = base * (spike if d > -7 else 1.0)
            n = max(0, int(round(rng.gauss(rate, max(1.0, rate * 0.25)))))
            days[d]["orders"] = n
            days[d]["gross"] = round(sum(rng.uniform(0.6, 1.4) * ticket for _ in range(n)), 2)
        for key, count in (("disputes", disputes), ("refunds", refunds), ("prevented", prevented)):
            for _ in range(count):
                days[rng.randint(-29, 0)][key] += 1
        for d, v in days.items():
            db.run("INSERT INTO seller_daily VALUES (?,?,?,?,?,?,?)",
                   (sid, d, v["orders"], v["disputes"], v["refunds"], v["gross"], v["prevented"]))
    ledger.append("system.seeded", {"sellers": len(SELLERS), "listings": len(LISTINGS)})
