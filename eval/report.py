"""Write NUMBERS.md and the README evaluation section from eval/results/* and models/*.

Headline: held-out test set v2 (eval/results/test2), scored once with the final configuration.
Also reported, clearly labelled: test set v1 (first held-out set, seen after its first scoring), the dev set,
and the local-model comparison (v1, v2 teacher, distilled students).

Usage: .venv/Scripts/python eval/report.py
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(split: str):
    d = ROOT / "eval" / "results" / split
    if not (d / "summary.json").exists():
        return None, []
    return json.loads((d / "summary.json").read_text()), [json.loads(l) for l in (d / "per_example.jsonl").read_text().splitlines()]


def pct(x) -> str:
    if x is None:
        return "–"
    return f"{100 * x:.1f}".rstrip("0").rstrip(".") + "%"


def row(name, m):
    if not m:
        return ""
    return (f"| {name} | {pct(m['recall'])} ({m['tp']}/{m['tp'] + m['fn']}) | {pct(m['precision'])} | "
            f"{pct(m['false_pause_rate'])} ({m['fp']}/{m['fp'] + m['tn']}) | {pct(m['honest_buyers_warned'])} | "
            f"{pct(m['scams_fully_missed'])} | {m['f1']:.2f} |\n")


HEAD = ("| Detector | Scams paused (recall) | Precision | Honest buyers wrongly paused | Honest buyers shown any warning "
        "| Scams with no warning at all | F1 |\n|---|---|---|---|---|---|---|\n")


def table(s):
    return (HEAD + row("Rules only", s["rules"]) + row("LLM only (grounded quotes)", s["llm"])
            + row("Local fine-tuned model only", s.get("model"))
            + row("Rules + local model (LLM outage mode)", s.get("fused_no_llm"))
            + row("**TrustLayer (rules + LLM + local model)**", s["fused"]))


def tactic_line(s):
    parts = [f"LLM {pct(s.get('tactic_accuracy_on_scams'))}"]
    if s.get("tactic_accuracy_local_model") is not None:
        parts.append(f"local model {pct(s['tactic_accuracy_local_model'])}")
    if s.get("tactic_accuracy_shown") is not None:
        parts.append(f"**shown to the buyer {pct(s['tactic_accuracy_shown'])}**")
    return " · ".join(parts)


def misses_md(per, notes):
    ms = [p for p in per if (p["fused"] == "PAUSE") != (p["label"] == "scam")]
    return "\n".join(
        f"- `{p['id']}` {p['label']} / {p['type']}: fused={p['fused']} (rules={p['rules']}, llm={p['llm']}, "
        f"model p={p.get('p_model')}, tactic shown={p.get('final_tactic')}, rule signals={', '.join(p['rule_keys']) or 'none'})"
        + (f"\n  - *Analysis:* {notes[p['id']]}" if p["id"] in notes else "") for p in ms) or "- none"


# Human analysis of errors, written after scoring. The engine was NOT changed in response.
NOTES = {
    "Ts003": "Seller proposes the 'Send Money' personal option; the buyer refuses and uses checkout. The LLM quoted the "
             "line but scored it 0.2, and a grounded LLM score currently outranks the local model (p=0.95).",
    "Tl048": "Honest seller in a hurry; the LLM read urgency as a tactic (the documented failure mode of LLM scam detectors).",
}

t2, t2_per = load("test2")
t1, t1_per = load("test")
t1b, _ = load("test_v1_v2model")
dev, _ = load("dev")
comp = json.loads((ROOT / "models/model_comparison.json").read_text()) if (ROOT / "models/model_comparison.json").exists() else None
if not t2:
    raise SystemExit("no eval/results/test2/summary.json yet")

per_type = "\n".join(f"| {t} | {v} |" for t, v in t2["per_type_fused_recall_or_specificity"].items())
lat = t2["llm_latency_ms"]

comp_md = ""
if comp:
    rows = "\n".join(
        f"| {'**' if c['name'] == comp['chosen'] else ''}{c['name']}{'** (deployed)' if c['name'] == comp['chosen'] else ''} | "
        f"{c['base_model']} | {c['size_mb']} MB | {c['dev_roc_auc']} | {c['threshold']} | {pct(c['dev_recall_at_thr'])} | "
        f"{c['dev_fp']} | {pct(c['dev_tactic_accuracy']) if c['dev_tactic_accuracy'] is not None else 'n/a'} | "
        f"{c['cpu_latency_ms_p50']} ms |" for c in comp["candidates"])
    comp_md = f"""
