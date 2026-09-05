"""Render worker (Stage 1).

Polls the SQLite job store, claims the next queued job, runs the ffmpeg merge,
and records the result. Run as a separate process in production
(``python worker.py``); ``start_background_worker`` runs it as a daemon thread
for local single-command dev (``python app.py``).
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "colab"))
from merge_engine import run_merge  # noqa: E402

import config  # noqa: E402
import jobs  # noqa: E402
import storage  # noqa: E402


def process_job(job: dict) -> None:
    job_id = job["id"]
    params = json.loads(job["params_json"])
    uploads = storage.uploads_dir(job_id)

    video_paths = [str(uploads / name) for name in params.get("videos", [])]
    image_path = str(uploads / params["image"]) if params.get("image") else None
    audio_path = str(uploads / params["audio"]) if params.get("audio") else None

    try:
        last_write = [0.0]
        last_pct = [-1.0]

        def on_progress(pct: float, message: str) -> None:
            now = time.time()
            # Throttle DB writes; always flush near the end.
            if pct - last_pct[0] < 0.5 and now - last_write[0] < 0.5 and pct < 99:
                return
            last_write[0] = now
            last_pct[0] = pct
            msg = message or f"Rendering… {pct:.0f}%"
            if message and "%" not in message:
                msg = f"{message} {pct:.0f}%"
            jobs.set_progress(job_id, pct, msg)

        result = run_merge(
            video_paths=video_paths or None,
            image_path=image_path,
            audio_path=audio_path,
            output_folder=str(storage.output_dir(job_id)),
            output_name=params["output_filename"],
            loop_mode=params.get("loop_mode") or None,
            loop_count=params.get("loop_count") or None,
            duration_minutes=params.get("duration_minutes") or None,
            stitch=params.get("stitch", False),
            keep_source_audio=params.get("keep_source_audio", True),
            mute=params.get("mute", False),
            resolution=params.get("resolution") or None,
            fps=params.get("fps") or None,
            quality=params.get("quality") or None,
            aspect=params.get("aspect") or None,
            fit=params.get("fit") or None,
            trims=params.get("trims") or None,
            progress_callback=on_progress,
            work_dir=str(storage.work_dir(job_id)),
        )
        jobs.mark_done(
            job_id,
            result.get("duration_seconds"),
            f"Rendered {result.get('filename')}",
        )
    except Exception as exc:  # surfaced to the user via job status
        jobs.mark_error(job_id, str(exc))
    finally:
        storage.cleanup_transient(job_id)


def _purge_expired() -> None:
    cutoff = time.time() - config.JOB_RETENTION_SECONDS
    for job_id in jobs.expired_job_ids(cutoff):
        storage.cleanup_job(job_id)
        jobs.delete_job(job_id)


def work_loop(stop_event: threading.Event | None = None) -> None:
    jobs.init_db()
    last_purge = 0.0
    while stop_event is None or not stop_event.is_set():
        try:
            job = jobs.claim_next_job()
        except Exception:
            job = None
        if job:
            process_job(job)
            continue

        now = time.time()
        if now - last_purge > 300:
            last_purge = now
            try:
                _purge_expired()
            except Exception:
                pass
        time.sleep(config.WORKER_POLL_SECONDS)


def start_background_worker() -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()
    thread = threading.Thread(target=work_loop, args=(stop_event,), daemon=True)
    thread.start()
    return stop_event, thread


if __name__ == "__main__":
    print(f"Render worker started. Storage: {config.DATA_DIR}. Polling for jobs…")
    work_loop()
