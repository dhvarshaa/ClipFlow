"""Storage + signed URLs (Stage 1: local filesystem).

Per-job layout under DATA_DIR/jobs/<job_id>/:
    uploads/   raw uploaded media (deleted after render)
    work/      ffmpeg scratch space (deleted after render)
    output/    final MP4 (kept until retention cleanup)

``signed_download_url`` emulates an object-store presigned URL with an
HMAC-signed, expiring token. Stage 2 re-implements these functions to put
media in S3/R2 and return real presigned URLs — callers stay unchanged.
"""

from __future__ import annotations

import hashlib
import hmac
import shutil
import time
from pathlib import Path

import config


def job_root(job_id: str) -> Path:
    return config.JOBS_DIR / job_id


def _sub(job_id: str, name: str) -> Path:
    path = job_root(job_id) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def uploads_dir(job_id: str) -> Path:
    return _sub(job_id, "uploads")


def work_dir(job_id: str) -> Path:
    return _sub(job_id, "work")


def output_dir(job_id: str) -> Path:
    return _sub(job_id, "output")


def find_output(job_id: str) -> Path | None:
    out = output_dir(job_id)
    files = [f for f in out.iterdir() if f.is_file()]
    return files[0] if files else None


# ---------- signed download URLs ----------
def _signature(job_id: str, expires: int) -> str:
    msg = f"{job_id}:{expires}".encode()
    return hmac.new(config.SECRET_KEY, msg, hashlib.sha256).hexdigest()


def signed_download_url(job_id: str) -> str:
    expires = int(time.time()) + config.DOWNLOAD_TTL_SECONDS
    token = _signature(job_id, expires)
    return f"/api/download/{job_id}?exp={expires}&token={token}"


def verify_token(job_id: str, expires: str | int | None, token: str | None) -> bool:
    if not token or expires is None:
        return False
    try:
        expires_int = int(expires)
    except (TypeError, ValueError):
        return False
    if time.time() > expires_int:
        return False
    return hmac.compare_digest(_signature(job_id, expires_int), token)


# ---------- cleanup ----------
def cleanup_transient(job_id: str) -> None:
    """Remove uploads + scratch once a render finishes; keep the output."""
    shutil.rmtree(job_root(job_id) / "uploads", ignore_errors=True)
    shutil.rmtree(job_root(job_id) / "work", ignore_errors=True)


def cleanup_job(job_id: str) -> None:
    shutil.rmtree(job_root(job_id), ignore_errors=True)
