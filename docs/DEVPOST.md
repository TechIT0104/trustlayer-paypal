# Devpost submission text

Copy each section into the matching Devpost field.

## Tagline
A trust layer for both sides of a PayPal payment: AI that stops scams before money moves, settles problems before
they become disputes, and warns sellers before a hold.

## Inspiration
PayPal's loudest complaints aren't about moving money; they're about trust breaking down around it.
- **Buyers:** purchase scams are 71% of UK authorised-push-payment fraud cases (£576M lost in 2025). If you're
  *tricked* into paying, for example "send it Friends & Family", it isn't "unauthorized", so it's rarely refunded.
- **Sellers:** 43.8% of chargebacks are friendly fraud, and 85% of people who file one say bad service pushed them to it.
  Card networks flag merchants above a 1.5% dispute ratio.
- **Everyone:** about 1 in 5 PayPal reviews mention sudden holds with no explanation.

Revolut cut card-scam losses about 30% with an AI "break the spell" flow; PayPal has nothing equivalent. We built it,
and extended the idea to the two other moments where trust fails.

## What it does
1. **Pay-pause.** Every checkout is a PayPal *authorization*, not a charge. Before the button appears, TrustLayer reads
   the listing and the buyer-seller chat. Explainable rules plus an LLM name the scam tactic and must quote the exact chat
   lines; every quote is checked against the real chat, so the AI can't invent evidence. Risky payments get a "break the
   spell" screen. If the buyer insists, the hold enters a cooling-off period and a trusted contact can stop it; either
   way the authorization is voided and nothing is charged.
2. **Pre-dispute resolution.** An unhappy buyer talks to an AI assistant acting for the seller. It classifies the issue
   and proposes a fix; code enforces the seller's refund policy so the model can't promise unauthorized money. Accepting
   executes on PayPal: a reduced capture (if still on hold) or a partial refund. Anything beyond policy goes to the
   seller's inbox.
3. **Seller account health.** Dispute ratio against the 1.5% line, refund rate, sales spikes, new-account velocity,
   scam pauses and Seller Protection coverage, explained in plain English with next steps, including "your dispute
   rate without early resolution".
4. **Audit log.** Every PayPal call and AI decision lives in a SHA-256 hash chain; tampering is detected and located.

## How we built it
- **PayPal:** Orders v2 (`intent: AUTHORIZE`), Payments v2 (authorize, capture, partial-final capture, void, refund,
  reauthorize), Payouts v1 (send and reconcile), Webhooks (register, signature verification, idempotent consumption),
  and the JS SDK with `intent=authorize`. Every state change carries a `PayPal-Request-Id` for idempotency. Handles
  `INSTRUMENT_DECLINED` (restart) and expired authorizations (reauthorize).
- **AI:** Groq `openai/gpt-oss-120b` (primary), Gemini `gemini-flash-lite-latest` (automatic fallback), optional local
  Ollama. JSON-only outputs, a grounding check on cited evidence, and deterministic policy enforcement around every
  model decision.
- **Stack:** FastAPI + SQLite, a no-build React frontend, deployed on Render. 43 offline tests (fake PayPal and fake
  LLM), a real-sandbox end-to-end test, a headless UI test, and a labelled evaluation set.
- **Dev tooling:** Claude Code with the PayPal AI Toolkit plugin and sandbox MCP server.

## Challenges we ran into
- **False positives.** Honest sellers say "another buyer is interested" or even "please *don't* use Friends & Family".
  Rules alone flag these. We fuse rules with an LLM, require corroboration before pausing, and measured it on hard negatives.
- **AI that invents evidence.** We require exact quotes with line numbers and verify each one; unverifiable quotes are discarded.
- **Sandbox realities.** Accounts created in some countries can't send Payouts; we documented the US-account setup.
  Payouts v1 and Orders v2 use different money schemas (`currency` vs `currency_code`).
- **Free-tier AI limits.** Groq's per-minute token caps meant we had to build rate-aware batching and provider fallback.

## Accomplishments we're proud of
- Real money paths end to end in sandbox: hold, cooling-off, void, AI-settled partial capture, refund, payout.
- The AI never moves money on its own say-so: policy limits, grounded evidence and human confirmation sit around every decision.
- Honest, reproducible numbers (see NUMBERS.md), including every miss.

## What we learned
Scam detection needs an intervention people trust: specific evidence, a calm explanation and a safe default. And
holding money (authorize, don't capture) is a powerful primitive for safety that most checkouts don't use.

## What's next
Real 24-hour cooling-off with SMS/email to trusted contacts, platform onboarding for multi-seller payouts, PayPal
Disputes API integration for cases that still escalate, and a small transaction-sequence model per seller.

## Built with
python, fastapi, sqlite, react, paypal-orders-v2, paypal-payments-v2, paypal-payouts, paypal-webhooks, paypal-js-sdk,
paypal-ai-toolkit, groq, gpt-oss-120b, gemini, ollama, render, playwright, pytest

## AI tools used (required field)
- **Groq, openai/gpt-oss-120b:** scam-tactic classification with cited evidence (Pay-pause), resolution-assistant turns,
  seller-health explanations. Every output is JSON, verified (quotes) or clamped (refund policy) by code.
- **Google Gemini, gemini-flash-lite-latest:** automatic fallback for all of the above when Groq is rate-limited.
- **Ollama, mistral (local, optional):** offline fallback.
- **Groq, qwen/qwen3.8-27b:** generated the labelled evaluation chats (a different model from the classifier).
- **Claude Code + PayPal AI Toolkit (MCP):** development assistant; used the sandbox MCP tools to inspect orders while building.
