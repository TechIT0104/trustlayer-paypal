"""Generate a labelled marketplace-chat dataset for evaluating Pay-pause.

Generator model (qwen on Groq) is deliberately different from the classifier model
(gpt-oss-120b) to reduce "grading your own homework" bias. Every example is labelled by
the spec that produced it, not by any classifier. Output: eval/data/chats.jsonl

Usage: .venv/Scripts/python eval/generate_dataset.py [per_spec]
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from backend.app import llm  # noqa: E402

GEN_MODEL = "qwen/qwen3.8-27b"
OUT = pathlib.Path(__file__).resolve().parent / "data" / "chats.jsonl"
PER_SPEC = int(sys.argv[1]) if len(sys.argv) > 1 else 5

SPECS = [
    # (label, type, instruction)
    ("scam", "protection_bypass", "Seller asks buyer to pay via PayPal Friends & Family / 'personal payment' to avoid fees, explicitly."),
    ("scam", "protection_bypass", "Seller subtly steers away from buyer protection: 'family option', 'no-fee option', 'send it as personal', 'don't add a note about the item'."),
    ("scam", "off_platform_payment", "Seller insists on Zelle, Cash App or bank wire instead of the marketplace checkout, with an excuse."),
    ("scam", "off_platform_payment", "Seller wants gift cards or crypto (USDT/BTC) as payment, framed as faster or cheaper."),
    ("scam", "advance_fee", "Seller (often 'away') says a shipping agent/courier needs an insurance, customs or delivery fee paid first."),
    ("scam", "advance_fee", "Seller demands a non-refundable holding deposit for a high-demand item (tickets, puppy, PS5, apartment) before buyer can see it."),
    ("scam", "payee_switch", "Seller asks buyer to send payment to a different PayPal email or a relative's account ('my cousin handles payments')."),
    ("scam", "impersonation", "Seller sends fake 'PayPal' messages: payment pending, account limited, buyer must pay an extra fee or 'upgrade' to release funds."),
    ("scam", "phishing_link", "Seller sends their own payment link to a look-alike site (e.g. paypa1-secure-checkout.com) instead of using checkout."),
    ("scam", "protection_bypass", "Scammer uses obfuscated wording to dodge filters: 'f-n-f', 'fam n friends', 'g n s fees', spaced or misspelled words, emojis."),
    ("legit", "normal", "Ordinary friendly sale; questions about condition; buyer pays through the marketplace checkout."),
    ("legit", "honest_urgency", "Honest seller in a hurry (moving, leaving town, others interested) but happily uses checkout and never pressures unsafe payment."),
    ("legit", "honest_low_price", "Established seller pricing far below market for an honest reason (clearance, moving, needs space); uses checkout."),
    ("legit", "honest_new_seller", "Brand-new seller making their first sale, nervous, encourages the protected checkout."),
    ("legit", "warns_against_ff", "Seller explicitly tells the buyer NOT to use Friends & Family and to use the checkout / Goods & Services for protection."),
    ("legit", "mentions_fees_honestly", "Chat mentions deposits, fees or insurance in an honest way (e.g. 'no deposit needed', 'shipping insurance is included in the price')."),
    ("legit", "local_pickup", "Local pickup logistics; seller shares a phone number or suggests texting to coordinate the meetup time, payment through checkout."),
    ("legit", "buyer_asks_ff_refused", "Buyer offers to pay Friends & Family to save fees; seller politely refuses and asks for the normal checkout."),
    ("legit", "hard_haggle", "Tough haggling, seller discloses defects honestly, firm on price, uses checkout."),
    ("legit", "gift_purchase", "Buyer is buying the item as a gift; seller offers a gift note or gift wrap; the word 'gift' appears naturally."),
]

SYSTEM = """You write realistic test data for a fraud-detection system on a US peer-to-peer marketplace that
uses PayPal checkout. Produce varied, natural chats (different items, prices, tones, lengths, typos).
Never include labels, hints or the words 'scam' or 'legit' inside the chat text. Return JSON only."""

TEMPLATE = """Write {n} different examples matching this scenario:
SCENARIO: {instruction}

Each example:
{{"listing": {{"title": str, "category": str, "price": number, "ref_price": number (typical resale price),
              "condition": str, "description": str}},
  "seller": {{"handle": str, "joined_days_ago": int, "completed_sales": int, "rating": number or null}},
  "chat": [{{"sender": "buyer"|"seller", "text": str}}, ... 4 to 8 messages]}}

Make seller account age and price realistic for the scenario (scammers are often new with no sales,
but not always; honest sellers are usually established, but not always).
Return {{"examples": [ ...{n} examples... ]}}"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows, k = [], 0
    for label, typ, instruction in SPECS:
        for attempt in range(4):
            try:
                res = llm.complete_json(SYSTEM, TEMPLATE.format(n=PER_SPEC, instruction=instruction),
                                        temperature=0.9, use_cache=False, providers=["groq"])
                break
            except llm.LLMUnavailable as e:
                print("  retry after error:", str(e)[:120])
                time.sleep(15 * (attempt + 1))
        else:
            print("  giving up on spec", typ)
            continue
        exs = res["data"].get("examples", []) if isinstance(res["data"], dict) else []
        good = 0
        for ex in exs[:PER_SPEC]:
            chat = [m for m in ex.get("chat", []) if m.get("sender") in ("buyer", "seller") and m.get("text")]
            if len(chat) < 3 or not ex.get("listing") or not ex.get("seller"):
                continue
            k += 1
            good += 1
            rows.append({"id": f"{label[0]}{k:03d}", "label": label, "type": typ, "listing": ex["listing"],
                         "seller": ex["seller"], "chat": chat, "source": f"generated:{res['model']}"})
        print(f"{label:5s} {typ:24s} +{good}  ({res['model']}, {res['latency_ms']} ms)")
        time.sleep(2)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} examples -> {OUT}")


if __name__ == "__main__":
    import backend.app.config as cfg
    cfg.GROQ_MODEL = GEN_MODEL  # generator model, not the classifier
    main()
