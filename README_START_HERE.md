# DR Screening Windows workstation

Research and clinician-support software; not a diagnostic device. Human review is authoritative. AI output
is assistance, not a confirmed clinical decision or a calibrated probability.

## First setup

Double-click **FIRST_RUN.bat** once while online, then **CHECK_SYSTEM.bat**. First run installs the
project-managed Python and locked dependencies and uses the prebuilt web app.

## Every day

- **START_DR_SCREENING.bat** opens **http://127.0.0.1:8000/app/**. Running it again reopens the same app; it
  does not start a second server.
- **STOP_DR_SCREENING.bat** when finished. Data, images and private settings are kept.
- **BACKUP_DR_SCREENING.bat** and **RESTORE_DR_SCREENING.bat** for recovery
  (`docs/developer/BACKUP_RESTORE.md`).

## Data

Source images stay in their own folders and are never rewritten. Review data is stored in PostgreSQL: a
project-owned Docker database when no external database URL is configured, or the configured external
database. The launcher never falls back to SQLite or another database. Keep TEST_ONLY engineering work
separate from real clinician work.

## AI

The workstation needs no GPU or model weights. `REMOTE_MODEL_URL` in the private settings points to an
authenticated model gateway; tokens stay server-side. Without a reachable model, manual review remains
available and CHECK_SYSTEM reports manual mode. A missing AI result is never shown as Grade 0 or "no
lesions". Do not publish the review or model ports to the internet.

## If something is wrong

- Run **CHECK_SYSTEM.bat**. If Python is missing, rerun **FIRST_RUN.bat**.
- Port 8000 busy: the launcher reports the process using it and never kills unrelated programs.
- Database not ready: start Docker Desktop and rerun START, or ask the operator to fix the external database.
- Web app missing or stale: re-extract the complete release. START never runs npm.
- Keep the private `.env`, `local-state/`, model weights, images, patient file names, logs and backups out of
  Git and out of release archives.

Settings reference: `docs/developer/CONFIGURATION.md`. Security: `docs/developer/SECURITY.md`.
