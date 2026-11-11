# NUMBERS: Pay-pause evaluation

Measured, not claimed. Reproduce any table with `python eval/run_eval.py <dataset> <results_dir>` then
`python eval/report.py`. LLM answers are cached in `eval/results/llm_cache.json`, so re-scoring is deterministic.

## Method
- **Disjoint datasets from different generator models.** Labels always come from the scenario that produced the chat.
  - Training: `eval/data/train_chats.jsonl` (281) and `train_hard_chats.jsonl` (105), generator `openai/gpt-oss-20b`.
  - Dev: `eval/data/chats.jsonl` (83, `qwen/qwen3.8-27b`). Used to develop rules and fusion, pick model epochs and
    thresholds, choose the deployed model and the tactic preference. Its numbers are optimistic.
  - Test v1: `eval/data/test_chats.jsonl` (80, qwen). Held out for the first engine; after we looked at its results
    it counts as **seen**, so it is reported only for comparison.
  - **Test v2**: `eval/data/test2_chats.jsonl` (80, qwen, new categories and phrasing). Generated before the v2 models were
    compared, never inspected, and scored **once** with the final configuration. This is the headline.
- Classifier LLM: `openai/gpt-oss-120b` on Groq, temperature 0, no fallback provider during measurement.
- Positive class = scam. **PAUSE** = money held + cooling-off. CAUTION = a warning without holding money.

## Headline: held-out test set v2 (80 chats)
| Detector | Scams paused (recall) | Precision | Honest buyers wrongly paused | Honest buyers shown any warning | Scams with no warning at all | F1 |
|---|---|---|---|---|---|---|
| Rules only | 35% (14/40) | 93.3% | 2.5% (1/40) | 20% | 15% | 0.51 |
| LLM only (grounded quotes) | 97.5% (39/40) | 95.1% | 5% (2/40) | 7.5% | 2.5% | 0.96 |
| Local fine-tuned model only | 90% (36/40) | 80% | 22.5% (9/40) | 60% | 5% | 0.85 |
| Rules + local model (LLM outage mode) | 80% (32/40) | 91.4% | 7.5% (3/40) | 40% | 2.5% | 0.85 |
| **TrustLayer (rules + LLM + local model)** | 100% (40/40) | 93% | 7.5% (3/40) | 17.5% | 0% | 0.96 |

Tactic named correctly on scams: LLM 55% · local model 47.5% · **shown to the buyer 62.5%** · ungrounded AI quotes discarded: 1 ·
LLM latency p50 1319 ms, p95 2245 ms. Local model: `v2-teacher`.

### Per scenario (fused: scams paused / honest chats not paused)
| Scenario | Correct |
|---|---|
| advance_fee | 4/4 |
| advance_fee_deposit | 4/4 |
| buyer_asks_ff_refused | 4/4 |
| gift_purchase | 2/4 |
| hard_haggle | 4/4 |
| honest_low_price | 3/4 |
| honest_new_seller | 4/4 |
| honest_urgency | 4/4 |
| impersonation | 4/4 |
| local_pickup | 4/4 |
| mentions_fees_honestly | 4/4 |
| normal | 4/4 |
| obfuscated | 4/4 |
| off_platform_giftcard_crypto | 4/4 |
| off_platform_payment | 4/4 |
| payee_switch | 4/4 |
| phishing_link | 4/4 |
| protection_bypass | 4/4 |
| protection_bypass_subtle | 4/4 |
| warns_against_ff | 4/4 |

### Every fused error on test v2
- `Vl051` legit / honest_low_price: fused=PAUSE (rules=CLEAR, llm=PAUSE, model p=0.7148, tactic shown=protection_bypass, rule signals=price_anomaly)
  - *Analysis:* Honest low-price sale, but the seller says they need 'guaranteed funds, not pending PayPal balances'; the LLM read that as a push away from protected payment. Borderline even for a human reviewer.
