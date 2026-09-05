"""SQLite-backed job store (Stage 1).

A single SQLite file on a shared volume is enough for the first few hundred
users. It survives restarts and works across separate web + worker processes
via ``BEGIN IMMEDIATE`` for atomic claiming. Stage 2 replaces this module with
Redis + RQ/Celery behind the same function names.
"""

from __future__ import annotations

import json
import sqlite3
import time

import config

QUEUED = "queued"
PROCESSING = "processing"
DONE = "done"
ERROR = "error"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id               TEXT PRIMARY KEY,
                status           TEXT NOT NULL,
                params_json      TEXT NOT NULL,
                output_name      TEXT,
                message          TEXT,
                error            TEXT,
                duration_seconds REAL,
                created_at       REAL,
                started_at       REAL,
                finished_at      REAL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);")


def create_job(job_id: str, params: dict, output_name: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, status, params_json, output_name, message, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, QUEUED, json.dumps(params), output_name, "Queued", time.time()),
        )


def get_job(job_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def claim_next_job() -> dict | None:
    """Atomically move the oldest queued job to ``processing`` and return it."""
    conn = _connect()
    conn.isolation_level = None  # manual transaction control
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at LIMIT 1",
            (QUEUED,),
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        conn.execute(
            "UPDATE jobs SET status = ?, started_at = ?, message = ? WHERE id = ?",
            (PROCESSING, time.time(), "Processing", row["id"]),
        )
        conn.execute("COMMIT")
        return dict(row)
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def set_message(job_id: str, message: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE jobs SET message = ? WHERE id = ?", (message, job_id))


def mark_done(job_id: str, duration_seconds: float | None, message: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, duration_seconds = ?, message = ?, "
            "error = NULL, finished_at = ? WHERE id = ?",
            (DONE, duration_seconds, message, time.time(), job_id),
        )


def mark_error(job_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, error = ?, message = ?, finished_at = ? WHERE id = ?",
            (ERROR, error, "Failed", time.time(), job_id),
        )


def expired_job_ids(cutoff_ts: float) -> list[str]:
    """Finished jobs older than the cutoff, safe to purge."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id FROM jobs WHERE status IN (?, ?) AND finished_at IS NOT NULL "
            "AND finished_at < ?",
            (DONE, ERROR, cutoff_ts),
        ).fetchall()
    return [r["id"] for r in rows]


def delete_job(job_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
