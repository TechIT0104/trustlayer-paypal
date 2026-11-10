"""v2 local model: scam/not-scam + tactic heads, teacher fine-tuning and student distillation, ONNX int8 export.

Teacher (default): BothBosu/distilbert-scam-classifier-v1.3 fine-tuned with two heads.
  .venv-train/Scripts/python models/train_scam_model_v2.py --role teacher --tag v2-teacher --export
Student: a small MiniLM distilled from the teacher (soft targets + labels), for faster CPU inference.
  .venv-train/Scripts/python models/train_scam_model_v2.py --role student --base nreimers/MiniLM-L6-H384-uncased \
      --teacher v2-teacher --tag v2-student-l6 --export

Data: eval/data/train_chats.jsonl + eval/data/train_hard_chats.jsonl (marketplace, gpt-oss-20b) and
BothBosu/scam-dialogue phone dialogues (scam head only). Dev (eval/data/chats.jsonl) picks the epoch.
Held-out test sets are never read here.
"""
import argparse
import json
import pathlib
import random
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F
from datasets import load_dataset
from sklearn.metrics import average_precision_score, roc_auc_score
from torch import nn
from torch.utils.data import DataLoader
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.localmodel import TACTICS, TYPE_TO_TACTIC, format_chat  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--role", choices=["teacher", "student"], default="teacher")
ap.add_argument("--base", default="BothBosu/distilbert-scam-classifier-v1.3")
ap.add_argument("--teacher", default="v2-teacher", help="teacher tag (checkpoint) for --role student")
ap.add_argument("--tag", default="v2-teacher")
ap.add_argument("--epochs", type=int, default=5)
ap.add_argument("--lr", type=float, default=3e-5)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--max_length", type=int, default=384)
ap.add_argument("--phone_ratio", type=float, default=0.35)
ap.add_argument("--tactic_weight", type=float, default=0.5)
ap.add_argument("--alpha", type=float, default=0.5, help="student: weight on hard labels vs teacher soft targets")
ap.add_argument("--temperature", type=float, default=2.0)
ap.add_argument("--export", action="store_true")
ap.add_argument("--seed", type=int, default=13)
args = ap.parse_args()
random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
dev = "cuda" if torch.cuda.is_available() else "cpu"
NT = len(TACTICS)


class TwoHead(nn.Module):
    """Shared encoder, a binary scam head and a tactic head, both on the [CLS] representation."""

    def __init__(self, base: str):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base)
        h = self.encoder.config.hidden_size
        self.drop = nn.Dropout(0.1)
        self.scam = nn.Linear(h, 2)
        self.tactic = nn.Linear(h, NT)

    def forward(self, input_ids, attention_mask):
        cls = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state[:, 0]
        cls = self.drop(cls)
        return self.scam(cls), self.tactic(cls)


def load_market(path: pathlib.Path):
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        li, s = r["listing"], r["seller"]
        listing = {"title": li.get("title", ""), "price": li.get("price") or 0, "ref_price": li.get("ref_price") or 0}
        seller = {"joined_days_ago": s.get("joined_days_ago") or 0, "completed_sales": s.get("completed_sales") or 0}
        y = 1 if r["label"] == "scam" else 0
        tac = TACTICS.index(TYPE_TO_TACTIC.get(r["type"], "none")) if y else 0
        out.append({"text": format_chat(listing, seller, r["chat"]), "y": y, "tactic": tac})
    return out


train_m = load_market(ROOT / "eval/data/train_chats.jsonl") + load_market(ROOT / "eval/data/train_hard_chats.jsonl")
val_m = load_market(ROOT / "eval/data/chats.jsonl")
phone = load_dataset("BothBosu/scam-dialogue")
phone_train = [{"text": f"[PHONE CALL]\n{r['dialogue']}", "y": int(r["label"]), "tactic": -100} for r in phone["train"]]
phone_test = [{"text": f"[PHONE CALL]\n{r['dialogue']}", "y": int(r["label"]), "tactic": -100} for r in phone["test"]]
random.shuffle(phone_train)
train = train_m + phone_train[:int(len(train_m) * args.phone_ratio)]
random.shuffle(train)
print(f"role={args.role} base={args.base} device={dev} | train {len(train_m)} marketplace + "
      f"{len(train) - len(train_m)} phone | dev {len(val_m)}", flush=True)

