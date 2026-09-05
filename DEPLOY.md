# Deploying Merge Studio

This app has two parts that run together:

- **web** – the site + API (accepts uploads, hands back a job, serves the finished file)
- **worker** – does the actual ffmpeg rendering in the background

They share a data folder (a small SQLite job list + the media files). ffmpeg runs
on the server, so wherever you deploy, ffmpeg must be present — the Docker image
already includes it.

---

## 1. Run locally (single command)

```bash
python3 app.py
```

Open http://127.0.0.1:5050. Running `app.py` directly starts the web server **and**
a background worker in the same process, so it behaves like a normal single-user tool.
Finished videos are offered via a **Download** button when the render completes
(data lives in `./data/`).

---

## 2. Try it publicly for free — local machine + a tunnel

Keep the app running locally and expose it with a free tunnel (no server needed).
Good for quick "test from my phone / share with a friend" sessions. Your Mac does
the rendering, and the link only works while the app is running.

**Cloudflare Tunnel:**
```bash
# install once: brew install cloudflared
python3 app.py            # in one terminal
cloudflared tunnel --url http://localhost:5050   # in another — prints a public https URL
```

**ngrok (alternative):** `ngrok http 5050` (free account required).

---

## 3. Deploy on Google Cloud (using the $300 / 90-day free trial)

Use a **Compute Engine VM** (a plain Linux server). Cloud Run is *not* suitable here
because it drops background work and doesn't keep files between runs.

### 3.1 Start the trial
Sign up at cloud.google.com and activate the free trial ($300 for 90 days). A card is
required for identity, but Google does **not** auto-charge when the trial ends — you'd
have to manually upgrade. So there's no surprise bill.

### 3.2 Create the VM
Compute Engine → **VM instances** → **Create instance**:
- **Machine type:** `e2-standard-2` (2 vCPU, 8 GB) to start; `e2-standard-4` for faster renders.
- **Boot disk:** Ubuntu 22.04 LTS, ~30 GB.
- **Firewall:** tick **Allow HTTP traffic**.
- Create it, then copy the **External IP**.

### 3.3 Get the code onto the VM
Click **SSH** on the VM row to open a browser terminal, then either:
```bash
git clone <your-repo-url> app        # if you push this project to GitHub
```
or, from your Mac (requires the gcloud CLI):
```bash
gcloud compute scp --recurse "/Users/varsha/Desktop/YT automation" VM_NAME:~/app
```

### 3.4 Install Docker and launch
In the VM's SSH terminal:
```bash
curl -fsSL https://get.docker.com | sh
cd ~/app

# serve on the normal web port 80 instead of 5050:
sed -i 's/"5050:5050"/"80:5050"/' docker-compose.yml

# keep download links valid across restarts + protect the trial with a password:
export SECRET_KEY="a-long-random-string"
export ACCESS_PASSWORD="pick-a-password"

sudo -E docker compose up --build -d
```

### 3.5 Open it
Visit **http://EXTERNAL_IP** in a browser. If you set `ACCESS_PASSWORD`, it prompts for
a login (any username, that password).

Handle more simultaneous renders by adding workers:
```bash
sudo docker compose up -d --scale worker=3
```

---

## 4. Settings (environment variables)

| Variable            | Default | Purpose                                                        |
|---------------------|---------|----------------------------------------------------------------|
| `SECRET_KEY`        | random  | Signs download links; set a fixed value in production.         |
| `ACCESS_PASSWORD`   | *(off)* | If set, the whole site requires this password (Basic Auth).    |
| `MAX_UPLOAD_MB`     | 500     | Max upload size per request.                                   |
| `DATA_DIR`          | ./data  | Where the job list + media live (mount a volume in production).|
| `DOWNLOAD_TTL_SECONDS` | 3600 | How long a download link stays valid.                          |
| `JOB_RETENTION_SECONDS`| 86400| How long finished jobs/files are kept before auto-cleanup.     |
| `WEB_CONCURRENCY`   | 2       | Web server processes (gunicorn).                               |

---

## 5. Keeping the $300 credit from draining

- **e2-standard-2** ≈ $0.07/hr ≈ ~$50/month → ~5–6 months on the credit.
- **e2-standard-4** ≈ $0.13/hr ≈ ~$97/month → ~3 months on the credit.

Tips:
- **Stop (don't delete) the VM when not testing** — stopped VMs don't bill for compute.
  Compute Engine → select VM → **Stop** / **Start**.
- **Set a budget alert:** Billing → Budgets & alerts → create a budget (e.g. $50) with email alerts.
- **Delete the VM** when finished exploring to stop all charges.
- Since it's public, keep the upload cap and the `ACCESS_PASSWORD` on so strangers
  can't burn credit rendering videos.

### Teardown
```bash
sudo docker compose down          # stop the app
```
Then in the console: **Stop** (pause, cheap) or **Delete** (remove, no charge) the VM.

---

## 6. Later: scaling to thousands (Stage 2 — not needed yet)

When the render queue is consistently busy, swap the built-in pieces for scalable ones:
- **Queue:** Redis + RQ/Celery with an autoscaling worker pool (replaces `jobs.py`).
- **Storage:** Cloudflare R2 or S3 + CDN, presigned URLs (replaces `storage.py`).
- Add hardware-accelerated encoding, user accounts, quotas, and rate limits.

`jobs.py` and `storage.py` were written as the swap points, so this is a change of
backend, not a rewrite.