- `Vl078` legit / gift_purchase: fused=PAUSE (rules=CLEAR, llm=PAUSE, model p=0.473, tactic shown=protection_bypass, rule signals=none)
  - *Analysis:* The seller offers to write 'Gift Voucher' in the PayPal memo to keep a present discreet; the LLM read 'gift' as a Friends & Family (gift payment) request, with grounded quotes, so it could pause on its own.
- `Vl080` legit / gift_purchase: fused=PAUSE (rules=CAUTION, llm=CAUTION, model p=0.6579, tactic shown=None, rule signals=off_platform)
  - *Analysis:* The seller sells a bait-shop gift card as an add-on. The 'gift card' keyword rule fired (it targets gift-card payment) and the LLM's 0.6 plus the rule-agreement bonus reached the pause line. A rule that can't tell 'pay me with a gift card' from 'buy a gift card' is the fix, but we did not change the engine after scoring.

In LLM-outage mode (rules + local model) the errors are the opposite kind: honest sellers who *warn against*
Friends & Family or deposits trip the keyword rules, and without the LLM to read the context only a confident local
model can veto them. That is why outage mode warns more honest buyers; it is a fallback, not the main path.

## Test set v1 (seen; for comparison)
As first scored with the v1 local model (before we looked at it):
| Detector | Scams paused (recall) | Precision | Honest buyers wrongly paused | Honest buyers shown any warning | Scams with no warning at all | F1 |
|---|---|---|---|---|---|---|
| Rules only | 22.5% (9/40) | 100% | 0% (0/40) | 15% | 20% | 0.37 |
| LLM only (grounded quotes) | 97.5% (39/40) | 97.5% | 2.5% (1/40) | 2.5% | 2.5% | 0.97 |
| Local fine-tuned model only | 90% (36/40) | 90% | 10% (4/40) | 55% | 0% | 0.90 |
| Rules + local model (LLM outage mode) | 82.5% (33/40) | 97.1% | 2.5% (1/40) | 37.5% | 0% | 0.89 |
| **TrustLayer (rules + LLM + local model)** | 97.5% (39/40) | 97.5% | 2.5% (1/40) | 2.5% | 2.5% | 0.97 |

Errors then: - `Ts003` scam / protection_bypass: fused=CLEAR (rules=CLEAR, llm=CLEAR, model p=0.9482, tactic shown=None, rule signals=none)
  - *Analysis:* Seller proposes the 'Send Money' personal option; the buyer refuses and uses checkout. The LLM quoted the line but scored it 0.2, and a grounded LLM score currently outranks the local model (p=0.95).
- `Tl048` legit / honest_urgency: fused=PAUSE (rules=CLEAR, llm=PAUSE, model p=0.7149, tactic shown=None, rule signals=urgency)
  - *Analysis:* Honest seller in a hurry; the LLM read urgency as a tactic (the documented failure mode of LLM scam detectors).

Re-scored with the final v2 configuration (not a clean test any more, since we had seen it):
| Detector | Scams paused (recall) | Precision | Honest buyers wrongly paused | Honest buyers shown any warning | Scams with no warning at all | F1 |
|---|---|---|---|---|---|---|
| Rules only | 22.5% (9/40) | 100% | 0% (0/40) | 15% | 20% | 0.37 |
| LLM only (grounded quotes) | 97.5% (39/40) | 97.5% | 2.5% (1/40) | 2.5% | 2.5% | 0.97 |
| Local fine-tuned model only | 85% (34/40) | 82.9% | 17.5% (7/40) | 37.5% | 2.5% | 0.84 |
| Rules + local model (LLM outage mode) | 72.5% (29/40) | 96.7% | 2.5% (1/40) | 30% | 5% | 0.83 |
| **TrustLayer (rules + LLM + local model)** | 97.5% (39/40) | 97.5% | 2.5% (1/40) | 2.5% | 2.5% | 0.97 |

Tactic accuracy: LLM 52.5% · local model 37.5% · **shown to the buyer 55%**


