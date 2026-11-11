# Demo video script (target 2:50, hard limit 3:00)

> **Current script:** [DEMO_SCRIPT.pdf](DEMO_SCRIPT.pdf) (source: [DEMO_SCRIPT.html](DEMO_SCRIPT.html)). It starts on the
> new Overview landing page, has click-by-click steps, a full 5-minute version and a 2:58 submission cut. The table
> below is the earlier version, kept for reference.

Record at 1366x768 or 1440x900, browser zoom 100%. Open the live site once beforehand so the free server is awake.
Before recording: Audit log → Reset demo. Keep a second tab ready for the trusted-contact link.
Voice-over only; no music you don't own. Sandbox buyer: the US personal sandbox account.

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:12 | Marketplace | "Purchase scams are 71% of authorised-payment fraud, and if you're tricked into paying it usually isn't refunded. TrustLayer puts AI where trust breaks down, on top of PayPal." |
| 0:12–0:45 | iPhone listing → Continue to payment → pause modal; point at the flagged lines and the line under the verdict (LLM + local model) | "This seller wants Friends and Family. Before any money moves, three layers check the chat: rules, an LLM that must quote the exact lines (every quote is verified, so it can't invent evidence), and a DistilBERT model we fine-tuned ourselves that runs on CPU in about 80 milliseconds and keeps working if the LLM is down. 'Don't send money' is the big button." |
| 0:45–1:05 | "I know this seller" → contact "Mom" → PayPal approve → countdown → contact tab → "Stop this payment" | "If you insist, the money is only authorized, a PayPal hold, with a cooling-off timer, and someone you trust can stop it. Voided. Zero dollars charged." |
| 1:05–1:35 | Canon listing → PayPal approve → Resolution center: "It arrived 4 days late and I missed my trip" → Accept | "An honest seller, a late parcel: that's how disputes start. The assistant offers 18 dollars within the seller's policy, and code enforces the limit. Accept: PayPal captures 162 and releases 18 of the hold. No dispute." |
| 1:35–1:45 | Confirm delivery → Payment card | "Confirm delivery and the seller is paid with PayPal Payouts. Every PayPal ID is here." |
| 1:45–2:05 | Seller health → GadgetHub | "Sellers fear holds with no warning. GadgetHub is over the 1.5% dispute line; without early resolution it would be 2.52%. Plain-English next steps." |
| 2:05–2:30 | Subscriptions → a trial → Simulate +5 days → honest reminder → Cancel. Then Seller health → Maya → Subscriptions kit → paste "6-month minimum, call us to cancel" → Review terms (blocked) | "Subscriptions without the trap. Before the first charge it tells you honestly whether you used it, here it says cancel, and cancelling is one confirmation. Sellers get the same kit: the AI reviews their terms, and code blocks traps like call-to-cancel before anything reaches PayPal." |
| 2:30–2:50 | Audit log → Simulate tampering → break detected; then README evaluation table | "Every PayPal call and AI decision is hash-chained. And these are our real numbers on 80 held-out chats, scored once: every scam paused, three honest buyers wrongly paused, and we show you why." |

## Backup lines if something is slow
- PayPal popup slow: use "PayPal button not loading? Use redirect checkout".
- Groq busy: the app falls back to Gemini, or to rules plus the local model. The line under the verdict shows which; that's a feature worth showing.
