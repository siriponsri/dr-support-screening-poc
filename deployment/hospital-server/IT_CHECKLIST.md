# DR Screening hospital server: IT checklist

One Linux server inside the hospital network runs the whole DR Screening system: the web app, its
PostgreSQL database, three AI model services on one NVIDIA GPU and an HTTPS front. Retinal images never
leave the hospital and normal operation needs no internet. Doctors use it from hospital PCs in a browser.

Screening and research support only; not a diagnostic device. The doctor's grade is always the final one.

## 1. Hardware

| Item | Minimum | Recommended |
| --- | --- | --- |
| GPU | NVIDIA GeForce RTX 3090, 24 GB (see note) | same |
| CPU | 8 cores, x86_64 (Intel/AMD) | 12 to 16 cores |
| RAM | 32 GB | 64 GB |
| System disk | SSD with 200 GB free for the system and Docker images | 1 TB SSD, RAID 1 if possible |
| Data disk (separate) | 1 TB | 4 TB or more |
| Backup | a separate disk or NAS at least the size of the data disk | same, off the server |
| Power | UPS | UPS |

GPU note, stated honestly:

- The start check (`deployment/dual-mode/bin/preflight.sh`) of the hospital profile accepts only an
  **NVIDIA RTX 3090** (compute capability 8.6) and refuses other cards. A different card (for example
  NVIDIA L4 or RTX A5000) needs a new profile qualified by the DR Screening team before installing.
- GPU memory need: about 2.8 GB was measured with the graders and PRISM loaded together in one process
  on the team server. Here the three models run as three separate containers on the same GPU, each with
  its own CUDA memory overhead; that total has **not been measured**. The same three-container setup
  passed a synthetic test on a 16 GB-class card (Tesla T4, 15 GB). So 16 GB is the lowest tested size
  and the 24 GB of an RTX 3090 leaves room.
- This package has **not yet run on an RTX 3090** or on a hospital server. Run it with public or
  consented test images first.

Disk sizes: an Optos JPEG is a few MB, an Optos DICOM can be 20 to 35 MB. The app also keeps analysis
copies and exports, so plan the data disk at several times the size of the image archive.

## 2. Software

- Ubuntu Server 22.04 or 24.04 LTS, 64-bit (x86_64).
- NVIDIA driver installed and working (`nvidia-smi` shows the card). Install it before the DR Screening
  installer: `sudo apt-get update && sudo ubuntu-drivers install`, then restart.
- Docker Engine with the Compose plugin, and the NVIDIA Container Toolkit. The installer offers to
  install both from the official Docker and NVIDIA repositories (it asks first, you type `yes`; this
  needs internet). Without internet, install them from your own repository mirror beforehand.

## 3. Network and ports

| Port | Open to | Purpose |
| --- | --- | --- |
| 443/TCP inbound | hospital LAN only | HTTPS web app for doctors' browsers |
| everything else | not opened | database, model gateway and model services listen on 127.0.0.1 only |

- Never open port 443 to the internet.
- Docker opens port 443 itself through iptables, so a `ufw` rule on the server alone does **not**
  limit it. Limit it with the hospital network firewall (allow only the hospital LAN ranges).
- Outbound internet is needed only while installing Docker or building images. Normal operation and the
  offline bundle need none.
- Users type one address: a DNS name you create (for example `dr-screening.<hospital-domain>`) or the
  server's fixed IP address. The installer asks for it.
- HTTPS uses a certificate made on the server (internal certificate authority). The installer saves the
  root certificate to `<data folder>/dr-screening-https-root.crt`; install it on hospital PCs as a trusted
  root (for example by group policy) so browsers do not warn.

## 4. What to prepare

- [ ] The server with Ubuntu, the NVIDIA driver and (optionally) Docker and the Toolkit.
- [ ] The offline bundle from the DR Screening team: `dr-screening-hospital-<tag>.tar` and
      `dr-screening-hospital-<tag>.tar.sha256` (made with `bin/make-offline-bundle.sh` on a machine with
      internet).
- [ ] The AI model files, delivered separately by the DR Screening team (they are not in the bundle and
      not in Git). See section 6.
- [ ] The address users will type (DNS name or fixed IP).
- [ ] Three folders, ideally on the data disk: images (the app only reads it), data, model files.
      Defaults: `/srv/dr-screening/images`, `/srv/dr-screening/data`, `/srv/dr-screening/models`.
- [ ] A username for the first administrator (the temporary password is typed during install and
      changed at the first sign-in).

## 5. Install: three commands

In the folder where you copied the two bundle files:

```bash
sha256sum -c dr-screening-hospital-<tag>.tar.sha256
sudo tar --no-same-owner -xf dr-screening-hospital-<tag>.tar -C /opt
sudo bash /opt/dr-screening-hospital-<tag>/dr-screening/deployment/hospital-server/install.sh
```

