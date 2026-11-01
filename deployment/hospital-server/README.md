# Package 2: hospital local server (Docker, GPU)

Everything inside the hospital network: the web app, PostgreSQL, the model
gateway, the three GPU model services (USPEC for UWF grading, RETFound for CFP
grading, PRISM for lesions) and an HTTPS front. Images never leave the hospital
and normal operation needs no internet.

Screening and research support only; not a diagnostic device.

## Install (hospital IT, no coding)

Read [IT_CHECKLIST.md](IT_CHECKLIST.md) first (hardware, ports, what to prepare). Then, on the server:

```bash
sha256sum -c dr-screening-hospital-<tag>.tar.sha256
sudo tar --no-same-owner -xf dr-screening-hospital-<tag>.tar -C /opt
sudo bash /opt/dr-screening-hospital-<tag>/dr-screening/deployment/hospital-server/install.sh
```

`install.sh` checks the server and prints plain fixes, asks four questions,
writes the private settings file `/etc/dr-screening/hospital.env` (mode 600,
passwords made on the server and never shown), loads the images, checks the
model files against the pinned versions, starts everything, creates the first
administrator and prints the web address. Running it again is safe and also
updates to a newer bundle.

From a Git copy with internet, run `sudo bash deployment/hospital-server/install.sh`
in the project folder instead; it builds the images.

## Make the offline bundle (DR Screening team, machine with internet)

```bash
bash deployment/hospital-server/bin/make-offline-bundle.sh <output-folder>
```

It exports the current commit, builds and saves every image the hospital
profile needs (for linux/amd64), and writes one `.tar` with a checksum
manifest inside and a `.sha256` beside it. Model weights are not included;
hand them over separately (layout in IT_CHECKLIST.md, section 6).

## Requirements

- Ubuntu Server 22.04 or 24.04, NVIDIA driver, Docker Engine with the Compose
  plugin and NVIDIA Container Toolkit (the installer can install the last two).
- The hospital profile's start check accepts only an NVIDIA RTX 3090. 12 to 16
  CPU cores, 64 GB RAM, a 1 TB system disk and a separate data disk are
  recommended. See IT_CHECKLIST.md (the original sizing note is kept in Git tag
  `archive/docs-before-cut-20261101`).
- Verified model assets on the server (they are not in the images or in Git).
  The services check them against the pinned hashes at start and refuse to run
  otherwise.

## Operate

| Task | Command |
| --- | --- |
| Health | `sudo sh bin/status.sh` |
| Backup (nightly via cron, offered by the installer) | `sudo sh bin/backup.sh` |
| Stop (data kept) | `sudo sh bin/stop.sh` |
| Update | new bundle, then its `install.sh` (answer `yes` to the update) |
| Roll back | previous bundle's `install.sh`; restore the pre-update backup if the schema changed |

## Manual route

```bash
sudo mkdir -p /etc/dr-screening /srv/dr-screening/{data,images,models}
sudo cp deployment/hospital-server/hospital.env.example /etc/dr-screening/hospital.env
sudo chmod 600 /etc/dr-screening/hospital.env   # then edit: replace every REPLACE value
sudo chown -R 10001 /srv/dr-screening/data      # the web app container user
sudo sh deployment/hospital-server/bin/start.sh         # preflight checks, then start everything
sudo sh deployment/hospital-server/bin/create-admin.sh admin
sudo sh deployment/hospital-server/bin/status.sh
```

Users open `https://<DR_SITE_ADDRESS>/app/` from hospital PCs. Containers
restart by themselves after a reboot.

## Status

The model services and gateway come from `deployment/dual-mode`, exercised in a
synthetic-only smoke on one Tesla T4. This package, the installer and the
offline bundle have not yet run on a hospital GPU server; run them on the
target hardware with public or consented images before real use.
