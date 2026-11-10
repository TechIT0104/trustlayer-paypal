"""Append-only, SHA-256 hash-chained event ledger.

Every money movement and every AI decision is written here with the PayPal IDs it
produced, so the whole history can be audited and any tampering is detectable.
"""
import hashlib
import json
import threading
import time

from . import db

_lock = threading.Lock()
GENESIS = "0" * 64


def _digest(prev_hash: str, ts: float, etype: str, order_id, seller_id, data_json: str) -> str:
    payload = json.dumps([prev_hash, round(ts, 6), etype, order_id, seller_id, data_json], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def append(etype: str, data: dict | None = None, order_id: str | None = None, seller_id: str | None = None) -> dict:
    with _lock:
        last = db.one("SELECT hash FROM events ORDER BY seq DESC LIMIT 1")
        prev = last["hash"] if last else GENESIS
        ts = time.time()
        data_json = json.dumps(data or {}, sort_keys=True, default=str)
        h = _digest(prev, ts, etype, order_id, seller_id, data_json)
        seq = db.run(
            "INSERT INTO events (ts, type, order_id, seller_id, data_json, prev_hash, hash) VALUES (?,?,?,?,?,?,?)",
            (ts, etype, order_id, seller_id, data_json, prev, h),
        )
        return {"seq": seq, "hash": h}


def verify() -> dict:
    rows = db.all("SELECT * FROM events ORDER BY seq")
    prev = GENESIS
    for r in rows:
        expected = _digest(prev, r["ts"], r["type"], r["order_id"], r["seller_id"], r["data_json"])
        if r["prev_hash"] != prev or r["hash"] != expected:
            return {"ok": False, "count": len(rows), "broken_at": r["seq"], "type": r["type"]}
        prev = r["hash"]
    return {"ok": True, "count": len(rows), "head": prev}


def recent(limit: int = 200, order_id: str | None = None) -> list[dict]:
    if order_id:
        rows = db.all("SELECT * FROM events WHERE order_id = ? ORDER BY seq DESC LIMIT ?", (order_id, limit))
    else:
        rows = db.all("SELECT * FROM events ORDER BY seq DESC LIMIT ?", (limit,))
    for r in rows:
        r["data"] = db.loads(r.pop("data_json"), {})
    return rows