The installer:

1. checks the server (Ubuntu, GPU model, driver, Docker, Compose, Toolkit, RAM, CPU, free disk, port 443)
   and prints a plain fix for anything missing;
2. asks four questions (address, images folder, data folder, model files folder), each with a default;
3. writes the private settings file `/etc/dr-screening/hospital.env` (root only, mode 600) with database
   password and model token made on the server; they are never shown;
4. checks every bundle file against its checksum and loads the images (or, from a Git copy with
   internet, builds them), then checks that containers can use the GPU;
5. checks the model files against the pinned versions, starts everything and waits until it is healthy;
6. asks for the first administrator (password typing is hidden), offers a nightly backup and prints
   the web address.

If the model files are not in place yet, the installer stops after step 4 and tells you what is missing;
copy them and run the same command again. Running it again is always safe: the settings file and
existing accounts are kept.

With internet and Git instead of the bundle: `git clone` the project, then
`sudo bash deployment/hospital-server/install.sh` (it builds the images; 20 to 40 minutes).

## 6. Model files

Copy them into the model files folder (default `/srv/dr-screening/models`) exactly as delivered:

| Path | Content |
| --- | --- |
| `uspec/` | USPEC folder: `manifest.json`, `grading_state.pt` and its four source files |
| `PRISM-DR/` | PRISM-DR source: a full git clone (with `.git`) at the pinned revision, unmodified |
| `prism/` | PRISM-DR released weights (the `Final Models` tree) with its `manifest.json` |
| `RETFound/` | RETFound source: a full git clone (with `.git`) at the pinned revision, unmodified |
| `retfound-aptos.pth` | RETFound APTOS checkpoint file |

They are checked by the program's own verification (`python -m dr_support.setup_models --verify`,
run by the installer and again by each model service at every start): git revision and checkpoint
SHA-256 for RETFound (`dr_support/providers/retfound.py`), git revision and the SHA-256 of all 21 weight
files for PRISM-DR (`dr_support/providers/prism.py`, `dr_support/providers/prism_assets.json`), and the
SHA-256 of the manifest, checkpoint and source files for USPEC (`dr_support/models/uspec_artifact.py`).
A model service refuses to start when a file is missing or changed. Files are mounted read-only.

## 7. After install

- Open `https://<address>/app/` from a hospital PC, sign in as the administrator and choose a new password.
- Add the doctors' accounts on the Admin page.
- In the app, the images folder appears as `/data/input`. The app reads only the top level of the folder
  chosen as a workspace input (files in sub-folders are ignored) and never changes the originals.

## 8. Daily operation

All commands as root, from `/opt/dr-screening-hospital-<tag>/dr-screening/deployment/hospital-server`:

| Task | Command |
| --- | --- |
| Health | `sudo sh bin/status.sh` |
| Stop (data kept) | `sudo sh bin/stop.sh` |
| Start again | `sudo sh bin/start.sh` (containers also restart by themselves after a reboot) |
| Backup now | `sudo sh bin/backup.sh` |
| Reset an account password | `sudo sh bin/create-admin.sh <username>` |

## 9. Backup

- The installer offers a nightly database backup at 02:30 (`/etc/cron.d/dr-screening-backup`). It keeps
  the last 14 dumps in `<data folder>/backups`. Log: `/var/log/dr-screening-backup.log`.
- Copy these to the backup disk or NAS every night: `<data folder>/backups/`, `<data folder>/config/`
  (accounts, hashed passwords), `<data folder>/output/` (exports). The image folder is the hospital's
  own archive; back it up as you already do.
- Keep a copy of `/etc/dr-screening/hospital.env` in a secured place: it holds the database password.
- Restore (not yet rehearsed; rehearse once on a test server): stop the web app, then
  `docker compose ... exec -T postgres pg_restore -U dr_support -d dr_support --clean < <file>.dump`
  with the same `-f` and `--env-file` options that `bin/backup.sh` uses.

## 10. Update and roll back

- Update: copy the new bundle, check and unpack it next to the old one (commands 1 and 2), run its
  `install.sh` and type `yes` when it offers the update. It takes a database backup first, loads the new
  images, keeps settings and accounts, and restarts. The database schema only moves forward.
- Roll back: run the previous bundle's `install.sh` and type `yes`. If the newer version already changed
  the database, also restore the backup taken before the update.

## 11. Not yet tested

- No run on an RTX 3090 or any hospital server; the GPU memory total of the three containers is unmeasured.
- The offline bundle, the installer and the restore procedure have not been run end to end. Rehearse on a
  test server with public or synthetic images before real use.
