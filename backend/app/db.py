"""Tiny SQLite layer. One file, no ORM, safe for FastAPI's threadpool."""
import json
import sqlite3
import threading
import time

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS sellers (
    id TEXT PRIMARY KEY, name TEXT, handle TEXT, paypal_email TEXT,
    joined_days_ago INTEGER, completed_sales INTEGER, rating REAL,
    location TEXT, policy_json TEXT
);
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY, seller_id TEXT, title TEXT, category TEXT,
    price REAL, ref_price REAL, description TEXT, emoji TEXT, condition TEXT,
    fulfil_json TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id TEXT, sender TEXT,
    text TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, listing_id TEXT, seller_id TEXT, amount REAL,
    status TEXT, paypal_order_id TEXT, authorization_id TEXT, capture_id TEXT,
    captured_amount REAL DEFAULT 0, refunded_amount REAL DEFAULT 0,
    payout_batch_id TEXT, payout_amount REAL DEFAULT 0,
    risk_json TEXT, hold_until REAL, trusted_contact TEXT, contact_token TEXT,
    contact_verdict TEXT, seller_protection TEXT, fee REAL DEFAULT 0,
    shipped_days_ago INTEGER, promised_days INTEGER, delivered_days_ago INTEGER,
    created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS issues (
    id TEXT PRIMARY KEY, order_id TEXT, status TEXT, transcript_json TEXT,
    offer_json TEXT, outcome_json TEXT, created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS seller_daily (
    seller_id TEXT, day INTEGER, orders INTEGER, disputes INTEGER,
    refunds INTEGER, gross REAL, prevented INTEGER DEFAULT 0,
    PRIMARY KEY (seller_id, day)
);
CREATE TABLE IF NOT EXISTS kv (
    k TEXT PRIMARY KEY, v TEXT
);
CREATE TABLE IF NOT EXISTS offerings (
    id TEXT PRIMARY KEY, seller_id TEXT, name TEXT, description TEXT, price REAL, trial_days INTEGER,
    benefits_json TEXT, review_json TEXT, status TEXT, created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY, plan_id TEXT, status TEXT, started_at REAL, trial_ends_at REAL,
    next_billing_at REAL, price REAL, clock_offset REAL DEFAULT 0, reminder_json TEXT,
    cancel_reason TEXT, cancelled_at REAL, paypal_json TEXT, created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, type TEXT, order_id TEXT,
    seller_id TEXT, data_json TEXT, prev_hash TEXT, hash TEXT
);
"""


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.executescript(SCHEMA)
            for table, col, typ in MIGRATIONS:  # additive, idempotent column migrations
                try:
                    _conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                except sqlite3.OperationalError:
                    pass
            _conn.commit()
        return _conn


MIGRATIONS = [
    ("orders", "payout_status", "TEXT"),
    ("orders", "auth_expires", "TEXT"),
    ("orders", "authorized_at", "REAL"),
    ("subscriptions", "offering_id", "TEXT"),
    ("subscriptions", "seller_id", "TEXT"),
    ("subscriptions", "uses", "INTEGER DEFAULT 0"),
]


def all(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, params).fetchall()]


def one(sql: str, params: tuple = ()) -> dict | None:
    with _lock:
        row = conn().execute(sql, params).fetchone()
        return dict(row) if row else None


def run(sql: str, params: tuple = ()) -> int:
    with _lock:
        cur = conn().execute(sql, params)
        conn().commit()
        return cur.lastrowid


def update(table: str, key: str, key_value, **fields) -> None:
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k} = ?" for k in fields)
    run(f"UPDATE {table} SET {cols} WHERE {key} = ?", (*fields.values(), key_value))


def loads(value: str | None, default=None):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def reset() -> None:
    with _lock:
        c = conn()
        for table in ("sellers", "listings", "messages", "orders", "issues", "seller_daily", "events", "subscriptions",
                      "offerings"):
            c.execute(f"DELETE FROM {table}")
        c.execute("DELETE FROM sqlite_sequence")
        c.commit()
