# TrustLayer — a trust layer for both sides of a PayPal payment

**Pay-pause scam interception · pre-dispute resolution · seller account health**, built on PayPal's
Orders v2, Payments v2 and Payouts APIs with an AI layer whose every money decision is bounded by code.

> Built for the **PayPal AI Hackathon** (Nov 2026). Runs entirely on the free PayPal **sandbox**.

---

## The problem

PayPal's biggest complaints aren't about moving money. They're about trust breaking down around it:

| Who | Pain (what the research says) | What PayPal does today |
|---|---|---|
| **Buyers** | Purchase scams are **71%** of UK authorised-push-payment fraud cases (£576M lost in 2025, +19%). If you're *tricked* into sending money (e.g. "pay me Friends & Family"), it isn't "unauthorized", so it's usually not refunded. | No visible in-the-moment intervention. Revolut cut card-scam losses ~30% with an AI "break the spell" flow; PayPal has no equivalent. |
| **Sellers** | **43.8%** of chargebacks are friendly fraud, and **85%** of consumers who file one say bad service pushed them to it. Card networks flag merchants above a **1.5%** dispute ratio (Visa VAMP, 2026). | Disputes are fought *after* they're filed. |
| **Sellers** | About 20% of PayPal reviews mention sudden holds or limitations with no warning and no explanation. | An opaque risk system. |

TrustLayer puts AI where those failures happen: **before** a scammed buyer's money moves, **before**
an unhappy buyer files a dispute, and **before** a seller's metrics trigger a hold.

## What it does

### 1. Pay-pause: scam interception before money moves
Every checkout is a PayPal **authorization** (`intent: AUTHORIZE`). The money is held, not taken. Before the buyer
even sees the PayPal button, TrustLayer reads the listing and the buyer–seller chat:

- **Rules layer** (explainable, no AI): Friends & Family requests, "no Goods & Services", gift cards/crypto/Zelle,
  up-front "courier fees", payee switches, fake "PayPal support", off-platform contact, pressure,
  price far below market, brand-new seller.
- **LLM layer**: names the scam *tactic* and must cite **exact quotes with chat line numbers**.
- **Grounding check**: every quote is verified against the real chat. Made-up "evidence" is thrown out, and an
  LLM-only score without grounded evidence can't trigger a pause on its own. (False positives and invented
  evidence are the documented failure modes of LLM scam detectors, e.g. arXiv 2502.03964, 2606.01475.)

Verdict: **CLEAR** → normal protected checkout · **CAUTION** → warning · **PAUSE** → a "break the spell"
screen that names the tactic in plain words, highlights the exact chat lines, and makes *"Don't pay"* the
big button. If the buyer still insists, the authorization goes into a **cooling-off hold** and a **trusted contact**
gets a link to double-check. Either can **void** the hold, so the buyer is never charged.

### 2. Pre-dispute resolution agent
After purchase, an unhappy buyer talks to an AI assistant acting for the seller, *before* anyone opens a PayPal
dispute. The LLM classifies the issue (late, damaged, not as described…), gauges dispute risk and proposes an outcome.
**Code enforces the seller's policy**: refund caps, when a full refund is allowed, no refunds for change of mind.
The model can't promise money the seller didn't authorize. One click executes it on PayPal:
- order still on hold → **capture the reduced amount** (the rest of the hold is released; nothing to refund, no fee on it)
- already captured → **partial refund** via the Refunds API

Anything outside the assistant's authority (a full refund on a delivered item, a severe defect) is **escalated to
the seller's inbox**, where the seller sends a refund of their choosing or declines. Every path ends in a PayPal call
or an explicit human decision, never a dead end.

### 3. Seller account health
A dashboard of the public signals that commonly trigger holds and reviews: dispute ratio vs the **1.5%** line,
refund rate, volume spikes vs the seller's own baseline, new-account velocity, scam pauses on their listings,
and Seller Protection coverage from real PayPal capture data. It shows **"dispute rate without TrustLayer's
early resolution"** and has the LLM explain it all in plain English with three next actions. It never claims
to know PayPal's internal risk model.