## The local models (all measured as int8 ONNX on CPU, on the dev set)
| Model | Starting point | Size | ROC-AUC | Threshold | Recall at threshold | False positives (of 34) | Tactic accuracy | CPU latency p50 |
|---|---|---|---|---|---|---|---|---|
{rows}

- **v1** (`scam-distilbert`): the public `BothBosu/distilbert-scam-classifier-v1.3` fine-tuned on 281 marketplace chats.
  Out of the box the public model flagged 59% of honest dev chats; after fine-tuning, 0% at the v1 GPU threshold.
- **v2 teacher**: same base, fine-tuned with two heads (scam / tactic) on 281 + 105 *hard* chats (honest patterns that
  fooled v1, polite scams). In LLM-outage mode it cut the share of honest dev chats shown a warning from 38% to 23.5%.
- **v2 students**: MiniLM-L6 / L12 distilled from the teacher (soft targets + labels). They kept, even improved, scam
  ranking at a fraction of the size and latency, but **lost most of the tactic skill**.
- Deployment rule fixed before comparing: {comp['rule']}. Result: **{comp['chosen']}**. The L12 student is the best pure
  scam detector and can be served instead with `LOCAL_MODEL=v2-student-l12`.
- Thresholds are calibrated on each int8 model's own dev outputs (highest recall at precision ≥ 95%). The tactic
  preference (local model first, then LLM) was chosen on dev: 53% vs 49%, a 2-example difference, so treat it as small.
"""

short = f"""Held-out **test set v2: {t2['n']} marketplace chats** ({t2['n_scam']} scams, {t2['n_legit']} honest; new item
categories and wording), generated before the final model was chosen and scored exactly once with the final configuration.

{table(t2)}
- Tactic named correctly on scams: {tactic_line(t2)}
- LLM p50 {lat['p50']} ms / p95 {lat['p95']} ms · local model about 80 ms on a laptop CPU
- The first held-out set, the dev set, every error, and the local-model comparison: [NUMBERS.md](NUMBERS.md)"""

numbers = f"""# NUMBERS: Pay-pause evaluation

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
- Classifier LLM: `{t2['classifier_model']}` on Groq, temperature 0, no fallback provider during measurement.
- Positive class = scam. **PAUSE** = money held + cooling-off. CAUTION = a warning without holding money.

## Headline: held-out test set v2 ({t2['n']} chats)
{table(t2)}
Tactic named correctly on scams: {tactic_line(t2)} · ungrounded AI quotes discarded: {t2['ungrounded_quotes_dropped']} ·
LLM latency p50 {lat['p50']} ms, p95 {lat['p95']} ms. Local model: `{t2['local_model'].get('name')}`.

### Per scenario (fused: scams paused / honest chats not paused)
| Scenario | Correct |
|---|---|
{per_type}

### Every fused error on test v2
{misses_md(t2_per, NOTES)}
{"" if not t1 else f'''
## Test set v1 (seen; for comparison)
As first scored with the v1 local model (before we looked at it):
{table(t1)}
Errors then: {misses_md(t1_per, NOTES)}
''' + ("" if not t1b else f'''
Re-scored with the final v2 configuration (not a clean test any more, since we had seen it):
{table(t1b)}
Tactic accuracy: {tactic_line(t1b)}
''')}
{"" if not dev else f'''
## Dev set ({dev['n']} chats; used for tuning, optimistic)
{table(dev)}
Three of the four dev errors are chats the generator labelled honest whose text is genuinely risky (the seller sends
their own "checkout link", or asks for payment before a local-pickup inspection), and one "scam" contains no scam.
We report the numbers as they are rather than relabel.
'''}
{comp_md}
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
"""
(ROOT / "NUMBERS.md").write_text(numbers, encoding="utf-8")
readme = (ROOT / "README.md").read_text(encoding="utf-8")
readme = re.sub(r"<!-- EVAL:START -->.*<!-- EVAL:END -->", f"<!-- EVAL:START -->\n{short}\n<!-- EVAL:END -->", readme, flags=re.S)
(ROOT / "README.md").write_text(readme, encoding="utf-8")
print(short)
