"""Fine-tune a public scam classifier for marketplace payment chats, then export ONNX int8.

Run in the CUDA training env:  .venv-train/Scripts/python models/train_scam_model.py [--base MODEL] [--tag NAME]

Data (all labels come from how the data was produced, never from a classifier):
  - in-domain train:  eval/data/train_chats.jsonl  (marketplace chats, generator gpt-oss-20b)
  - in-domain dev:    eval/data/chats.jsonl        (marketplace chats, generator qwen) -> validation + threshold
  - out-of-domain:    BothBosu/scam-dialogue (Apache-2.0) phone-call dialogues, train split mixed in so the
                      model keeps general scam knowledge; its test split is reported as a sanity check.
  - held-out test:    eval/data/test_chats.jsonl   is NOT touched here (scored only by eval/run_eval.py).

Base model default: BothBosu/distilbert-scam-classifier-v1.3 (Apache-2.0; DistilBERT fine-tuned on LLM-generated
scam phone dialogues). Ablation: --base distilbert-base-uncased (no scam pre-training).
"""
import argparse
import json
import pathlib
import random
import sys
import time

import numpy as np
import torch
from datasets import load_dataset
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.localmodel import format_chat  # noqa: E402  (same text format as serving)

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="BothBosu/distilbert-scam-classifier-v1.3")
ap.add_argument("--tag", default="scam-distilbert")
ap.add_argument("--epochs", type=int, default=4)
ap.add_argument("--lr", type=float, default=3e-5)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--max_length", type=int, default=384)
ap.add_argument("--phone_ratio", type=float, default=0.5, help="phone dialogues per in-domain example")
ap.add_argument("--export", action="store_true", help="export ONNX int8 to models/<tag>/")
ap.add_argument("--seed", type=int, default=13)
args = ap.parse_args()

random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
dev = "cuda" if torch.cuda.is_available() else "cpu"
print(f"device={dev} base={args.base}", flush=True)


def load_market(path: pathlib.Path) -> list[tuple[str, int]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        li, s = r["listing"], r["seller"]
        listing = {"title": li.get("title", ""), "price": li.get("price") or 0, "ref_price": li.get("ref_price") or 0}
        seller = {"joined_days_ago": s.get("joined_days_ago") or 0, "completed_sales": s.get("completed_sales") or 0}
        out.append((format_chat(listing, seller, r["chat"]), 1 if r["label"] == "scam" else 0))
    return out


train_market = load_market(ROOT / "eval" / "data" / "train_chats.jsonl")
val_market = load_market(ROOT / "eval" / "data" / "chats.jsonl")
phone = load_dataset("BothBosu/scam-dialogue")
phone_train = [(f"[PHONE CALL]\n{r['dialogue']}", int(r["label"])) for r in phone["train"]]
phone_test = [(f"[PHONE CALL]\n{r['dialogue']}", int(r["label"])) for r in phone["test"]]
random.shuffle(phone_train)
n_phone = int(len(train_market) * args.phone_ratio)
train = train_market + phone_train[:n_phone]
random.shuffle(train)
print(f"train: {len(train_market)} marketplace + {n_phone} phone | val (dev, marketplace): {len(val_market)} | "
      f"phone test: {len(phone_test)} | scam share {np.mean([y for _, y in train]):.2f}", flush=True)

tok = AutoTokenizer.from_pretrained(args.base)
model = AutoModelForSequenceClassification.from_pretrained(args.base, num_labels=2).to(dev)


def batches(data, shuffle):
    def collate(b):
        enc = tok([t for t, _ in b], truncation=True, max_length=args.max_length, padding=True, return_tensors="pt")
        enc["labels"] = torch.tensor([y for _, y in b])
        return enc
    return DataLoader(data, batch_size=args.batch, shuffle=shuffle, collate_fn=collate)


@torch.no_grad()
def probs(data) -> np.ndarray:
    model.eval(); out = []
    for b in batches(data, False):
        b = {k: v.to(dev) for k, v in b.items() if k != "labels"}
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=dev == "cuda"):
            logits = model(**b).logits.float()
        out.append(torch.softmax(logits, -1)[:, 1].cpu().numpy())
    return np.concatenate(out)


def report(name: str, data, p: np.ndarray, thr: float) -> dict:
    y = np.array([l for _, l in data]); pred = (p >= thr).astype(int)
    pr, rc, f1, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    fp_rate = float(((pred == 1) & (y == 0)).sum() / max(1, (y == 0).sum()))
    m = {"precision": round(float(pr), 3), "recall": round(float(rc), 3), "f1": round(float(f1), 3),
         "false_positive_rate": round(fp_rate, 3), "roc_auc": round(float(roc_auc_score(y, p)), 3),
         "pr_auc": round(float(average_precision_score(y, p)), 3), "n": int(len(y)), "threshold": round(thr, 3)}
    print(f"  {name:28s} " + " ".join(f"{k}={v}" for k, v in m.items()), flush=True)
    return m


