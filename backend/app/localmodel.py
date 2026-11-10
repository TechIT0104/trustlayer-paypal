"""Fine-tuned local scam classifier (DistilBERT -> ONNX int8), the third Pay-pause layer.

Why a local model next to rules and the LLM:
- It runs on CPU in tens of milliseconds with no API key, no rate limit and no network,
  so Pay-pause keeps a learned signal even when every hosted LLM is down or throttled.
- It is trained (models/train_scam_model.py) starting from BothBosu/distilbert-scam-classifier-v1.3,
  a public scam classifier trained on LLM-generated phone-scam dialogues (Apache-2.0), and fine-tuned
  on marketplace payment chats. Training and inference share `format_chat` below.

The model never pauses a payment on its own (it cannot cite evidence); it supports the rules and the LLM.
"""
import json
import pathlib
import threading

from . import config

MODEL_DIR = pathlib.Path(config.ROOT) / "models" / "scam-distilbert"
_lock = threading.Lock()
_state: dict = {"loaded": False, "session": None, "tokenizer": None, "meta": {}, "error": None}


def format_chat(listing: dict, seller: dict, messages: list[dict]) -> str:
    """Canonical text the model sees. Keep identical between training and serving."""
    price = float(listing.get("price") or 0)
    ref = float(listing.get("ref_price") or 0)
    ratio = f"{price / ref:.2f}" if ref > 0 else "unknown"
    head = (f"[LISTING] {listing.get('title', '')} | price {price:.0f} | typical {ref:.0f} | price ratio {ratio}\n"
            f"[SELLER] joined {seller.get('joined_days_ago', 0)} days ago | {seller.get('completed_sales', 0)} sales\n")
    body = "\n".join(f"{m.get('sender', 'unknown').upper()}: {m.get('text', '')}" for m in messages)
    return head + body


def _load() -> None:
    with _lock:
        if _state["loaded"]:
            return
        _state["loaded"] = True
        onnx_path = MODEL_DIR / "model.int8.onnx"
        if not onnx_path.exists():
            _state["error"] = "model file not found"
            return
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            _state["session"] = ort.InferenceSession(str(onnx_path), opts, providers=["CPUExecutionProvider"])
            tok = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
            meta = json.loads((MODEL_DIR / "meta.json").read_text(encoding="utf-8"))
            tok.enable_truncation(max_length=meta.get("max_length", 384))
            _state["tokenizer"], _state["meta"] = tok, meta
        except Exception as e:  # noqa: BLE001 - a missing optional dependency just disables this layer
            _state["error"] = f"{type(e).__name__}: {e}"


def available() -> bool:
    _load()
    return _state["session"] is not None


def info() -> dict:
    _load()
    meta = _state["meta"]
    return {"available": _state["session"] is not None, "error": _state["error"],
            "name": meta.get("name"), "base_model": meta.get("base_model"), "threshold": meta.get("threshold")}


def predict(listing: dict, seller: dict, messages: list[dict]) -> dict | None:
    """Returns {"p_scam": float, "threshold": float, "latency_ms": int, "model": str} or None if unavailable."""
    import time

    if not available():
        return None
    import numpy as np
    t0 = time.time()
    enc = _state["tokenizer"].encode(format_chat(listing, seller, messages))
    ids = np.array([enc.ids], dtype=np.int64)
    mask = np.array([enc.attention_mask], dtype=np.int64)
    logits = _state["session"].run(None, {"input_ids": ids, "attention_mask": mask})[0][0]
    e = np.exp(logits - logits.max())
    p = float(e[1] / e.sum())
    meta = _state["meta"]
    return {"p_scam": round(p, 4), "threshold": meta.get("threshold", 0.5), "latency_ms": int((time.time() - t0) * 1000),
            "model": meta.get("name", "scam-distilbert")}
