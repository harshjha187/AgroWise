"""
AgroWise — Database Layer (SQLite)
============================================================
Stores every analyzed reading (including soil moisture) and
every generated alert. SQLite ships with Python, so there is
nothing to install and the database file (agrowise.db) is
created automatically on first run next to this file.

If an older database from v1 (no moisture columns) is found,
init_db() migrates it in-place by ADD COLUMNing the missing
moisture fields — old readings get NULL moisture and are
still displayed / exported.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional

# Defaults to a file next to this module (unchanged local-dev behavior).
# Override for deployments where the data directory is a mounted volume
# (e.g. Docker) rather than the backend/ source folder itself.
DB_PATH = Path(os.environ.get("AGROWISE_DB_PATH") or (Path(__file__).resolve().parent / "agrowise.db"))
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       INTEGER NOT NULL,              -- epoch milliseconds
    n_raw    REAL, p_raw REAL, k_raw REAL,
    m_raw    REAL,                          -- moisture raw (%)
    ph_raw   REAL, t_raw REAL,
    n        REAL, p REAL, k REAL,
    m        REAL,                          -- moisture filtered (%)
    ph       REAL, t REAL,                  -- noise-filtered
    sub_n    INTEGER, sub_p INTEGER, sub_k INTEGER,
    sub_m    INTEGER,                       -- moisture sub-score
    sub_ph   INTEGER, sub_t INTEGER,
    score    INTEGER NOT NULL,
    cls      TEXT NOT NULL,                 -- FERTILE / MODERATE / BARREN
    m_status TEXT,                          -- LOW / OPTIMAL / HIGH
    source   TEXT DEFAULT 'unknown',        -- ESP32 / SIM / MANUAL / MOBILE
    device_id TEXT DEFAULT 'default'        -- distinguishes multiple physical devices
);
CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings (ts);

CREATE TABLE IF NOT EXISTS alerts (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       INTEGER NOT NULL,
    level    TEXT NOT NULL,                 -- critical / warning / ok
    message  TEXT NOT NULL
);
"""

# Columns added in v2 — forward-migration for pre-moisture DBs
_V2_COLUMNS = [
    ("m_raw",    "REAL"),
    ("m",        "REAL"),
    ("sub_m",    "INTEGER"),
    ("m_status", "TEXT"),
]

# Columns added in v3 — forward-migration for pre-device-id DBs
_V3_COLUMNS = [
    ("device_id", "TEXT DEFAULT 'default'"),
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)
        # forward-migrate older databases
        cols = _existing_columns(conn, "readings")
        for name, dtype in _V2_COLUMNS:
            if name not in cols:
                conn.execute(f"ALTER TABLE readings ADD COLUMN {name} {dtype}")
        cols = _existing_columns(conn, "readings")
        for name, dtype in _V3_COLUMNS:
            if name not in cols:
                conn.execute(f"ALTER TABLE readings ADD COLUMN {name} {dtype}")


# ------------------------------------------------------------------
# Row <-> API shape helpers
# ------------------------------------------------------------------
def _row_to_reading(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "ts": row["ts"],
        "raw": {"n": row["n_raw"], "p": row["p_raw"], "k": row["k_raw"],
                "m": row["m_raw"], "ph": row["ph_raw"], "t": row["t_raw"]},
        "f":   {"n": row["n"], "p": row["p"], "k": row["k"],
                "m": row["m"], "ph": row["ph"], "t": row["t"]},
        "subs": {"n": row["sub_n"], "p": row["sub_p"], "k": row["sub_k"],
                 "m": row["sub_m"], "ph": row["sub_ph"], "t": row["sub_t"]},
        "score": row["score"],
        "cls": row["cls"],
        "moisture_status": row["m_status"],
        "source": row["source"],
        "device_id": row["device_id"],
    }


