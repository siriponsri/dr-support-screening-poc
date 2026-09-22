# S8 — Production & Deployment Hardening

Status: **prepared specification for Luna/Max to READ AND RE-WRITE against the final repository**.

## Goal

Turn DR Support Screening POC from a development repository into a clean, reproducible hospital-deployment candidate without expanding scientific scope.

S8 is not a model-research milestone. It is a release-engineering, deployment, documentation, and operator-experience milestone.

## Owner priorities

1. Professional repository with only files that serve the released system.
2. **Delete obsolete documentation; do not create `docs/archive/`.**
3. One-time online server setup; normal model inference should use verified local weights without internet.
4. Fast, explicit Model API startup and health checks.
5. Clean-clone installation and reboot/restart acceptance.
6. Reproducible clinician manual generated from Playwright screenshots and exported to PDF.
7. Final README with logo, architecture diagram, quick start, deployment model, safety boundary, and documentation links.

## Non-goals

Do not add:
- new grading/lesion models;
- fine-tuning;
- calibration claims;
- Grad-CAM/XAI;
- PACS/DICOMweb;
- new annotation semantics;
- new clinical claims;
- broad UI redesign unrelated to deployment blockers.

## S8A — Repository cleanup

### Method

Create an inventory first. Classify every root-level file, directory, and `docs/*` item as:

```text
KEEP
REWRITE
DELETE
UNKNOWN
```

Resolve `UNKNOWN` before deletion by checking imports, scripts, package metadata, tests, runtime references, and README links.

### Documentation policy

There is **no archive directory**.

Before deletion, extract any still-valid operational facts into the final documentation set. Then remove superseded milestone specs, handoffs, owner-audit notes, old deployment experiments, duplicate READMEs, smoke-result files, and planning documents that are no longer needed by operators or developers.

Likely deletion candidates include historical `S*` specs, `PRE_*`, `OWNER_*`, `BRIDGE_*`, superseded deployment docs, temporary smoke JSON, obsolete handoff/goal files, and duplicate frontend/root documentation — but S8 must verify references before deleting.

### Target release tree

```text
README.md
LICENSE
AGENTS.md                 # keep only if still useful to contributors/agents
CHANGELOG.md
.env.example
pyproject.toml
Dockerfile                # only if validated and used
START.cmd                 # clinician workstation entrypoint if retained

dr_support/
frontend/
scripts/
deployment/
docs/
tests/
```

Delete legacy `web/`, duplicate package surfaces, demo-only artifacts, or unused startup files only after proving they are no longer referenced.

## S8B — Model server bootstrap

Target: hospital Linux GPU server.

### One-time setup (internet allowed)

Provide a single documented setup path that:
- checks supported Python version;
- creates an isolated environment;
- installs runtime + model + DICOM dependencies;
- verifies NVIDIA/CUDA availability when GPU inference is expected;
- downloads RETFound and PRISM assets through the repository's existing setup mechanism;
- verifies pinned revision/checkpoint hashes;
- runs model-load and smoke inference checks;
- writes no token/secrets into repository files;
- ends with a clear `READY` or actionable failure.

Prefer a command similar to:

```bash
./scripts/model-server/setup.sh
```

S8 must rewrite the implementation to match the actual repository rather than blindly copying this draft command.

### Normal startup (internet not required)

Provide:

```bash
./scripts/model-server/start.sh
./scripts/model-server/healthcheck.sh
```

Normal startup must:
- load already-verified local assets;
- never silently download missing weights;
- fail clearly when an asset/hash is missing;
- expose the existing Model API contract;
- use explicit environment configuration;
- default to one worker for GPU model loading unless validated otherwise.

Expected runtime intent:

```text
APP_PROFILE=model_api
MODEL_RUNTIME=local
INFERENCE_DEVICE=cuda:0
WORKERS=1
```

Verify these names against the final code.

### Service management

For Linux deployment, provide an optional systemd unit and installation helper:

```text
deployment/dr-support-model-api.service
scripts/model-server/install-service.sh
```

Service acceptance includes start, stop, restart, boot enablement, logs, and health check.

## S8C — Clinician/review application deployment

Document the supported deployment topology clearly:
- clinician workstation/browser uses the `review` profile;
- model inference is remote through the provider-neutral Model API;
- local review must remain usable when the Model API is temporarily unavailable;
- model weights must not load on the clinician workstation;
- workspace/export storage location must be explicit and writable;
- secrets live in environment/config outside Git.

