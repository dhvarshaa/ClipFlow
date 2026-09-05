"""Merge Studio web API (Stage 1).

Thin, non-blocking Flask app:
  POST /api/merge        -> save uploads, enqueue a job, return {job_id}
  GET  /api/job/<id>     -> job status/progress, plus a signed download_url when done
  GET  /api/download/<id>-> stream the finished MP4 (signed, expiring link)

The actual ffmpeg work happens in worker.py so requests never block on a render
(which would time out behind any real proxy). All heavy validation lives in
run_merge and surfaces through job status; here we only do cheap up-front checks.
"""

from __future__ import annotations

import hmac
import sys
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, send_from_directory

sys.path.insert(0, str(Path(__file__).resolve().parent / "colab"))
from merge_engine import (  # noqa: E402
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    normalize_output_name,
)

import config  # noqa: E402
import jobs  # noqa: E402
import storage  # noqa: E402

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES

jobs.init_db()


def _bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


@app.before_request
def _require_password():
    """Optional Basic-Auth gate for public deployments.

    Disabled unless ACCESS_PASSWORD is set, so local dev is unaffected. The
    health check stays open so uptime monitors don't need credentials.
    """
    if not config.ACCESS_PASSWORD or request.path == "/healthz":
        return None
    auth = request.authorization
    if auth and hmac.compare_digest(auth.password or "", config.ACCESS_PASSWORD):
        return None
    return Response(
        "Authentication required.",
        401,
        {"WWW-Authenticate": 'Basic realm="Merge Studio"'},
    )


def _err(message: str, code: int = 400):
    return jsonify({"error": message}), code


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/api/merge", methods=["POST"])
def merge():
    videos = [f for f in (request.files.getlist("videos") or []) if f and f.filename]
    single = request.files.get("video")
    if not videos and single and single.filename:
        videos = [single]
    image = request.files.get("image")
    audio = request.files.get("audio")

    has_videos = len(videos) > 0
    has_image = bool(image and image.filename)
    has_audio = bool(audio and audio.filename)

    duration_minutes = request.form.get("duration_minutes", "").strip()
    loop_count = request.form.get("loop_count", "").strip()
    output_name = request.form.get("output_filename", "").strip()
    loop_mode = request.form.get("loop_mode", "").strip() or None
    stitch = _bool(request.form.get("stitch"))
    keep_source_audio = _bool(request.form.get("keep_source_audio", "true"))
    mute = _bool(request.form.get("mute"))

    # --- cheap up-front validation (mirrors the frontend rules) ---
    if has_videos and has_image:
        return _err("Use either video(s) or a still image, not both.")
    if not has_videos and not has_image and not has_audio:
        return _err("Add video(s), a still image, or an audio file.")
    try:
        output_filename = normalize_output_name(output_name)
    except ValueError as exc:
        return _err(str(exc))
    if has_image and not has_audio and not duration_minutes:
        return _err("Provide a target duration when using only a still image.")
    single_only = (
        (len(videos) == 1 and not has_audio) or (has_audio and not has_videos and not has_image)
    ) and not has_image
    if single_only and not duration_minutes and not loop_count:
        return _err("Provide target duration or loop count for a single file.")
    if len(videos) == 1 and has_audio and not loop_mode:
        return _err("Choose whether to loop video, audio, or both.")
    if stitch and len(videos) < 2:
        return _err("Add at least two videos to stitch.")

    # --- persist uploads for the worker ---
    job_id = uuid.uuid4().hex
    uploads = storage.uploads_dir(job_id)
    try:
        saved_videos: list[str] = []
        for idx, file in enumerate(videos):
            ext = Path(file.filename).suffix.lower()
            if ext not in VIDEO_EXTENSIONS:
                raise ValueError(f"Unsupported video format: {ext}")
            name = f"video-{idx:03d}{ext}"
            file.save(uploads / name)
            saved_videos.append(name)

        image_name = None
        if has_image:
            ext = Path(image.filename).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                raise ValueError(f"Unsupported image format: {ext}")
            image_name = f"image{ext}"
            image.save(uploads / image_name)

        audio_name = None
        if has_audio:
            ext = Path(audio.filename).suffix.lower()
            if ext not in AUDIO_EXTENSIONS:
                raise ValueError(f"Unsupported audio format: {ext}")
            audio_name = f"audio{ext}"
            audio.save(uploads / audio_name)
    except ValueError as exc:
        storage.cleanup_job(job_id)
        return _err(str(exc))

    params = {
        "videos": saved_videos,
        "image": image_name,
        "audio": audio_name,
        "duration_minutes": duration_minutes,
        "loop_count": loop_count,
        "output_filename": output_filename,
        "loop_mode": loop_mode,
        "stitch": stitch,
        "keep_source_audio": keep_source_audio,
        "mute": mute,
    }
    jobs.create_job(job_id, params, output_filename)

    return jsonify(
        {"job_id": job_id, "status": jobs.QUEUED, "status_url": f"/api/job/{job_id}"}
    ), 202


@app.route("/api/job/<job_id>")
def job_status(job_id: str):
    job = jobs.get_job(job_id)
    if not job:
        return _err("Job not found.", 404)
    resp = {
        "job_id": job_id,
        "status": job["status"],
        "message": job["message"],
        "filename": job["output_name"],
        "duration_seconds": job["duration_seconds"],
        "error": job["error"],
    }
    if job["status"] == jobs.DONE:
        resp["download_url"] = storage.signed_download_url(job_id)
    return jsonify(resp)


@app.route("/api/download/<job_id>")
def download(job_id: str):
    if not storage.verify_token(job_id, request.args.get("exp"), request.args.get("token")):
        return _err("Invalid or expired download link.", 403)
    job = jobs.get_job(job_id)
    if not job or job["status"] != jobs.DONE:
        return _err("Output not ready.", 404)
    output = storage.find_output(job_id)
    if not output or not output.exists():
        return _err("Output file is no longer available.", 404)
    return send_file(
        str(output),
        as_attachment=True,
        download_name=job["output_name"] or output.name,
    )


if __name__ == "__main__":
    # Local dev convenience: run a worker in-process so a single command works.
    # Under gunicorn (production) this block does not run; use the worker service.
    import worker

    worker.start_background_worker()
    print(f"Merge Studio on http://127.0.0.1:5050  ·  storage: {config.DATA_DIR}")
    app.run(host="127.0.0.1", port=5050, debug=True, use_reloader=False)