tok = AutoTokenizer.from_pretrained(args.base)
model = TwoHead(args.base).to(dev)

teacher_soft = None
if args.role == "student":
    tdir = ROOT / "models" / "checkpoints" / args.teacher
    ttok = AutoTokenizer.from_pretrained(tdir)
    tmodel = TwoHead(str(tdir / "encoder")).to(dev)
    tmodel.load_state_dict(torch.load(tdir / "heads_and_encoder.pt", map_location=dev))
    tmodel.eval()
    teacher_soft = {}
    with torch.no_grad():
        for i in range(0, len(train), 32):
            chunk = train[i:i + 32]
            enc = ttok([d["text"] for d in chunk], truncation=True, max_length=args.max_length, padding=True,
                       return_tensors="pt").to(dev)
            s, t = tmodel(enc["input_ids"], enc["attention_mask"])
            for d, sl, tl in zip(chunk, s.float().cpu(), t.float().cpu()):
                teacher_soft[d["text"]] = (sl, tl)
    del tmodel
    torch.cuda.empty_cache()
    print(f"teacher soft targets computed for {len(teacher_soft)} examples", flush=True)


def batches(data, shuffle):
    def collate(b):
        enc = tok([d["text"] for d in b], truncation=True, max_length=args.max_length, padding=True, return_tensors="pt")
        enc["y"] = torch.tensor([d["y"] for d in b])
        enc["tactic"] = torch.tensor([d["tactic"] for d in b])
        if teacher_soft is not None and all(d["text"] in teacher_soft for d in b):  # training batches only
            enc["ts"] = torch.stack([teacher_soft[d["text"]][0] for d in b])
            enc["tt"] = torch.stack([teacher_soft[d["text"]][1] for d in b])
        return enc
    return DataLoader(data, batch_size=args.batch, shuffle=shuffle, collate_fn=collate)


@torch.no_grad()
def predict(data):
    model.eval(); ps, ts = [], []
    for b in batches(data, False):
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=dev == "cuda"):
            s, t = model(b["input_ids"].to(dev), b["attention_mask"].to(dev))
        ps.append(torch.softmax(s.float(), -1)[:, 1].cpu().numpy()); ts.append(t.float().argmax(-1).cpu().numpy())
    return np.concatenate(ps), np.concatenate(ts)


def evaluate(name, data):
    p, t = predict(data)
    y = np.array([d["y"] for d in data]); tac = np.array([d["tactic"] for d in data])
    m = {"roc_auc": round(float(roc_auc_score(y, p)), 3), "pr_auc": round(float(average_precision_score(y, p)), 3)}
    scam_mask = (y == 1) & (tac >= 0)
    if scam_mask.any():
        m["tactic_accuracy"] = round(float((t[scam_mask] == tac[scam_mask]).mean()), 3)
    print(f"  {name:22s} " + " ".join(f"{k}={v}" for k, v in m.items()), flush=True)
    return m, p


def kl(student_logits, teacher_logits, T):
    return F.kl_div(F.log_softmax(student_logits / T, -1), F.softmax(teacher_logits / T, -1), reduction="batchmean") * T * T


opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
steps = args.epochs * len(batches(train, True))
sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)
scaler = torch.cuda.amp.GradScaler(enabled=dev == "cuda")
best, best_state, t0 = -1.0, None, time.time()
for ep in range(args.epochs):
    model.train(); losses = []
    for b in batches(train, True):
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=dev == "cuda"):
            s, t = model(b["input_ids"].to(dev), b["attention_mask"].to(dev))
            y, tac = b["y"].to(dev), b["tactic"].to(dev)
            hard = F.cross_entropy(s.float(), y)
            tac_loss = F.cross_entropy(t.float(), tac, ignore_index=-100) if (tac >= 0).any() else s.sum() * 0
            loss = hard + args.tactic_weight * tac_loss
            if "ts" in b:
                ts, tt = b["ts"].to(dev), b["tt"].to(dev)
                soft = kl(s.float(), ts, args.temperature)
                mask = tac >= 0
                soft_t = kl(t.float()[mask], tt[mask], args.temperature) if mask.any() else s.sum() * 0
                loss = args.alpha * loss + (1 - args.alpha) * (soft + args.tactic_weight * soft_t)
        opt.zero_grad(); scaler.scale(loss).backward(); scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(opt); scaler.update(); sched.step(); losses.append(loss.item())
    m, _ = evaluate(f"epoch {ep + 1} dev", val_m)
    score = m["roc_auc"] + 0.25 * m.get("tactic_accuracy", 0)  # both heads matter; scam ranking first
    print(f"epoch {ep + 1}: loss {np.mean(losses):.4f} | select {score:.3f} | {time.time() - t0:.0f}s", flush=True)
    if score > best:
        best, best_state = score, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
model.load_state_dict(best_state)
print("best epoch on dev:", flush=True)
dev_m, _ = evaluate("dev marketplace", val_m)
phone_m, _ = evaluate("phone test", phone_test)
n_params = sum(p.numel() for p in model.parameters())
report = {"role": args.role, "base_model": args.base, "teacher": args.teacher if args.role == "student" else None,
          "args": vars(args), "dev_marketplace": dev_m, "phone_test": phone_m, "params_millions": round(n_params / 1e6, 1),
          "train_seconds": int(time.time() - t0), "n_train_marketplace": len(train_m)}
out_dir = ROOT / "models" / args.tag
out_dir.mkdir(parents=True, exist_ok=True)

ck = ROOT / "models" / "checkpoints" / args.tag
ck.mkdir(parents=True, exist_ok=True)
model.encoder.save_pretrained(ck / "encoder"); tok.save_pretrained(ck)
torch.save(model.state_dict(), ck / "heads_and_encoder.pt")

if args.export:
    from onnxruntime.quantization import QuantType, quantize_dynamic
    model.eval().to("cpu").float()
    dummy = tok("hello world", return_tensors="pt")
    fp32 = out_dir / "model.fp32.onnx"
    torch.onnx.export(model, (dummy["input_ids"], dummy["attention_mask"]), str(fp32),
                      input_names=["input_ids", "attention_mask"], output_names=["logits", "tactic_logits"],
                      dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"},
                                    "logits": {0: "b"}, "tactic_logits": {0: "b"}}, opset_version=17)
    quantize_dynamic(str(fp32), str(out_dir / "model.int8.onnx"), weight_type=QuantType.QInt8)
    fp32.unlink()
    tok.backend_tokenizer.save(str(out_dir / "tokenizer.json"))
    meta = {"name": args.tag, "base_model": args.base, "role": args.role, "teacher": report["teacher"],
            "threshold": 0.5, "max_length": args.max_length, "tactics": TACTICS, "params_millions": report["params_millions"],
            "trained_on": {"marketplace": len(train_m), "phone_dialogues": len(train) - len(train_m),
                           "sources": ["eval/data/train_chats.jsonl", "eval/data/train_hard_chats.jsonl",
                                       "BothBosu/scam-dialogue (Apache-2.0)"]}}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    report["onnx_int8_mb"] = round((out_dir / "model.int8.onnx").stat().st_size / 1e6, 1)
    print(f"exported {out_dir / 'model.int8.onnx'} ({report['onnx_int8_mb']} MB)", flush=True)
(out_dir / "training_report.json").write_text(json.dumps(report, indent=2))