def pick_threshold(y: np.ndarray, p: np.ndarray, min_precision: float = 0.95) -> float:
    """Highest-recall threshold that keeps precision >= min_precision on the dev set (fallback: best F1)."""
    best, best_f1 = 0.5, -1.0
    for t in np.linspace(0.05, 0.99, 95):
        pred = (p >= t).astype(int)
        tp = ((pred == 1) & (y == 1)).sum(); fp = ((pred == 1) & (y == 0)).sum(); fn = ((pred == 0) & (y == 1)).sum()
        prec = tp / max(1, tp + fp); rec = tp / max(1, tp + fn); f1 = 2 * prec * rec / max(1e-9, prec + rec)
        if prec >= min_precision and rec > 0:
            score = rec + 1e-3 * t  # prefer higher threshold among equal recall
            if score > best_f1:
                best, best_f1 = float(t), score
    if best_f1 < 0:
        for t in np.linspace(0.05, 0.99, 95):
            pred = (p >= t).astype(int)
            _, _, f1, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
            if f1 > best_f1:
                best, best_f1 = float(t), f1
    return best


results = {"base_model": args.base, "args": vars(args)}
print("before fine-tuning (zero-shot):", flush=True)
results["zero_shot"] = {"dev_marketplace": report("dev marketplace", val_market, probs(val_market), 0.5),
                        "phone_test": report("phone test", phone_test, probs(phone_test), 0.5)}

opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
steps = args.epochs * len(batches(train, True))
sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)
scaler = torch.cuda.amp.GradScaler(enabled=dev == "cuda")
best_auc, best_state = -1.0, None
t0 = time.time()
for ep in range(args.epochs):
    model.train(); losses = []
    for b in batches(train, True):
        b = {k: v.to(dev) for k, v in b.items()}
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=dev == "cuda"):
            loss = model(**b).loss
        opt.zero_grad(); scaler.scale(loss).backward(); scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(opt); scaler.update(); sched.step(); losses.append(loss.item())
    pv = probs(val_market); yv = np.array([l for _, l in val_market])
    auc = roc_auc_score(yv, pv)
    print(f"epoch {ep + 1}: loss {np.mean(losses):.4f} | dev ROC-AUC {auc:.3f} | {time.time() - t0:.0f}s", flush=True)
    if auc > best_auc:
        best_auc, best_state = auc, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
model.load_state_dict(best_state)

pv = probs(val_market); yv = np.array([l for _, l in val_market])
thr = pick_threshold(yv, pv)
print("after fine-tuning (best epoch by dev ROC-AUC):", flush=True)
results["fine_tuned"] = {"dev_marketplace": report("dev marketplace", val_market, pv, thr),
                         "phone_test": report("phone test", phone_test, probs(phone_test), thr)}
results["threshold"] = thr
results["train_seconds"] = int(time.time() - t0)

out_dir = ROOT / "models" / args.tag
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "training_report.json").write_text(json.dumps(results, indent=2))

if args.export:
    import onnx  # noqa: F401
    from onnxruntime.quantization import QuantType, quantize_dynamic

    ckpt = ROOT / "models" / "checkpoints" / args.tag
    model.save_pretrained(ckpt); tok.save_pretrained(ckpt)
    model.eval().to("cpu").float()
    dummy = tok("hello world", return_tensors="pt")
    fp32 = out_dir / "model.fp32.onnx"
    torch.onnx.export(model, (dummy["input_ids"], dummy["attention_mask"]), str(fp32),
                      input_names=["input_ids", "attention_mask"], output_names=["logits"],
                      dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}, "logits": {0: "b"}},
                      opset_version=17)
    quantize_dynamic(str(fp32), str(out_dir / "model.int8.onnx"), weight_type=QuantType.QInt8)
    fp32.unlink()
    tok.backend_tokenizer.save(str(out_dir / "tokenizer.json"))
    meta = {"name": args.tag, "base_model": args.base, "threshold": thr, "max_length": args.max_length,
            "labels": {"0": "NON-SCAM", "1": "SCAM"}, "trained_on": {
                "marketplace_train": len(train_market), "phone_dialogues": n_phone,
                "sources": ["eval/data/train_chats.jsonl (gpt-oss-20b generated)", "BothBosu/scam-dialogue (Apache-2.0)"]},
            "dev_metrics": results["fine_tuned"]["dev_marketplace"]}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    size = (out_dir / "model.int8.onnx").stat().st_size / 1e6
    print(f"exported {out_dir / 'model.int8.onnx'} ({size:.1f} MB)", flush=True)
