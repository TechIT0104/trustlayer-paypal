"""Evaluate Pay-pause on the labelled dataset: rules-only vs LLM-only vs fused (the product).

Positive class = scam. An intervention is a PAUSE verdict (money held + cooling-off).
We also report how often honest buyers see *any* warning (PAUSE or CAUTION), because
false alarms are the main reason scam warnings get ignored.

Usage: .venv/Scripts/python eval/run_eval.py
Writes eval/results/summary.json and eval/results/per_example.jsonl
"""
import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import config, llm, scam  # noqa: E402

config.LLM_PROVIDERS = ["groq"]  # one model for a clean measurement (the app itself falls back to Gemini)
DATA = ROOT / "eval" / "data" / "chats.jsonl"
# dataset sub-scenarios -> classifier tactic(s) that count as a correct label
EXPECTED_TACTIC = {
    "protection_bypass": {"protection_bypass"}, "protection_bypass_subtle": {"protection_bypass"},
    "obfuscated": {"protection_bypass", "off_platform_payment"},
    "off_platform_payment": {"off_platform_payment"}, "off_platform_giftcard_crypto": {"off_platform_payment"},
    "advance_fee": {"advance_fee"}, "advance_fee_deposit": {"advance_fee"},
    "payee_switch": {"payee_switch"}, "impersonation": {"impersonation"},
    "phishing_link": {"phishing_link", "impersonation"},
}
OUTDIR = ROOT / "eval" / "results"


def load() -> list[dict]:
    rows = []
    for line in DATA.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        li = r["listing"]
        r["listing_n"] = {"title": li.get("title", ""), "category": li.get("category", ""),
                          "price": float(li.get("price") or 0), "ref_price": float(li.get("ref_price") or 0),
                          "condition": li.get("condition", ""), "description": li.get("description", "")}
        s = r["seller"]
        r["seller_n"] = {"handle": s.get("handle", "seller"), "joined_days_ago": int(s.get("joined_days_ago") or 0),
                         "completed_sales": int(s.get("completed_sales") or 0), "rating": s.get("rating")}
        rows.append(r)
    return rows


def run_one(r: dict, mode: str) -> dict:
    for attempt in range(8):
        try:
            return scam.assess(r["listing_n"], r["seller_n"], r["chat"], mode=mode)
        except llm.LLMUnavailable:
            time.sleep(8 * (attempt + 1))
    raise RuntimeError("LLM unavailable")


def metrics(rows: list[dict], key: str) -> dict:
    tp = sum(1 for r in rows if r["label"] == "scam" and r[key] == "PAUSE")
    fn = sum(1 for r in rows if r["label"] == "scam" and r[key] != "PAUSE")
    fp = sum(1 for r in rows if r["label"] == "legit" and r[key] == "PAUSE")
    tn = sum(1 for r in rows if r["label"] == "legit" and r[key] != "PAUSE")
    warn_legit = sum(1 for r in rows if r["label"] == "legit" and r[key] in ("PAUSE", "CAUTION"))
    missed_any = sum(1 for r in rows if r["label"] == "scam" and r[key] == "CLEAR")
    n_scam, n_legit = tp + fn, fp + tn
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / n_scam if n_scam else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "false_pause_rate": round(fp / n_legit, 3) if n_legit else 0.0,
            "honest_buyers_warned": round(warn_legit / n_legit, 3) if n_legit else 0.0,
            "scams_fully_missed": round(missed_any / n_scam, 3) if n_scam else 0.0}


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    rows = load()
    print(f"{len(rows)} examples: {sum(r['label'] == 'scam' for r in rows)} scam / {sum(r['label'] == 'legit' for r in rows)} legit")
    per, lat = [], []
    for i, r in enumerate(rows, 1):
        rr = run_one(r, "rules")
        lm = run_one(r, "llm")
        fu = run_one(r, "fused")  # reuses the cached LLM call from "llm" mode: same prompt
        ai = fu.get("ai") or {}
        if ai and not ai.get("cached"):
            lat.append(ai["latency_ms"])
        elif lm.get("ai") and not lm["ai"].get("cached"):
            lat.append(lm["ai"]["latency_ms"])
        rec = {"id": r["id"], "label": r["label"], "type": r["type"],
               "rules": rr["verdict"], "llm": lm["verdict"], "fused": fu["verdict"],
               "score": fu["score"], "rule_keys": [s["key"] for s in fu["signals"]],
               "ai_type": ai.get("scam_type"), "ai_risk": ai.get("risk"),
               "grounded": len(ai.get("evidence", [])), "dropped": ai.get("dropped_evidence", 0)}
        per.append(rec)
        flag = "" if (rec["fused"] == "PAUSE") == (r["label"] == "scam") else "  <-- miss" if r["label"] == "scam" else "  <-- FALSE PAUSE"
        print(f"[{i:3d}] {r['id']} {r['label']:5s} {r['type']:22s} rules={rec['rules']:7s} llm={rec['llm']:7s} fused={rec['fused']:7s}{flag}", flush=True)
        time.sleep(1.5)  # stay under free-tier tokens/minute
    with (OUTDIR / "per_example.jsonl").open("w", encoding="utf-8") as f:
        for p in per:
            f.write(json.dumps(p) + "\n")
    scams = [p for p in per if p["label"] == "scam"]
    type_ok = sum(1 for p in scams if p["ai_type"] in EXPECTED_TACTIC.get(p["type"], {p["type"]}))
    summary = {
        "n": len(per), "n_scam": len(scams), "n_legit": len(per) - len(scams),
        "classifier_model": config.GROQ_MODEL, "dataset": str(DATA.relative_to(ROOT)),
        "rules": metrics(per, "rules"), "llm": metrics(per, "llm"), "fused": metrics(per, "fused"),
        "tactic_accuracy_on_scams": round(type_ok / len(scams), 3) if scams else None,
        "ungrounded_quotes_dropped": sum(p["dropped"] for p in per),
        "llm_latency_ms": {"p50": int(statistics.median(lat)) if lat else None,
                           "p95": int(sorted(lat)[int(0.95 * (len(lat) - 1))]) if lat else None},
        "per_type_fused_recall_or_specificity": {},
    }
    for t in sorted({p["type"] for p in per}):
        g = [p for p in per if p["type"] == t]
        ok = sum(1 for p in g if (p["fused"] == "PAUSE") == (p["label"] == "scam"))
        summary["per_type_fused_recall_or_specificity"][t] = f"{ok}/{len(g)}"
    (OUTDIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("rules", "llm", "fused", "tactic_accuracy_on_scams", "llm_latency_ms")}, indent=2))


if __name__ == "__main__":
    main()
