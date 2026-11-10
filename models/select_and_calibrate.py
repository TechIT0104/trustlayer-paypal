"""Compare exported local models on the DEV set (never a test set), calibrate thresholds, pick one to deploy.

For each models/<name>/model.int8.onnx: ROC-AUC, threshold = highest recall at precision >= 0.95 (on the int8
model's own outputs), recall / false positives at it, tactic accuracy on scams, CPU latency (1 thread), size.
Deployment rule, fixed before looking at results: the smallest model within 0.01 ROC-AUC and 0.05 tactic accuracy
of the best v2 teacher; otherwise the teacher.

Usage: .venv/Scripts/python models/select_and_calibrate.py
"""
import json
import pathlib
import sys
import time

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.localmodel import TACTICS, TYPE_TO_TACTIC, format_chat  # noqa: E402

CANDIDATES = ["scam-distilbert", "v2-teacher", "v2-student-l6", "v2-student-l12"]


def dev_rows():
    rows = []
    for line in (ROOT / "eval/data/chats.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        li, s = r["listing"], r["seller"]
        text = format_chat({"title": li.get("title", ""), "price": li.get("price") or 0, "ref_price": li.get("ref_price") or 0},
                           {"joined_days_ago": s.get("joined_days_ago") or 0, "completed_sales": s.get("completed_sales") or 0},
                           r["chat"])
        y = int(r["label"] == "scam")
        rows.append((text, y, TYPE_TO_TACTIC.get(r["type"], "none") if y else "none"))
    return rows


def auc(p, y):
    pos, neg = p[y == 1], p[y == 0]
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def run(name, rows):
    d = ROOT / "models" / name
    if not (d / "model.int8.onnx").exists():
        return None
    meta = json.loads((d / "meta.json").read_text())
    opts = ort.SessionOptions(); opts.intra_op_num_threads = 1
    sess = ort.InferenceSession(str(d / "model.int8.onnx"), opts, providers=["CPUExecutionProvider"])
    tok = Tokenizer.from_file(str(d / "tokenizer.json")); tok.enable_truncation(max_length=meta.get("max_length", 384))
    ps, tacs, lat = [], [], []
    for text, _, _ in rows:
        enc = tok.encode(text)
        t0 = time.time()
        outs = sess.run(None, {"input_ids": np.array([enc.ids], dtype=np.int64),
                               "attention_mask": np.array([enc.attention_mask], dtype=np.int64)})
        lat.append((time.time() - t0) * 1000)
        lg = outs[0][0]; e = np.exp(lg - lg.max()); ps.append(e[1] / e.sum())
        tacs.append(meta["tactics"][int(outs[1][0].argmax())] if len(outs) > 1 and meta.get("tactics") else None)
    p = np.array(ps); y = np.array([r[1] for r in rows])
    best = None
    for t in np.arange(0.05, 0.995, 0.01):
        tp = int(((p >= t) & (y == 1)).sum()); fp = int(((p >= t) & (y == 0)).sum()); fn = int(((p < t) & (y == 1)).sum())
        prec, rec = tp / max(1, tp + fp), tp / max(1, tp + fn)
        if prec >= 0.95 and (best is None or rec > best[1] + 1e-9 or (abs(rec - best[1]) < 1e-9 and t > best[0])):
            best = (round(float(t), 2), rec, tp, fp)
    scams = [(t, r[2]) for t, r in zip(tacs, rows) if r[1] == 1]
    tac_acc = (sum(1 for t, g in scams if t == g) / len(scams)) if tacs[0] is not None else None
    lat.sort()
    out = {"name": name, "base_model": meta.get("base_model"), "role": meta.get("role", "v1"),
           "params_millions": meta.get("params_millions"), "size_mb": round((d / "model.int8.onnx").stat().st_size / 1e6, 1),
           "dev_roc_auc": round(auc(p, y), 3), "threshold": best[0], "dev_recall_at_thr": round(best[1], 3),
           "dev_tp": best[2], "dev_fp": best[3], "dev_tactic_accuracy": None if tac_acc is None else round(tac_acc, 3),
           "cpu_latency_ms_p50": round(lat[len(lat) // 2], 1), "cpu_latency_ms_p95": round(lat[int(0.95 * (len(lat) - 1))], 1)}
    meta["threshold"] = best[0]
    meta["threshold_note"] = "calibrated on this int8 model's dev-set outputs (highest recall at precision >= 0.95)"
    meta["dev_metrics_onnx"] = {k: out[k] for k in ("dev_roc_auc", "dev_recall_at_thr", "dev_tp", "dev_fp", "dev_tactic_accuracy")}
    (d / "meta.json").write_text(json.dumps(meta, indent=2))
    return out


def main():
    rows = dev_rows()
    res = [r for r in (run(n, rows) for n in CANDIDATES) if r]
    print(f"{'model':16s} {'params':>7s} {'MB':>6s} {'AUC':>6s} {'thr':>5s} {'recall':>7s} {'FP':>3s} {'tactic':>7s} {'p50ms':>7s} {'p95ms':>7s}")
    for r in res:
        print(f"{r['name']:16s} {str(r['params_millions']):>7s} {r['size_mb']:>6} {r['dev_roc_auc']:>6} {r['threshold']:>5} "
              f"{r['dev_recall_at_thr']:>7} {r['dev_fp']:>3} {str(r['dev_tactic_accuracy']):>7s} {r['cpu_latency_ms_p50']:>7} {r['cpu_latency_ms_p95']:>7}")
    teacher = next((r for r in res if r["name"] == "v2-teacher"), None)
    chosen = teacher
    if teacher:
        ok = [r for r in res if r["name"].startswith("v2-student") and r["dev_roc_auc"] >= teacher["dev_roc_auc"] - 0.01
              and (r["dev_tactic_accuracy"] or 0) >= (teacher["dev_tactic_accuracy"] or 0) - 0.05]
        if ok:
            chosen = min(ok, key=lambda r: r["size_mb"])
    summary = {"candidates": res, "chosen": chosen["name"] if chosen else "scam-distilbert",
               "rule": "smallest v2 student within 0.01 dev ROC-AUC and 0.05 dev tactic accuracy of the v2 teacher, else the teacher"}
    (ROOT / "models" / "model_comparison.json").write_text(json.dumps(summary, indent=2))
    print("chosen for deployment:", summary["chosen"])


if __name__ == "__main__":
    main()
