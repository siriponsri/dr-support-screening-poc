# Package 2: hospital local server (Docker, GPU)

Everything inside the hospital network: the web app, PostgreSQL, the model
gateway, the three GPU model services (USPEC for UWF grading, RETFound for CFP
grading, PRISM for lesions) and an HTTPS front. Images never leave the hospital
and normal operation needs no internet.

Screening and research support only; not a diagnostic device.

## Requirements

- Ubuntu Server 22.04 or 24.04, Docker Engine with the Compose plugin, NVIDIA
  driver and NVIDIA Container Toolkit. The administrator adds the service
  account to the `docker` group.
- One GPU with 16 GB or more (24 GB recommended), 12 to 16 CPU cores, 64 GB RAM,
  a 1 TB system disk and a separate data disk. See
  `docs/planning/PHASE1_ALL_IN_ONE_PLAN_20261031.md` section 5.3.
- Verified model assets on the server (they are not in the images or in Git).
  The services check them against the pinned hashes at start and refuse to run
  otherwise.

## Install

```bash
sudo mkdir -p /etc/dr-screening /srv/dr-screening/{data,images,models}
sudo cp deployment/hospital-server/hospital.env.example /etc/dr-screening/hospital.env
sudo chmod 600 /etc/dr-screening/hospital.env   # then edit: replace every REPLACE value
sudo chown -R 10001 /srv/dr-screening/data      # the web app container user
deployment/hospital-server/bin/start.sh         # preflight checks, then start everything
deployment/hospital-server/bin/create-admin.sh admin
deployment/hospital-server/bin/status.sh
```

Users open `https://<DR_SITE_ADDRESS>/app/` from hospital PCs. Containers
restart by themselves after a reboot.

## Operate

| Task | Command |
| --- | --- |
| Health | `bin/status.sh` |
| Backup (nightly via cron) | `bin/backup.sh` |
| Stop (data kept) | `bin/stop.sh` |
| Update | new image tag and source commit in the env file, then `bin/start.sh` |
| Roll back | previous tag in the env file, then `bin/start.sh` |

Offline install: build and save images on a machine with internet
(`docker compose ... build` then `docker save`), copy them with their SHA-256,
`docker load` on the server. The web app images can use
`deployment/webapp/bin/save-images.sh`.

## Status

The model services and gateway come from `deployment/dual-mode`, exercised in a
synthetic-only smoke on one Tesla T4. This package has not yet run on a
hospital GPU server; run it on the target hardware with public or consented
images before real use.
