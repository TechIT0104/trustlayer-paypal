# TrustLayer — a trust layer for both sides of a PayPal payment

**Pay-pause scam interception · pre-dispute resolution · seller account health**, built on PayPal's
Orders v2, Payments v2 and Payouts APIs with an AI layer whose every money decision is bounded by code.

> Built for the **PayPal AI Hackathon** (Nov 2026). Runs entirely on the free PayPal **sandbox**.

**Live demo: https://trustlayer-e5mz.onrender.com**. It's on Render's free tier, so the first load after idle can take
about 50 seconds. **Audit log → Reset demo** restores the starting data.

## Try it: PayPal sandbox buyer login

When the PayPal window opens (checkout or subscription), log in with this **sandbox test buyer**. It holds only
sandbox test money; it is not a real PayPal account and cannot move real funds.

| | |
|---|---|
| Email | `sb-hbn8w53835765@personal.example.com` |
| Password | `YFp3sUZ?` |

Start with the *iPhone 15 Pro* listing (a scam), then the *Canon AE-1* (an honest seller with a late parcel). The
Overview page lists six things to try. You can also use your own sandbox personal account from developer.paypal.com.

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
- **Fine-tuned local model**: a DistilBERT scam classifier we fine-tuned (starting from the public
  `BothBosu/distilbert-scam-classifier-v1.3`) on marketplace payment chats, exported to ONNX int8, and run on CPU
  inside the API in tens of milliseconds. It supports the other layers and never pauses alone (it can't cite evidence).
  When every hosted LLM is rate-limited or down, rules plus this model take over instead of rules alone.
  See [The fine-tuned local models](#the-fine-tuned-local-models).

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

### 4. TrustLayer Plus: subscriptions without the trap
About 7 in 10 US adults have been charged after forgetting a free trial, and 20+ states now require click-to-cancel.
Plus is a $4.99/month membership sold on **PayPal Subscriptions** that works the other way round:
- A real 7-day free trial (a `TRIAL` billing cycle on an ACTIVE PayPal plan). The server **verifies every subscription
  with PayPal** (`GET /v1/billing/subscriptions/{id}`, matching plan, ACTIVE/APPROVED) before granting anything.
- **Two days before the first charge**, an AI-written reminder says honestly whether the member has actually used it,
  and recommends cancelling if not. The date and amount are stated by code, never by the model.
- **Cancel in one confirmation**, always on the page. The assistant may offer a pause instead, but only if the member
  got real value; code decides that, and it can never block cancelling.
- Pause/resume (suspend/activate), and `BILLING.SUBSCRIPTION.*` / `PAYMENT.SALE.COMPLETED` webhooks keep state in sync.

**The same kit for sellers.** Any seller can sell their own membership (the demo seeds Maya's "Film Roll Club",
$12/month with a 14-day trial) from their seller page:
- **Terms review before launch:** the LLM flags dark patterns and vague promises in the seller's wording and suggests
  clearer text. **Code blocks the hard traps** (call/email to cancel, cancellation fees, minimum terms, "no cancellations"),
  including in the AI's own rewrite, and writes the price/renewal/trial/cancel disclosure every subscriber sees.
- Publishing creates a real PayPal catalog product and billing plan for that seller.
- A **subscriber dashboard** with trial/active status, "record a delivery", and a **forgotten-trial chargeback risk** flag
  (trial subscribers about to be charged who never received anything). That flag also appears in seller health,
  because those charges come back as disputes.

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
Held-out **test set v2: 80 marketplace chats** (40 scams, 40 honest; new item
categories and wording), generated before the final model was chosen and scored exactly once with the final configuration.

| Detector | Scams paused (recall) | Precision | Honest buyers wrongly paused | Honest buyers shown any warning | Scams with no warning at all | F1 |
|---|---|---|---|---|---|---|
| Rules only | 35% (14/40) | 93.3% | 2.5% (1/40) | 20% | 15% | 0.51 |
| LLM only (grounded quotes) | 97.5% (39/40) | 95.1% | 5% (2/40) | 7.5% | 2.5% | 0.96 |
| Local fine-tuned model only | 90% (36/40) | 80% | 22.5% (9/40) | 60% | 5% | 0.85 |
| Rules + local model (LLM outage mode) | 80% (32/40) | 91.4% | 7.5% (3/40) | 40% | 2.5% | 0.85 |
| **TrustLayer (rules + LLM + local model)** | 100% (40/40) | 93% | 7.5% (3/40) | 17.5% | 0% | 0.96 |

- Tactic named correctly on scams: LLM 55% · local model 47.5% · **shown to the buyer 62.5%**
- LLM p50 1319 ms / p95 2245 ms · local model about 80 ms on a laptop CPU
- The first held-out set, the dev set, every error, and the local-model comparison: [NUMBERS.md](NUMBERS.md)
<!-- EVAL:END -->

## The fine-tuned local models

| | |
|---|---|
| Starting point | [`BothBosu/distilbert-scam-classifier-v1.3`](https://huggingface.co/BothBosu/distilbert-scam-classifier-v1.3) (Apache-2.0), a DistilBERT scam classifier from the synthetic-data scam-detection work ([code](https://github.com/BothBosu/Synthetic-Data-for-Scam-Detection-Leveraging-LLMs-to-Train-Deep-Learning-Models), MIT) trained on LLM-generated scam **phone calls** |
| v1 | Fine-tuned on 281 marketplace chats ([train_chats.jsonl](eval/data/train_chats.jsonl), `gpt-oss-20b`) + 140 [`BothBosu/scam-dialogue`](https://huggingface.co/datasets/BothBosu/scam-dialogue) dialogues. The public model flagged **59%** of honest dev chats; v1 flagged **0%** at its threshold (ROC-AUC 0.885 → 0.956) |
| **v2 (deployed)** | Same base, **two heads** (scam probability + which of 6 tactics), trained on the 281 chats plus **105 hard examples** ([train_hard_chats.jsonl](eval/data/train_hard_chats.jsonl): honest patterns that fooled v1, polite scams). In LLM-outage mode it cut honest dev chats shown a warning from 38% to 23.5%, and it names the tactic as well as the LLM ([models/train_scam_model_v2.py](models/train_scam_model_v2.py)) |
| Distilled students | MiniLM-L6 (23 MB, 28 ms) and MiniLM-L12 (34 MB, 58 ms) learned from the v2 teacher's soft outputs. Better scam ranking (dev ROC-AUC up to 0.980) at a fraction of the cost, but they lost most of the tactic skill, so by our pre-set rule the teacher is deployed. Switch with `LOCAL_MODEL=v2-student-l12` |
| Serving | ONNX, int8 dynamic quantization, ONNX Runtime on CPU in the API (about 80 ms on a laptop, ~600 ms on Render's free CPU). Thresholds calibrated on each int8 model's own dev outputs ([models/select_and_calibrate.py](models/select_and_calibrate.py)) |
| Training | GTX 1650, 4 GB: v1 about 9 min, v2 teacher 14 min, students 6–13 min |
| Honest limits | Never pauses a payment alone (it can't cite evidence). Dev chose epochs, thresholds, the deployed model and the tactic preference; test set v2 is the real measure ([NUMBERS.md](NUMBERS.md)) |

## PayPal technology used

| PayPal capability | Where |
|---|---|
| **Orders v2**: create with `intent: AUTHORIZE`, authorize | every checkout ([backend/app/paypal.py](backend/app/paypal.py)) |
| **Payments v2**: capture (full / partial-final), void, refund, reauthorize | release, scam cancel, resolution settlements, expired holds |
| **Payouts v1**: create batch, get status | pay the seller after delivery, minus platform fee; reconcile the outcome |
| **Webhooks**: register, verify signature, consume events | [backend/app/webhooks.py](backend/app/webhooks.py) |
| **Subscriptions v1**: catalog product, billing plan with free trial, verify, cancel, suspend, activate | TrustLayer Plus ([backend/app/subscriptions.py](backend/app/subscriptions.py)) |
| **JS SDK** with `vault=true&intent=subscription` (separate namespace) | the Plus subscribe button |
| **PayPal JS SDK** buttons (`intent=authorize`) | buyer approval in the browser, plus a redirect fallback |
| Seller Protection status from authorizations and captures | seller health dashboard |
| **PayPal AI Toolkit** (Claude Code plugin + sandbox MCP server) | used during development to inspect orders and test sandbox flows |

## AI tools used and how

| Tool / model | Used for | Guardrails |
|---|---|---|
| **Groq · `openai/gpt-oss-120b`** (primary) | scam tactic classification with cited evidence; resolution-agent turns; seller-health explanations | JSON-only outputs, temperature 0 for risk, grounded-quote verification, policy enforcement in code, hard timeouts |
| **Google Gemini · `gemini-flash-lite-latest`** | automatic fallback when Groq is rate-limited or down | same prompts and checks |
| **Ollama · `mistral`** (local, optional) | offline last-resort fallback | same |
| **Groq · `qwen/qwen3.8-27b`** | generating the labelled dev and held-out test sets (a *different* model from the classifier) | labels come from the generation spec, never from a classifier |
| **Groq · `openai/gpt-oss-20b`** | generating the training set for the local model (a third generator, disjoint from dev/test) | same |
| **DistilBERT, fine-tuned by us** (from `BothBosu/distilbert-scam-classifier-v1.3`, Apache-2.0) | local scam probability inside Pay-pause, ONNX int8 on CPU; keeps working during LLM outages | never pauses alone; threshold chosen on the dev set |
| **`BothBosu/scam-dialogue`** dataset (Apache-2.0) | out-of-domain scam dialogues mixed into fine-tuning | sanity-checked on its own test split |
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
python -m pytest tests            # 65 offline tests: ledger, scam rules + grounding + fusion + local model, refund policy,
                                  # every order path, webhooks, subscriptions + seller kit, reauthorization (fake PayPal + fake LLM)
python scripts/e2e_paypal.py      # real sandbox: approve → hold → AI settlement → capture → payout; and scam → pause → void
python scripts/ui_smoke.py        # headless: every page renders, no console errors, mobile layout
python eval/run_eval.py && python eval/report.py   # Pay-pause precision / recall / false-pause rate → NUMBERS.md
```
(The two browser scripts need `pip install playwright && playwright install chromium`.)

### Deploy (Render, free)
`render.yaml` is a ready Blueprint: New → Blueprint → this repo → fill the secret env vars. After the first deploy, run
`python scripts/register_webhook.py https://<your-app>.onrender.com` and set the printed `PAYPAL_WEBHOOK_ID`.

## Demo script (3 acts, under 3 minutes)
The click-by-click recording script is [docs/DEMO_SCRIPT.pdf](docs/DEMO_SCRIPT.pdf). In short:
1. **The scam**: open the *iPhone 15 Pro* listing → **Continue to payment** → Pay-pause flags Friends & Family + "no G&S" and highlights the exact chat lines → **Don't send money**. Or choose **continue with safeguards**, add a trusted contact, approve in PayPal, and watch the **cooling-off countdown**; the contact clicks **Stop this payment** and the **hold is voided**.
2. **The honest problem**: buy the *Canon AE-1* (no risk found) → approve → on the order page: *"It arrived 4 days late and I missed my trip"* → the assistant offers a partial refund within policy → **Accept offer** → PayPal captures less and releases the rest of the hold → **Pay out seller** → seller paid by Payouts.
3. **The seller's view**: *Seller health → GadgetHub*: dispute rate over the 1.5% line, the rate without early resolution, plain-English actions. **Audit log**: **Verify chain**, then **Simulate tampering**.

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
