"""Central configuration for the Merge Studio web app (Stage 1).

Everything is driven by environment variables so the same image runs locally
and on a server. Storage is a local directory here; Stage 2 swaps it for S3/R2
by re-implementing storage.py behind the same interface.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Root for all runtime data (job DB + per-job uploads/work/output).
# On a server, mount a volume here (e.g. DATA_DIR=/data).
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data")).expanduser()
JOBS_DIR = DATA_DIR / "jobs"
DB_PATH = DATA_DIR / "jobs.db"
SECRET_FILE = DATA_DIR / ".secret"

# Optional shared password (HTTP Basic Auth). Empty = gate disabled (local dev).
# Set ACCESS_PASSWORD to protect a public trial deployment.
ACCESS_PASSWORD = os.environ.get("ACCESS_PASSWORD", "123456")

# Limits / lifetimes.
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "500")) * 1024 * 1024
DOWNLOAD_TTL_SECONDS = int(os.environ.get("DOWNLOAD_TTL_SECONDS", "3600"))
JOB_RETENTION_SECONDS = int(os.environ.get("JOB_RETENTION_SECONDS", str(24 * 3600)))
WORKER_POLL_SECONDS = float(os.environ.get("WORKER_POLL_SECONDS", "1.0"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _load_secret_key() -> bytes:
    """Shared secret for signing download URLs.

    Prefer the SECRET_KEY env var (set this in production). Otherwise persist a
    random key under DATA_DIR so tokens survive restarts and are shared by the
    web + worker containers (they mount the same volume).
    """
    env = os.environ.get("SECRET_KEY")
    if env:
        return env.encode()
    if SECRET_FILE.exists():
        return SECRET_FILE.read_bytes()
    key = secrets.token_hex(32).encode()
    try:
        SECRET_FILE.write_bytes(key)
    except OSError:
        pass
    return key


SECRET_KEY = _load_secret_key()