### Plus: a hash-chained audit ledger
Every PayPal call and every AI decision is written to an append-only, SHA-256 hash-chained ledger with the PayPal
IDs it produced (order, authorization, capture, refund, payout batch). Edit any record and verification names the break.

## How the money moves (real sandbox calls)

```
 Buyer ── chat ──▶ Pay-pause (rules + LLM + grounding) ──▶ CLEAR / CAUTION / PAUSE
                                                              │
   PayPal JS SDK (intent=authorize) ──▶ POST /v2/checkout/orders            (create, AUTHORIZE)
   buyer approves in PayPal          ──▶ POST /v2/checkout/orders/{id}/authorize   → HOLD
        │                                   PAUSE ⇒ cooling-off + trusted contact
        ├── scam / buyer cancels ───────▶ POST /v2/payments/authorizations/{id}/void   → $0 charged
        ├── problem ⇒ resolution agent ─▶ POST …/authorizations/{id}/capture (reduced, final)
        │                                 or POST /v2/payments/captures/{id}/refund (partial)
        └── delivered ──────────────────▶ POST …/authorizations/{id}/capture
                                          POST /v1/payments/payouts  → seller paid (minus platform fee)
```

Production details that are handled, not hand-waved:
- **Idempotency:** every state-changing call sends a `PayPal-Request-Id` derived from our order and action IDs, so retries
  and double clicks can never double-charge or double-pay. Payout batch IDs are tied to order IDs for the same reason.
- **Webhooks:** `POST /api/webhooks/paypal` verifies each event with PayPal's `verify-webhook-signature` API, drops
  duplicates (PayPal retries), and reconciles authorization voids, captures, refunds and payout item outcomes
  (`SUCCEEDED / UNCLAIMED / FAILED / RETURNED`). `scripts/register_webhook.py` registers it after deploy.
- **Payout reconciliation:** payout status is polled until PayPal reports a final state, even without webhooks.
- **Declined funding:** `INSTRUMENT_DECLINED` on authorize returns a restart signal, and the JS SDK calls `actions.restart()`.
- **Expired holds:** past PayPal's 3-day honor period, a capture that fails with `AUTHORIZATION_EXPIRED` is
  reauthorized and retried automatically.

## Evaluation (honest numbers)

<!-- EVAL:START -->
_Run `python eval/run_eval.py`; results land in `eval/results/summary.json` and [NUMBERS.md](NUMBERS.md)._
<!-- EVAL:END -->

## PayPal technology used

| PayPal capability | Where |
|---|---|
| **Orders v2**: create with `intent: AUTHORIZE`, authorize | every checkout ([backend/app/paypal.py](backend/app/paypal.py)) |
| **Payments v2**: capture (full / partial-final), void, refund, reauthorize | release, scam cancel, resolution settlements, expired holds |
| **Payouts v1**: create batch, get status | pay the seller after delivery, minus platform fee; reconcile the outcome |
| **Webhooks**: register, verify signature, consume events | [backend/app/webhooks.py](backend/app/webhooks.py) |
| **PayPal JS SDK** buttons (`intent=authorize`) | buyer approval in the browser, plus a redirect fallback |
| Seller Protection status from authorizations and captures | seller health dashboard |
| **PayPal AI Toolkit** (Claude Code plugin + sandbox MCP server) | used during development to inspect orders and test sandbox flows |

## AI tools used and how

| Tool / model | Used for | Guardrails |
|---|---|---|
| **Groq · `openai/gpt-oss-120b`** (primary) | scam tactic classification with cited evidence; resolution-agent turns; seller-health explanations | JSON-only outputs, temperature 0 for risk, grounded-quote verification, policy enforcement in code, hard timeouts |
| **Google Gemini · `gemini-flash-lite-latest`** | automatic fallback when Groq is rate-limited or down | same prompts and checks |
| **Ollama · `mistral`** (local, optional) | offline last-resort fallback | same |
| **Groq · `qwen/qwen3.8-27b`** | generating the labelled evaluation dataset (a *different* model from the classifier) | labels come from the generation spec, never from a classifier |
| **Claude Code (Anthropic)** with the PayPal AI Toolkit plugin | pair-programming the project | n/a |

## Run it locally (about 5 minutes)

