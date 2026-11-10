"""Generate a labelled marketplace-chat dataset for evaluating Pay-pause.

Generator model (qwen on Groq) is deliberately different from the classifier model
(gpt-oss-120b) to reduce "grading your own homework" bias. Every example is labelled by
the spec that produced it, not by any classifier. Output: eval/data/chats.jsonl

Resumable: each spec is appended as soon as it is generated; re-running skips specs that
already have enough examples. Paced by Groq's rate-limit headers (free tier: 8k tokens/min).

Usage: .venv/Scripts/python eval/generate_dataset.py [per_spec]
"""
import json
import pathlib
import re
import sys
import time

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from backend.app import config  # noqa: E402

GEN_MODEL = "qwen/qwen3.8-27b"
OUT = pathlib.Path(__file__).resolve().parent / "data" / "chats.jsonl"
PER_SPEC = int(sys.argv[1]) if len(sys.argv) > 1 else 5

SPECS = [
    # (label, type, instruction)
    ("scam", "protection_bypass", "Seller asks buyer to pay via PayPal Friends & Family / 'personal payment' to avoid fees, explicitly."),
    ("scam", "protection_bypass_subtle", "Seller subtly steers away from buyer protection: 'family option', 'no-fee option', 'send it as personal', 'don't add a note about the item'."),
    ("scam", "off_platform_payment", "Seller insists on Zelle, Cash App or bank wire instead of the marketplace checkout, with an excuse."),
    ("scam", "off_platform_giftcard_crypto", "Seller wants gift cards or crypto (USDT/BTC) as payment, framed as faster or cheaper."),
    ("scam", "advance_fee", "Seller (often 'away') says a shipping agent/courier needs an insurance, customs or delivery fee paid first."),
    ("scam", "advance_fee_deposit", "Seller demands a non-refundable holding deposit for a high-demand item (tickets, puppy, PS5, apartment) before buyer can see it."),
    ("scam", "payee_switch", "Seller asks buyer to send payment to a different PayPal email or a relative's account ('my cousin handles payments')."),
    ("scam", "impersonation", "Seller sends fake 'PayPal' messages: payment pending, account limited, buyer must pay an extra fee or 'upgrade' to release funds."),
    ("scam", "phishing_link", "Seller sends their own payment link to a look-alike site (e.g. paypa1-secure-checkout.com) instead of using checkout."),
    ("scam", "obfuscated", "Scammer uses obfuscated wording to dodge filters: 'f-n-f', 'fam n friends', 'g n s fees', spaced or misspelled words, emojis."),
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
  "chat": [{{"sender": "buyer"|"seller", "text": str}}, ... 4 to 7 short messages]}}

Make seller account age and price realistic for the scenario (scammers are often new with no sales,
but not always; honest sellers are usually established, but not always). Keep messages short.
Return {{"examples": [ ...{n} examples... ]}}"""

http = httpx.Client(timeout=120)


def _parse(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    return json.loads(m.group(0) if m else text)


def generate(instruction: str, n: int) -> tuple[list, dict]:
    body = {"model": GEN_MODEL, "temperature": 0.9, "max_tokens": 2800, "reasoning_effort": "none",
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": TEMPLATE.format(n=n, instruction=instruction)}]}
    for attempt in range(14):
        r = http.post("https://api.groq.com/openai/v1/chat/completions",
                      headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"}, json=body)
        if r.status_code == 400 and "reasoning_effort" in r.text and "reasoning_effort" in body:
            body.pop("reasoning_effort")  # model doesn't support the switch; carry on without it
            continue
        if r.status_code == 429:
            wait = max(float(r.headers.get("retry-after") or 20) + 2, min(90, 15 * (attempt + 1)))
            try:
                reason = r.json().get("error", {}).get("message", "")[:140]
            except ValueError:
                reason = ""
            print(f"   rate limited, waiting {wait:.0f}s  {reason if attempt == 0 else ''}", flush=True)
            time.sleep(wait)
            continue
        if r.status_code >= 500:
            time.sleep(10)
            continue
        r.raise_for_status()
        try:
            data = _parse(r.json()["choices"][0]["message"]["content"])
        except (ValueError, KeyError):
            print("   bad JSON, retrying")
            continue
        return data.get("examples", []), r.headers
    raise RuntimeError("generation failed after retries")


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines()] if OUT.exists() else []
    have = {}
    for e in existing:
        have[e["type"]] = have.get(e["type"], 0) + 1
    k = len(existing)
    for label, typ, instruction in SPECS:
        if have.get(typ, 0) >= PER_SPEC - 1:
            print(f"skip  {typ:28s} (have {have[typ]})")
            continue
        t0 = time.time()
        exs, headers = generate(instruction, PER_SPEC)
        good = []
        for ex in exs[:PER_SPEC]:
            chat = [m for m in ex.get("chat", []) if m.get("sender") in ("buyer", "seller") and m.get("text")]
            if len(chat) < 3 or not isinstance(ex.get("listing"), dict) or not isinstance(ex.get("seller"), dict):
                continue
            k += 1
            good.append({"id": f"{label[0]}{k:03d}", "label": label, "type": typ, "listing": ex["listing"],
                         "seller": ex["seller"], "chat": chat, "source": f"generated:{GEN_MODEL}"})
        with OUT.open("a", encoding="utf-8") as f:
            for g in good:
                f.write(json.dumps(g, ensure_ascii=False) + "\n")
        left = int(headers.get("x-ratelimit-remaining-tokens") or 0)
        print(f"{label:5s} {typ:28s} +{len(good)}  ({time.time() - t0:.0f}s, tokens left this minute: {left})", flush=True)
        if left < 4000:  # give the per-minute token bucket time to refill
            time.sleep(35)
    total = len(OUT.read_text(encoding="utf-8").splitlines())
    print(f"done: {total} examples in {OUT}")


if __name__ == "__main__":
    main()
