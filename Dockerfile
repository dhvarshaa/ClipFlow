# Merge Studio image — Python + ffmpeg. Used by both the web and worker
# services (they run different commands from the same image).
FROM python:3.12-slim

# ffmpeg is a system binary the app shells out to; it must be in the image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# All runtime data (job DB + media) lives here — mount a volume in production.
ENV DATA_DIR=/data
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 5050

# Default to the web tier; the worker service overrides the command.
CMD ["gunicorn", "-c", "gunicorn_conf.py", "app:app"]
