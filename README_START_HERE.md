# DR Screening Workstation Release

This package is a no-code Windows workstation release for public or approved
synthetic review. It is not a production or clinical deployment and does not
authorize hospital-data export, model use, training, or diagnosis.

## First run

1. Extract the complete `DR-Screening-Workstation-<version>.zip` to a local
   folder. Do not run it from inside the ZIP file.
2. Double-click `FIRST_RUN.bat` once while online. It provisions the project
   Python environment and installs locked workstation dependencies. It reuses
   the prebuilt frontend; the normal user does not run npm commands.
3. Use `CHECK_SYSTEM.bat` to see actionable readiness.
4. Use `START_DR_SCREENING.bat` to start the local workstation and open the
   browser at `http://127.0.0.1:8000/app/`.
5. Use `STOP_DR_SCREENING.bat` when finished.

## Safe boundaries

- The workstation runs with `APP_PROFILE=review`, `MODEL_RUNTIME=remote`, and
  binds to `127.0.0.1`.
- The frontend must already be present under `frontend/dist`; daily startup
  never installs or builds frontend dependencies.
- PostgreSQL is the normal case store. Set a private `DR_SUPPORT_DATABASE_URL`
  to use an external server, or leave it blank and let the launcher start the
  project-owned Docker PostgreSQL service. Generated local credentials stay in
  ignored `local-state/release/postgres.env`; the launcher never falls back to
  SQLite or prints the password.
- Private values such as `REMOTE_MODEL_URL` and `REMOTE_MODEL_TOKEN` belong in
  a local untracked `.env` or approved environment. Never commit them.
- Keep source images immutable and use only approved public or synthetic data.
- No model weights, patient data, runtime database, logs, or `local-state/`
  contents belong in the release archive.

## Model API package

`DR-Model-API-<version>.zip` is a contract-only package for later
Linux/GPU work. The current helper deliberately reports the runtime as
disabled; it does not download or load weights. The USPEC manifest records
expected identity only. P3.1 Runtime Qualification / Model Host Qualification
remains deferred and non-blocking.

## Recovery

- If first run fails, run `CHECK_SYSTEM.bat`, confirm approved internet access,
  and retry from an extracted folder.
- If startup reports that port 8000 is in use, inspect the reported process;
  the launcher does not kill unrelated processes.
- If PostgreSQL is not ready, start Docker Desktop for the managed local path,
  or correct the private external URL. `CHECK_SYSTEM.bat` reports the selected
  source and the credential-safe connectivity result.
- If the prebuilt frontend is missing, re-extract the release archive rather
  than installing frontend tooling on the workstation.

For operator details, read `docs/operations/INSTALLATION.md`,
`docs/operations/TROUBLESHOOTING.md`, and `docs/operations/SECURITY_PRIVACY.md`.
Milestone specifications and receipts under `docs/milestone/` are historical
evidence and remain authoritative for their recorded decisions; they are not
the daily operating guide.
