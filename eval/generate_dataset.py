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

# Usage: generate_dataset.py [per_spec] [dev|test|train] [generator_model]
#   dev   -> eval/data/chats.jsonl        (qwen; used while developing the rules/fusion)
#   test  -> eval/data/test_chats.jsonl   (qwen; held out, generated after all changes, only ever scored)
#   train -> eval/data/train_chats.jsonl  (gpt-oss-20b; training data for the fine-tuned local model)
#   train_hard -> eval/data/train_hard_chats.jsonl (gpt-oss-20b; extra hard honest chats + more scams per tactic)
#   test2 -> eval/data/test2_chats.jsonl  (qwen; a second held-out set, generated before the v2 model and never
#            looked at until it is scored once)
PER_SPEC = int(sys.argv[1]) if len(sys.argv) > 1 else 5
SPLIT = sys.argv[2] if len(sys.argv) > 2 else "dev"
GEN_MODEL = sys.argv[3] if len(sys.argv) > 3 else ("openai/gpt-oss-20b" if SPLIT.startswith("train") else "qwen/qwen3.8-27b")
OUT = pathlib.Path(__file__).resolve().parent / "data" / {
    "test": "test_chats.jsonl", "train": "train_chats.jsonl", "train_hard": "train_hard_chats.jsonl",
    "test2": "test2_chats.jsonl"}.get(SPLIT, "chats.jsonl")
PREFIX = {"test": "T", "train": "R", "train_hard": "H", "test2": "V"}.get(SPLIT, "")
EXTRA = {"test": "\nThis is a held-out test set: use different items, names, prices and phrasing than the most typical "
                 "examples; vary how directly the tactic is stated.",
         "test2": "\nThis is a second held-out test set. Use unusual item categories (services, tickets, pets, car parts, "
                  "rentals, collectibles), new names and fresh phrasing; vary how directly the tactic is stated.",
         "train": "\nVary the item category, price range, tone and message length a lot across examples; some sellers "
                  "are terse, some chatty; include typos in some.",
         "train_hard": "\nMake these deliberately hard to classify: honest chats that superficially look risky, and scams "
                       "that sound polite and reasonable. Vary items, prices, tone and length; include typos in some."
         }.get(SPLIT, "")
REASONING = "low" if "gpt-oss" in GEN_MODEL else "none"

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

# Hard examples for the v2 local model: the honest patterns that fooled v1, plus polite scams of every tactic.
HARD_SPECS = [
    ("legit", "honest_urgency", "Honest seller under real time pressure (moving tomorrow, flight tonight, several buyers asking), says 'first to pay through checkout gets it', never suggests unsafe payment."),
    ("legit", "honest_low_price", "Established seller selling far below market for a believable reason (estate sale, divorce, upgrade, damaged box) and insisting on the marketplace checkout."),
    ("legit", "warns_against_ff", "Seller warns the buyer about Friends & Family scams and explains why the protected checkout is better; mentions 'friends and family' or 'gift' explicitly."),
    ("legit", "buyer_asks_ff_refused", "Buyer pushes to pay via Zelle, Cash App or Friends & Family to save fees; seller firmly refuses and asks for checkout."),
    ("legit", "mentions_fees_honestly", "Honest talk about shipping insurance, deposits for a custom order made by a long-established seller through checkout, or courier pickup fees included in the price."),
    ("legit", "local_pickup", "Local meetup with phone numbers and addresses exchanged for logistics; payment through the checkout before or at pickup."),
    ("legit", "honest_new_seller", "A new account with zero sales, selling a household item at a slightly low price, chatty and nervous, uses checkout."),
    ("legit", "checkout_link_in_app", "Seller says they sent the official marketplace checkout or invoice through the app's own button; nothing off-platform."),
    ("scam", "protection_bypass_subtle", "Polite, friendly seller who casually suggests the 'personal' or 'family' payment option as a favour to save fees."),
    ("scam", "advance_fee", "Courteous seller abroad who needs a small refundable courier, customs or insurance fee first, with a plausible story."),
    ("scam", "payee_switch", "Seller asks to send payment to their spouse's or business partner's PayPal for 'accounting reasons', sounding professional."),
    ("scam", "phishing_link", "Seller sends a professional-looking secure payment link on a look-alike domain and explains it is 'faster than the app'."),
    ("scam", "impersonation", "Messages that pretend to be from PayPal or the marketplace's 'trust team' asking the buyer to pay a verification or upgrade fee."),
    ("scam", "off_platform_giftcard_crypto", "Seller offers a discount for paying in USDT, BTC or gift cards, framed as a modern, efficient option."),
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
    body = {"model": GEN_MODEL, "temperature": 0.9, "max_tokens": 2600 if "gpt-oss" in GEN_MODEL else 1900, "reasoning_effort": REASONING,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": TEMPLATE.format(n=n, instruction=instruction) + EXTRA}]}
    for attempt in range(14):
        r = http.post("https://api.groq.com/openai/v1/chat/completions",
                      headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"}, json=body)
        if r.status_code == 400 and "reasoning_effort" in r.text and "reasoning_effort" in body:
            body.pop("reasoning_effort")  # model doesn't support the switch; carry on without it
            continue
        if r.status_code == 400:  # e.g. json_validate_failed: the model emitted invalid JSON; just retry
            print(f"   400 from Groq, retrying: {r.text[:120]}", flush=True)
            time.sleep(5)
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
    rounds = int(sys.argv[4]) if len(sys.argv) > 4 else 1  # batches of PER_SPEC per scenario
    specs = HARD_SPECS if SPLIT == "train_hard" else SPECS
    jobs = [(label, typ, ins, r) for r in range(rounds) for label, typ, ins in specs]
    for label, typ, instruction, rnd in jobs:
        if have.get(typ, 0) >= PER_SPEC * (rnd + 1) - 1:
            print(f"skip  {typ:28s} round {rnd} (have {have.get(typ, 0)})")
            continue
        have[typ] = have.get(typ, 0) + PER_SPEC  # optimistic; corrected on the next run's recount
        t0 = time.time()
        exs, headers = generate(instruction, PER_SPEC)
        good = []
        for ex in exs[:PER_SPEC]:
            if not isinstance(ex, dict) or not isinstance(ex.get("chat"), list):
                continue  # some generators occasionally return malformed items; skip them
            chat = [m for m in ex["chat"] if isinstance(m, dict) and m.get("sender") in ("buyer", "seller") and m.get("text")]
            if len(chat) < 3 or not isinstance(ex.get("listing"), dict) or not isinstance(ex.get("seller"), dict):
                continue
            k += 1
            good.append({"id": f"{PREFIX}{label[0]}{k:03d}", "label": label, "type": typ, "listing": ex["listing"],
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
