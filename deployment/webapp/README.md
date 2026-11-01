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

## Windows (Docker Desktop): setup in one double-click

1. Install Docker Desktop and start it (wait until it says Running).
2. Double-click `SETUP_WEB_APP.bat` in the project folder. It asks two questions (image folder, AI server
   address or Enter for none), makes the private settings file
   `%LOCALAPPDATA%\DRScreening\webapp.env` with random passwords, builds and starts the app, asks for the
   first administrator account, puts **DR Screening Web App** on the desktop and opens
   `https://localhost/app/`.
3. Next time: the desktop button (`start-webapp.bat`). `stop-webapp.bat` stops the app; data is kept.

Running setup again is safe: the settings file and existing accounts are kept. The browser warns about the
certificate the first time because it is made on this computer.

Manual route (or Linux): copy `webapp.env.example` to a private file, replace every `REPLACE` value, then
`bin/start.sh` and `bin/create-admin.sh admin`.

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
