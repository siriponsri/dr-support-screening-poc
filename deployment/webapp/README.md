# Package 1: DR Screening web app (Docker)

The review web app with its PostgreSQL database and an HTTPS front. The AI
model server is reached by URL: the hospital model server (package 2) or the
team server through a route the hospital approved. Without a model server the
app still works for manual review; AI shows as not available.

Screening and research support only; not a diagnostic device.

## What runs

| Service | Image | Purpose |
| --- | --- | --- |
| `review` | `dr-screening/review` (built from `deployment/dual-mode/Dockerfile.review`) | web app and API, sign-in required |
| `postgres` | `postgres:16-alpine` | cases, reviews, annotations |
| `https` | `caddy:2.8-alpine` | HTTPS on port 443 with an internal certificate |

Folders on the host: `config` (accounts file), `state`, `output` (exports and
grade folders), and the image folder, mounted read-only so originals are never
changed.

## Windows (Docker Desktop), one click

1. Install Docker Desktop and start it.
2. Copy `webapp.env.example` to `%LOCALAPPDATA%\DRScreening\webapp.env` and
   replace every `REPLACE` value.
3. Double-click `start-webapp.bat`. It starts the services, waits, and opens
   `https://localhost/app/`. `stop-webapp.bat` stops them; data is kept.
4. First time only: create the administrator account (Git Bash):
   `DR_ENV_FILE="$LOCALAPPDATA/DRScreening/webapp.env" deployment/webapp/bin/create-admin.sh admin`

The browser warns about the internal certificate the first time; trust it or
install Caddy's root certificate from the `dr_screening_webapp_caddy` volume.

## Linux server

```bash
sudo mkdir -p /etc/dr-screening && sudo cp deployment/webapp/webapp.env.example /etc/dr-screening/webapp.env
sudo chmod 600 /etc/dr-screening/webapp.env   # then edit: replace every REPLACE value
deployment/webapp/bin/start.sh                 # start and wait until it answers
deployment/webapp/bin/create-admin.sh admin    # first time only
deployment/webapp/bin/backup.sh                # database backup (add to cron)
deployment/webapp/bin/stop.sh                  # stop; data is kept
```

The container runs as user 10001: on Linux, make the data folders writable for
that user (`sudo chown -R 10001 <DR_DATA_DIR>`).

## No internet in the hospital network

On a machine with internet: `bin/save-images.sh` builds and saves the images
to one file and prints its SHA-256. Copy the file and this repository folder,
then on the server: `bin/load-images.sh <file> <sha256>` and `bin/start.sh`.

## Update and rollback

Set a new `DR_SCREENING_IMAGE_TAG` and `DR_SCREENING_SOURCE_COMMIT`, build or
load the new image, run `bin/start.sh`. To roll back, set the previous tag and
run `bin/start.sh` again. Take a backup first; the database schema only moves
forward.
