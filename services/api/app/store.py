"""Tiny document store on SQLite: collections of JSON documents keyed by id.

Enough for a prototype (sessions, leads, orders, consents) without an ORM; swapping
for Postgres means re-implementing these five functions.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import VAR_DIR

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_db_path: Path | None = None


def _connect() -> sqlite3.Connection:
    global _conn, _db_path
    if _conn is None:
        VAR_DIR.mkdir(parents=True, exist_ok=True)
        _db_path = VAR_DIR / "udyam.db"
        _conn = sqlite3.connect(_db_path, check_same_thread=False)
        _conn.execute("CREATE TABLE IF NOT EXISTS docs (collection TEXT, id TEXT, data TEXT, updated_at TEXT,"
                      " PRIMARY KEY (collection, id))")
        _conn.commit()
    return _conn


def use_memory() -> None:
    """Switch to an in-memory database (tests)."""
    global _conn
    with _lock:
        _conn = sqlite3.connect(":memory:", check_same_thread=False)
        _conn.execute("CREATE TABLE docs (collection TEXT, id TEXT, data TEXT, updated_at TEXT, PRIMARY KEY (collection, id))")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def put(collection: str, id: str, data: dict) -> None:
    with _lock:
        c = _connect()
        c.execute("INSERT OR REPLACE INTO docs VALUES (?, ?, ?, ?)", (collection, id, json.dumps(data, ensure_ascii=False), now()))
        c.commit()


def get(collection: str, id: str) -> dict | None:
    with _lock:
        row = _connect().execute("SELECT data FROM docs WHERE collection=? AND id=?", (collection, id)).fetchone()
    return json.loads(row[0]) if row else None


def all(collection: str) -> list[dict]:
    with _lock:
        rows = _connect().execute("SELECT data FROM docs WHERE collection=? ORDER BY updated_at DESC", (collection,)).fetchall()
    return [json.loads(r[0]) for r in rows]


def delete(collection: str, id: str) -> None:
    with _lock:
        c = _connect()
        c.execute("DELETE FROM docs WHERE collection=? AND id=?", (collection, id))
        c.commit()
