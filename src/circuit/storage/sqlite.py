from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/circuit.db")

_conn: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    global _conn

    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row

    return _conn


def init_db() -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            request_id TEXT PRIMARY KEY,
            timestamp TEXT,
            provider TEXT,
            model TEXT,
            status_code INTEGER,
            latency_ms INTEGER,
            tokens_input INTEGER,
            tokens_output INTEGER,
            cost_usd REAL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS quota_usage (
            client_key_hash TEXT,
            date TEXT,
            usd_spent REAL,
            PRIMARY KEY (client_key_hash, date)
        )
        """
    )

    conn.commit()


def record_request(
    *,
    request_id: str,
    timestamp: str,
    provider: str,
    model: str,
    status_code: int,
    latency_ms: int,
    tokens_input: Optional[int],
    tokens_output: Optional[int],
    cost_usd: Optional[float],
) -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO requests (
            request_id,
            timestamp,
            provider,
            model,
            status_code,
            latency_ms,
            tokens_input,
            tokens_output,
            cost_usd
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            timestamp,
            provider,
            model,
            status_code,
            latency_ms,
            tokens_input,
            tokens_output,
            cost_usd,
        ),
    )

    conn.commit()


def get_daily_spend(client_key_hash: str, date: str) -> float:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT usd_spent FROM quota_usage
        WHERE client_key_hash = ? AND date = ?
        """,
        (client_key_hash, date),
    )

    row = cursor.fetchone()
    return row["usd_spent"] if row else 0.0


def add_spend(client_key_hash: str, date: str, amount: float) -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO quota_usage (client_key_hash, date, usd_spent)
        VALUES (?, ?, ?)
        ON CONFLICT(client_key_hash, date)
        DO UPDATE SET usd_spent = usd_spent + ?
        """,
        (client_key_hash, date, amount, amount),
    )

    conn.commit()