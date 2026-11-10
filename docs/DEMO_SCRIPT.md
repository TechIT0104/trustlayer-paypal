# Demo video script (target 2:45, hard limit 3:00)

Record at 1366x768 or 1440x900, browser zoom 100%, PayPal sandbox buyer already logged out.
Before recording: Audit log -> Reset demo. Keep a second tab ready for the trusted-contact link.
No music with third-party rights; voice-over only (or royalty-free track you own).

| Time | Screen | Voice-over |
|---|---|---|
| 0:00-0:15 | Marketplace | "Purchase scams are 71% of authorised-payment fraud, and if you're tricked into paying, it usually isn't refunded. Sellers lose disputes that started as a late parcel. TrustLayer puts AI where trust breaks down, on top of PayPal." |
| 0:15-0:45 | iPhone listing -> Continue to payment -> pause modal | "This seller wants Friends and Family and 'no Goods and Services'. Before any money moves, TrustLayer checks the chat: rules plus an LLM that must quote the exact lines. Every quote is verified against the real chat, so it can't invent evidence. It names the tactic in plain words and makes 'Don't send money' the big button." |
| 0:45-1:10 | "I know this seller" -> trusted contact "Mom" -> PayPal approve -> order page countdown -> open contact tab -> "Stop this payment" | "If you insist, the money is only authorized, a PayPal hold, with a cooling-off timer, and someone you trust gets a link. Mom says stop: the authorization is voided. Zero dollars charged." |
| 1:10-1:45 | Canon listing -> Clear -> PayPal approve -> order page -> Resolution center: "It arrived 4 days late and I missed my trip" -> offer -> Accept | "An honest seller. The camera arrives late and the buyer is annoyed. That's how disputes start. The resolution assistant reads the order facts and the seller's policy and offers 18 dollars. Code enforces the policy, so the AI can't give away money the seller didn't allow. Accept: PayPal captures 162, releases 18 of the hold, and there's no dispute." |
| 1:45-2:00 | Confirm delivery -> Payment card shows payout | "Confirm delivery: the seller is paid out with PayPal Payouts, minus the platform fee. Every PayPal ID is right here." |
| 2:00-2:25 | Seller health -> GadgetHub | "For sellers, the scariest thing about PayPal is a hold with no warning. GadgetHub is at 1.59% disputes, over the 1.5% card-network line. Without early resolution it would be 2.52%. Plain-English next steps, from public signals only." |
| 2:25-2:40 | Audit log -> Simulate tampering -> chain breaks at record | "Every PayPal call and AI decision is in a hash-chained audit log. Edit one record and verification names the break." |
| 2:40-2:50 | README evaluation table | "On 100 labelled chats, here are our real precision, recall and false-pause numbers. TrustLayer: safer payments for both sides, built on PayPal." |

## Backup lines if something is slow
- PayPal popup slow: use "PayPal button not loading? Use redirect checkout".
- Groq busy: the app falls back to Gemini automatically; the model name under the verdict changes, which is fine to show.
