# DR Screening Windows workstation

Use **START_DR_SCREENING.bat** each day and **STOP_DR_SCREENING.bat** when
finished. START opens **http://127.0.0.1:8000/app/**. Run START again to reopen
the same managed workstation; it does not create a second server.

This is a research and clinician-support POC. Human review remains authoritative.
AI output is assistance, not a confirmed clinical decision or a calibrated
probability. Private hospital evaluation requires explicit authorization and
passing the private-root gate. Hospital dataset export remains blocked.

## First setup

For an extracted workstation release, double-click **FIRST_RUN.bat** once while
online, then **CHECK_SYSTEM.bat**. First run provisions project-managed Python
and locked dependencies using the prebuilt frontend. Daily START does not run
package installation, Git updates or frontend builds. For a developer checkout,
use the setup commands in `docs/operations/INSTALLATION.md`; the operator must
build `frontend/dist` for the current frontend sources before delivery.

## Local data and persistence

The normal entrypoint runs the Review UI/API on this Windows computer. Source
images remain in their original folders and are read without rewriting them.
An operator may bind both authorized UWF and CFP roots with the server-only
`DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS` JSON configuration. This creates one
mixed-modality queue, retaining hospital provenance. On Windows, admission
requires readable ACLs restricted to the workstation operator, SYSTEM and local
Administrators; redirected paths or other access grants fail closed. The app
does not change ACLs automatically. Do not bypass a failed privacy check.

PostgreSQL stores review state locally when the checkout-owned Docker service is
selected. A configured external PostgreSQL URL is verified and used as supplied.
The launcher never silently substitutes SQLite or a different database. STOP
preserves the database volume, source images and private settings, and does not
stop external databases or Lightning services. Keep TEST_ONLY engineering work
separate from genuine clinician-confirmed work.

The current machine's actual source, database, test results and remaining actions
are recorded privately in `local-state/local-handoff/LOCAL_WINDOWS_HANDOFF.md`
when this checkout has been prepared by the operator. Read its status before a
demo; a reachable UI alone does not prove that image admission or AI works.

## Separate remote AI and remote browser access

The Windows workstation uses `APP_PROFILE=review`, `MODEL_RUNTIME=remote`, and
loopback binding. It does not need local model weights or a workstation GPU.
`REMOTE_MODEL_URL` must point to an authenticated private **model gateway**, not
the Review `/app/` page. Keep tokens server-side in private configuration. The
existing Lightning gateway and Unified Review deployment have their own runbook
in `deployment/lightning-native/README.md`; this workstation launcher neither
starts nor changes those services. The separate contract-only Model API release
ZIP is not evidence of the running Lightning service's readiness.

Remote browser fallback opens a Review service running on Lightning through an
authorized private transport. Its queue and database are on Lightning. It cannot
read Windows image folders automatically, and its success does not validate the
local image workflow. Do not publish the Review or model ports to the internet.
Preserve SSH host verification and TLS verification.

Without a reachable compatible model capability, manual review remains available.
CHECK_SYSTEM reports this as manual mode; it is not a successful inference test.
No AI result must be replaced with Grade 0 or a negative lesion finding.

## Recovery

- Run **CHECK_SYSTEM.bat** for readiness. For missing Python in an extracted
  release, rerun **FIRST_RUN.bat**.
- If port 8000 is occupied, inspect the reported PID and executable. The launcher
  does not kill unrelated processes.
- For checkout-owned PostgreSQL, start Docker Desktop and rerun START. For an
  external database, have the operator repair the configured connection.
- For a missing or stale frontend, rebuild in a developer checkout or re-extract
  the complete release. Daily START verifies the existing bundle and never runs
  npm.
- Keep private `.env`, `local-state/`, model weights, images, patient filenames,
  logs and database backups out of Git and release archives.

Operator details: `docs/operations/INSTALLATION.md`,
`docs/operations/TROUBLESHOOTING.md`, and `docs/operations/SECURITY_PRIVACY.md`.
Frozen milestone requirements remain authoritative for their recorded scope.