Preserve the existing Windows `START.cmd` only if it remains the validated simplest workstation entrypoint. Remove or rewrite it if S8 identifies a better authoritative launcher.

## S8D — Offline-readiness test

After successful online setup:
1. stop the Model API;
2. disable external internet access or simulate an offline environment;
3. restart the service;
4. verify `/health` and `/v1/models`;
5. run one RETFound prediction and one PRISM prediction using local assets;
6. verify no download attempt occurs;
7. verify logs contain no secrets or patient-identifying metadata.

CVAT Online is an optional external integration and is not required to function offline.

## S8E — Configuration, security, and privacy

Final docs must cover:
- environment variables and defaults;
- model-server URL/token handling;
- bind address/port;
- firewall/LAN expectations;
- filesystem paths and permissions;
- log location/rotation expectations;
- backup/restore of application state and exported datasets;
- DICOM PHI handling and safe metadata policy;
- no secret/token in code, screenshots, logs, or committed `.env`;
- public/synthetic fixtures for documentation and automated tests.

Do not claim regulatory approval or autonomous diagnosis. Preserve human-in-the-loop framing.

## S8F — Automated clinician manual

Create a Playwright-driven manual capture workflow using only public/synthetic data.

Recommended structure:

```text
scripts/manual/capture_manual.ts
scripts/manual/build_manual.py   # or a single Playwright/Node build path

docs/manual/screenshots/
docs/CLINICIAN_USER_MANUAL.md
docs/CLINICIAN_USER_MANUAL.pdf
```

Required capture principles:
- deterministic demo workspace;
- fixed desktop viewport; optional mobile appendix;
- no tokens, real PHI, local usernames, or sensitive paths;
- wait for stable UI state before capture;
- crop/annotate only when needed;
- regenerate screenshots from the final release, not from stale images.

Suggested clinician manual journey:
1. start/open application;
2. create/select workspace;
3. scan/add retinal images;
4. inspect Worklist;
5. link patient and confirm eye;
6. open Review;
7. run AI analysis;
8. toggle/filter PRISM lesion overlays and read confidence score;
9. record clinician decision;
10. use CVAT only when dense annotation is needed;
11. review Dataset status;
12. export dataset;
13. inspect Models & Audit.

PDF should be produced automatically from the final manual HTML/Markdown using a reproducible local toolchain.

## S8G — Final documentation set

At release, keep only documentation that an operator, clinician, installer, or contributor actually needs.

Recommended final set:

```text
docs/INSTALLATION.md
docs/DEPLOYMENT.md
docs/MODEL_SERVER.md
docs/OPERATOR_RUNBOOK.md
docs/CONFIGURATION.md
docs/SECURITY_PRIVACY.md
docs/BACKUP_RESTORE.md
docs/TROUBLESHOOTING.md
docs/CLINICIAN_USER_MANUAL.md
docs/CLINICIAN_USER_MANUAL.pdf
docs/FUTURE_EXPERIMENTS.md
docs/RELEASE_CHECKLIST.md
```

This list may shrink further if two documents can be merged without harming usability. Deletion is preferred over redundant documentation.

## S8H — Release acceptance

Run from a clean clone or clean machine/VM where practical.

Minimum acceptance:
- install from documented prerequisites;
- build frontend;
- run backend/unit tests;
- run frontend tests/typecheck/build;
- install/download/verify model assets;
- start Model API;
- healthcheck passes;
- start review application;
- connect review app to Model API;
- ingest PNG/TIFF and supported ophthalmic DICOM;
- run one grade and lesion inference;
- confirm Review and Dataset workflow;
- export dataset;
- restart services;
- reboot model server and verify service recovery when systemd is enabled;
- perform offline model-server smoke after initial setup;
- generate clinician manual screenshots/PDF;
- verify README links and commands from a clean checkout.

## Final S8 state

S8 may be marked complete only when:
- repository is clean and intentionally minimal;
- obsolete docs are deleted rather than archived;
- authoritative setup/start/healthcheck paths work;
- model weights are verified and reusable offline;
- operator and clinician docs match the final UI/code;
- the automated manual is regenerated from the release candidate;
- all tests/builds pass;
- main is clean and synchronized;
- final release tag/version is chosen explicitly by the owner.
