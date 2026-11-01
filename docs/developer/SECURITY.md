# Security and privacy

Retinal Review Workbench is a research and clinician-support proof of concept. Human review is
authoritative. It makes no claim of autonomous diagnosis or referral, regulatory approval, clinical
validation or calibrated probabilities.

## Rules

- **Images.** Originals are never moved, renamed, rewritten or deleted; the app stores references, hashes
  and derived analysis lineage. Only public or consented images may go to the team server dr-train; real
  hospital use runs on the hospital package inside the hospital network.
- **Model payload.** Image bytes and contract identifiers go to the configured Model API only when inference
  is requested. Local paths, patient resolver fields, OCR fields and raw DICOM headers are not sent. DICOM
  ingestion exposes only the safe technical metadata allowlist.
- **Secrets.** `REMOTE_MODEL_TOKEN`, `CVAT_TOKEN`, database URLs, personal tokens and SSH keys stay
  server-side in private configuration or a secret manager. Never in React, browser storage, SQLite, logs,
  screenshots, chat or committed files. Rotate a credential immediately if it leaks.
- **Git.** No secrets, PHI, model weights, runtime databases or `local-state/` contents. Owner's private
  material lives outside the repository (and `.archives/` is ignored).
- **Network.** Bind the review app to localhost unless a controlled network requires otherwise. Keep the
  Model API on a protected LAN or behind TLS and authentication; never expose port 7860 to the internet.
  Preserve SSH host-key and TLS verification.
- **Provenance.** Model revisions, checkpoint hashes, image and analysis SHA-256 and annotation provenance
  are shown read-only. They establish lineage, not accuracy.
- **Incidents.** If PHI or a secret is committed, logged or exported: stop distribution, record the incident,
  rotate the secret and remove the artifact from release outputs. Rewriting Git history does not replace
  rotation.

## Audit of 31 October 2026

Read-only review of `main` (`41c8603`) and `feat/phase1-finish`, then fixes merged in `110b47e`. Scope:
secrets, sign-in and roles, data leaving the app, the dr-train gateway, launchers, Docker packages. Clinical
semantics and model identities were not changed.

### Fixed

| # | Finding | Fix |
| --- | --- | --- |
| 1 | Physicians and experts could change the AI server address at runtime | `PUT /v1/model-connection` and its test are administrator-only when sign-in is on |
| 2 | Referral webhook could send any server environment variable as its token | token variable names must start with `REFERRAL_`; checked again before sending |
| 3, 19 | Referral webhook and drop folder could point anywhere | operator lists webhook hosts in `DR_SUPPORT_REFERRAL_HOSTS` and the drop root in `DR_SUPPORT_REFERRAL_DROP_ROOT`; UNC paths refused |
| 6 | Every role except researcher could create, edit or delete Workspaces | create, edit, delete and folder pickers are administrator-only |
| 9 | A nurse could overwrite or un-sign a signed report | only a signing role amends a signed report; the signed version is kept in `amended_versions` |
| 10 | Researcher accounts could read patient name and HN | researchers are refused `/v1/referrals*` and screening reports |
| 12 | Personal tokens could reach any gateway GET path and PRISM control without the workstation check | personal tokens reach only the service paths; PRISM prepare, grant and cancel need an allowed workstation |
| 13 | Revoking a personal token needed a gateway restart | the principals file is reread when it changes |
| 20 | Sending a referral held the case lock during the network call | the call runs outside the lock |
| 22, 23 | Last administrator could be demoted; a reset re-enabled a disabled account; a new password left other sign-ins active | all three fixed |
| 24, 25 | Accounts, server-mode, connector and principals files used the default file mode | written 0600 through one helper |
| 26, 27 | Launcher settings went into ssh and a remote shell unchecked | `DR_HOST`, `DR_KEY` and remote paths validated |
| 28 | Personal accounts (`command=/bin/false`) failed the launcher's SSH check | exit code 1 accepted in personal mode |
| 32 | CSV guard missed tab, CR and pipe | covered |
| 36 | Behind the HTTPS front the app saw `http` while the browser sent `https` | `FORWARDED_ALLOW_IPS` set for the review container in both packages |
| 4 (part) | Model API example bound to every address with the token optional | example binds 127.0.0.1 and the token is required |

Tests: `test_pilot_auth`, `test_referral_outbox`, `test_screening_report`, `test_server_mode`,
`test_regular_service`, plus the deployment and demo script tests.

### Open

| # | Finding | Why open / next step |
| --- | --- | --- |
| 4 | Model API serves without a token when `REMOTE_MODEL_TOKEN` is unset | refusing to start changes the model server contract; owner decision |
| 5 | Public-folder demo mode labels any folder as public | needs a signed public manifest or an allow list; the operator is the owner today |
| 7 | No Host check in no-sign-in mode (DNS rebinding on a workstation) | add a trusted-host list; affects every local launcher |
| 8 | `APP_PROFILE=full` (dev only) drops the sign-in middleware | fix the profile merge; never used for real data |
| 11 | Patient name and HN are plain text in case JSON and backups | backup encryption and file mode; field encryption needs a design |
| 14 | Model traffic may use plain http between hosts | allow http only to loopback or tunnels |
| 15 | No global login rate limit | per-address limit and a cap on the failure table |
| 16, 17 | Model containers run as root; the app uses the database superuser | non-root images; least-privilege database role |
| 21 | Session cookie has no `Secure` flag | set it when served over HTTPS |
| 29 to 31, 33 | Error text with paths, server-side folder picker, unbounded admission reads, model API body limit | hardening items |
| 34 | Owner username and paths in examples | owner to decide |
| 37 | With sign-in off, anyone can sign under a typed name | deployments run with sign-in; label or refuse later |
| 12 (part) | PRISM jobs are not bound to the person who prepared them | job ids are random; binding needs a gateway change |

### Closed by the owner (1 November 2026)

18 (`HN5071` in old receipts and tests) and 35 (team portraits): the owner confirmed consent was obtained for
all of them; kept as they are.

### Checked and fine

Password hashing (PBKDF2, 310k iterations), session cookie flags, admin route checks, CSRF coverage with
sign-in on, SQL parameters, `torch.load(weights_only=True)`, no shell subprocesses, HTML escaping on the
print page, request body limit on the review API, origin gates for CVAT and model calls, loopback port
bindings in Compose, read-only image mounts, no secrets or private keys in tracked files.
