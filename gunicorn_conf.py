"""Gunicorn config for the web tier.

The web process is I/O-bound (uploads/downloads + quick DB writes); the heavy
ffmpeg work runs in the separate worker service, so a small worker count with
threads is plenty. Tune via env: WEB_CONCURRENCY, WEB_THREADS, WEB_TIMEOUT, PORT.
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5050')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("WEB_THREADS", "4"))
# Generous timeout so large uploads/downloads aren't cut off (renders are async).
timeout = int(os.environ.get("WEB_TIMEOUT", "300"))
accesslog = "-"
errorlog = "-"