## Dev set (83 chats; used for tuning, optimistic)
| Detector | Scams paused (recall) | Precision | Honest buyers wrongly paused | Honest buyers shown any warning | Scams with no warning at all | F1 |
|---|---|---|---|---|---|---|
| Rules only | 22.4% (11/49) | 100% | 0% (0/34) | 17.6% | 10.2% | 0.37 |
| LLM only (grounded quotes) | 98% (48/49) | 94.1% | 8.8% (3/34) | 11.8% | 2% | 0.96 |
| Local fine-tuned model only | 89.8% (44/49) | 95.7% | 5.9% (2/34) | 32.4% | 4.1% | 0.93 |
| Rules + local model (LLM outage mode) | 81.6% (40/49) | 97.6% | 2.9% (1/34) | 23.5% | 2% | 0.89 |
| **TrustLayer (rules + LLM + local model)** | 98% (48/49) | 94.1% | 8.8% (3/34) | 11.8% | 2% | 0.96 |

Three of the four dev errors are chats the generator labelled honest whose text is genuinely risky (the seller sends
their own "checkout link", or asks for payment before a local-pickup inspection), and one "scam" contains no scam.
We report the numbers as they are rather than relabel.


## The local models (all measured as int8 ONNX on CPU, on the dev set)
| Model | Starting point | Size | ROC-AUC | Threshold | Recall at threshold | False positives (of 34) | Tactic accuracy | CPU latency p50 |
|---|---|---|---|---|---|---|---|---|
| scam-distilbert | BothBosu/distilbert-scam-classifier-v1.3 | 67.3 MB | 0.962 | 0.88 | 85.7% | 2 | n/a | 79.0 ms |
| **v2-teacher** (deployed) | BothBosu/distilbert-scam-classifier-v1.3 | 66.8 MB | 0.962 | 0.77 | 89.8% | 2 | 44.9% | 84.4 ms |
| v2-student-l6 | nreimers/MiniLM-L6-H384-uncased | 22.9 MB | 0.966 | 0.95 | 83.7% | 2 | 28.6% | 28.0 ms |
| v2-student-l12 | microsoft/MiniLM-L12-H384-uncased | 33.9 MB | 0.98 | 0.94 | 93.9% | 0 | 26.5% | 58.4 ms |

- **v1** (`scam-distilbert`): the public `BothBosu/distilbert-scam-classifier-v1.3` fine-tuned on 281 marketplace chats.
  Out of the box the public model flagged 59% of honest dev chats; after fine-tuning, 0% at the v1 GPU threshold.
- **v2 teacher**: same base, fine-tuned with two heads (scam / tactic) on 281 + 105 *hard* chats (honest patterns that
  fooled v1, polite scams). In LLM-outage mode it cut the share of honest dev chats shown a warning from 38% to 23.5%.
- **v2 students**: MiniLM-L6 / L12 distilled from the teacher (soft targets + labels). They kept, even improved, scam
  ranking at a fraction of the size and latency, but **lost most of the tactic skill**.
- Deployment rule fixed before comparing: smallest v2 student within 0.01 dev ROC-AUC and 0.05 dev tactic accuracy of the v2 teacher, else the teacher. Result: **v2-teacher**. The L12 student is the best pure
  scam detector and can be served instead with `LOCAL_MODEL=v2-student-l12`.
- Thresholds are calibrated on each int8 model's own dev outputs (highest recall at precision ≥ 95%). The tactic
  preference (local model first, then LLM) was chosen on dev: 53% vs 49%, a 2-example difference, so treat it as small.

## What changed between the very first run and these numbers
1. The first harness counted rate-limited LLM calls as rules-only answers (reported 57% recall). It now retries.
2. Fusion bug: grounded LLM evidence could not pause on its own. Fixed (on dev).
3. Broader off-platform rules; a three-way vote when a keyword rule and the LLM disagree (on dev).
4. Local model v1, then v2 (hard examples + tactic head), thresholds and preference chosen on dev.

## Caveats
- All chats are LLM-generated: realistic patterns, not real-world prevalence or adversarial pressure.
- 80 test examples gives roughly ±8–10 points of uncertainty on each rate.
- Both test sets use the same 20 scenario types as training (v2 with new categories and wording), so they measure
  generalisation to new wording, not to entirely new tactics.