# ------------------------------------------------------------------
# Writes
# ------------------------------------------------------------------
def insert_reading(reading: dict) -> int:
    raw, f, subs = reading["raw"], reading["f"], reading["subs"]
    with _lock, _connect() as conn:
        cur = conn.execute(
            """INSERT INTO readings
               (ts, n_raw, p_raw, k_raw, m_raw, ph_raw, t_raw,
                n, p, k, m, ph, t,
                sub_n, sub_p, sub_k, sub_m, sub_ph, sub_t,
                score, cls, m_status, source, device_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (reading["ts"],
             raw["n"], raw["p"], raw["k"], raw["m"], raw["ph"], raw["t"],
             f["n"], f["p"], f["k"], f["m"], f["ph"], f["t"],
             subs["n"], subs["p"], subs["k"], subs["m"], subs["ph"], subs["t"],
             reading["score"], reading["cls"],
             reading.get("moisture_status"),
             reading.get("source", "unknown"),
             reading.get("device_id", "default")),
        )
        return cur.lastrowid


def insert_alerts(alerts: list[dict]) -> None:
    if not alerts:
        return
    with _lock, _connect() as conn:
        conn.executemany(
            "INSERT INTO alerts (ts, level, message) VALUES (?,?,?)",
            [(a["ts"], a["level"], a["message"]) for a in alerts],
        )


def clear_all() -> None:
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM readings")
        conn.execute("DELETE FROM alerts")


# ------------------------------------------------------------------
# Reads
# ------------------------------------------------------------------
def get_readings(limit: int = 200, device_id: Optional[str] = None) -> list[dict]:
    """Most recent `limit` readings in chronological (oldest-first) order,
    optionally scoped to a single device_id."""
    with _lock, _connect() as conn:
        if device_id:
            rows = conn.execute(
                "SELECT * FROM readings WHERE device_id = ? ORDER BY id DESC LIMIT ?",
                (device_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM readings ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return [_row_to_reading(r) for r in reversed(rows)]


def get_distinct_devices() -> list[str]:
    """Every device_id that has ever posted a reading, for populating a
    device filter/selector in the UI."""
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT device_id FROM readings WHERE device_id IS NOT NULL ORDER BY device_id"
        ).fetchall()
    return [r["device_id"] for r in rows]


def get_latest(device_id: Optional[str] = None) -> Optional[dict]:
    """Most recent reading, optionally scoped to one device_id. Scoping
    matters beyond just display: the EMA noise filter and BARREN-transition
    alerts both key off "the previous reading" — with multiple physical
    devices posting concurrently, that must be the same device's previous
    reading, not whichever device happened to post most recently overall."""
    with _lock, _connect() as conn:
        if device_id:
            row = conn.execute(
                "SELECT * FROM readings WHERE device_id = ? ORDER BY id DESC LIMIT 1",
                (device_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM readings ORDER BY id DESC LIMIT 1"
            ).fetchone()
    return _row_to_reading(row) if row else None


def get_alerts(limit: int = 30) -> list[dict]:
    """Most recent alerts, newest first."""
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_summary() -> dict:
    with _lock, _connect() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM readings").fetchone()["c"]
        avg = conn.execute("SELECT AVG(score) a FROM readings").fetchone()["a"]
        counts = {
            r["cls"]: r["c"]
            for r in conn.execute(
                "SELECT cls, COUNT(*) c FROM readings GROUP BY cls"
            ).fetchall()
        }
        moisture_counts = {
            (r["m_status"] or "UNKNOWN"): r["c"]
            for r in conn.execute(
                "SELECT m_status, COUNT(*) c FROM readings GROUP BY m_status"
            ).fetchall()
        }
    return {
        "total_readings": total,
        "avg_score": round(avg, 1) if avg is not None else None,
        "class_counts": {
            "FERTILE": counts.get("FERTILE", 0),
            "MODERATE": counts.get("MODERATE", 0),
            "BARREN": counts.get("BARREN", 0),
        },
        "moisture_counts": {
            "LOW": moisture_counts.get("LOW", 0),
            "OPTIMAL": moisture_counts.get("OPTIMAL", 0),
            "HIGH": moisture_counts.get("HIGH", 0),
        },
    }


def all_rows_for_export() -> list[sqlite3.Row]:
    with _lock, _connect() as conn:
        return conn.execute("SELECT * FROM readings ORDER BY id ASC").fetchall()