Requirements: Python 3.11+, a free PayPal developer account, and a free Groq and/or Gemini key.

```bash
git clone <this repo> && cd <repo>
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env      # fill in PayPal sandbox app + AI keys (see comments inside)
python -m uvicorn backend.app.main:app --port 8000
```

Open **http://127.0.0.1:8000**. Demo data seeds itself on first start, and **Ledger → Reset demo** reseeds it.

**PayPal sandbox setup** (developer.paypal.com):
1. Sandbox → Accounts: make sure you have a **Business** account with country **United States** and a **Personal** (buyer) account.
2. Apps & Credentials → Sandbox → **Create App** (Merchant) **linked to that US business account**, and tick **Payouts** under Features.
3. Put the Client ID and Secret in `.env`. When the PayPal button opens, log in with the **personal** sandbox account.

### Tests
```bash
pip install -r backend/requirements-dev.txt
python -m pytest tests            # 43 offline tests: ledger, scam rules + grounding + fusion, refund policy,
                                  # every order path, webhooks, reauthorization, declined funding (fake PayPal + fake LLM)
python scripts/e2e_paypal.py      # real sandbox: approve → hold → AI settlement → capture → payout; and scam → pause → void
python scripts/ui_smoke.py        # headless: every page renders, no console errors, mobile layout
python eval/run_eval.py && python eval/report.py   # Pay-pause precision / recall / false-pause rate → NUMBERS.md
```
(The two browser scripts need `pip install playwright && playwright install chromium`.)

### Deploy (Render, free)
`render.yaml` is a ready Blueprint: New → Blueprint → this repo → fill the secret env vars. After the first deploy, run
`python scripts/register_webhook.py https://<your-app>.onrender.com` and set the printed `PAYPAL_WEBHOOK_ID`.

## Demo script (3 acts, under 3 minutes)
1. **The scam**: open the *iPhone 15 Pro* listing → **Continue to pay** → Pay-pause flags Friends & Family + "no G&S" and highlights the exact chat lines → **Don't pay**. Or insist, add a trusted contact, approve in PayPal, and watch the **cooling-off countdown**; the contact clicks **"This looks like a scam"** and the **hold is voided**.
2. **The honest problem**: buy the *Canon AE-1* (CLEAR) → approve → on the order page: *"It arrived 4 days late and I missed my trip"* → the agent offers $18 within policy → **Accept** → PayPal captures $162 and releases $18 → **Item received** → seller paid by Payouts.
3. **The seller's view**: *Seller health → GadgetHub*: 1.59% dispute rate over the 1.5% line, "2.52% without early resolution", plain-English actions. **Ledger**: tamper with a record, then **Verify**.

## Honest limitations
- Sandbox only. A production version needs PayPal's platform/partner onboarding for multi-seller payouts, and real 24-hour cooling-off windows (the demo uses 2 minutes).
- The evaluation set is LLM-generated (by a different model) and labelled by scenario. It measures behaviour on realistic patterns, not real-world prevalence.
- The seller-health dashboard uses public signals, not PayPal's internal models; demo history is synthetic and seeded.
- The trusted-contact link is shown in-app; a production version would send it by SMS or email.
- There is no login: one demo buyer, and the seller inbox is reachable from the seller-health page. Demo-only endpoints
  (reset, tamper simulation) are disabled with `DEMO_MODE=false`.

## Research and sources that shaped the design
- *Counter-Scam: LLM chain-of-response system* (arXiv 2606.01475): LLMs confuse scam types, which motivates tactic naming plus grounded evidence.
- *LLM-based real-time detection of phone scams* (arXiv 2502.03964): false positives on benign "payment" talk, which motivates corroborated pausing and the hard-negative test set.
- *SR-Fraud* (arXiv 2609.27287) and *SoK: Security of LLM agents in agentic commerce* (arXiv 2604.15367): payments are irreversible, so act *before* settlement.
- UK Finance / PSR APP-fraud statistics 2025; Chargebacks911 2026 field report (friendly fraud 43.8%); Visa VAMP 1.5% threshold (Apr 2026); Revolut's AI scam-intervention results.

## License
[MIT](LICENSE)
