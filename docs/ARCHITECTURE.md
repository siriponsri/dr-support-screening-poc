# Architecture (team handoff)

Retinal Review Workbench: a clinician-controlled DR screening, review and research-labelling app.
AI is optional assistance; the person's grade is always authoritative. Not a diagnostic device.
Start here, then read [`AGENTS.md`](../AGENTS.md) (binding rules), [`CLAUDE.md`](../CLAUDE.md)
(commands and architecture notes) and [`HANDOFF.md`](../HANDOFF.md) (current state).

## 1. System at a glance

```text
Browser (React SPA at /app/, EN/TH)
   |  HTTPS (sign-in cookie)
Review app (FastAPI, APP_PROFILE=review, MODEL_RUNTIME=remote)
   |-- PostgreSQL (one JSON document per case, with revision)
   |-- private config folder (accounts, server mode, referral connector)
   |-- AI model server, one of:
         a) hospital model server: deployment/hospital-server (gateway + USPEC + RETFound + PRISM on GPU)
         b) team server dr-train: regular gateway 127.0.0.1:7860 over SSH, GPU child on demand (7861)
```

| Piece | Where | Entry |
| --- | --- | --- |
| Review app | `dr_support/` | `dr_support/run.py` -> `dr_support/app.py:create_app` -> `api/_factory.py:create_app` |
| Model API (GPU) | same package, `APP_PROFILE=model_api` | `services/model_api.py` |
| Regular gateway (dr-train) | `scripts/model-server/regular_service.py` | daily authority `regular_authority.py` (calls, GPU-seconds, AI hours, tickets, audit chain) |
| QA launcher | `scripts/qa/m1_server_app.py` | `serve-regular` (app + SSH tunnel + queue) |
| One-click demo | `scripts/demo/` | desktop shortcut "DR Screening Demo" |
| Frontend | `frontend/src/` | `routes.tsx`, pages in `pages/`, API client `lib/api.ts`, i18n `lib/i18n.tsx` |
| Docker | `deployment/webapp` (package 1), `deployment/hospital-server` (package 2), base `deployment/dual-mode` | `bin/start.sh` |

Runtime profiles fail hard on a wrong combination (no silent fallback): `review`+`remote`,
`model_api`+`local` (CUDA required), `full`+`local` (dev/demo only). `dr_support.api:app` is a legacy
entry used only by root smoke tests.

## 2. Case flow

1. **Admission** (`services/admission.py`): scans the workspace input folder; the content SHA-256 is the
   case identity; originals are never changed; vanished files become `SOURCE_MISSING`.
2. **Patient and eye** (`services/resolver.py`): filename first; conflicts are never auto-resolved.
3. **Confirm Image** (`workflow.py`): the person confirms CFP or UWF, quality, patient and eye. AI needs this.
4. **AI grading**: `_factory.infer()` routes UWF to USPEC and CFP to RETFound (`services/capability_routing.py`);
   the analysis image and coordinate mapping come from `imaging/derivatives.py`; geometry stays in original pixels.
5. **PRISM lesions** (`services/prism_preview*.py`): prepare a one-use receipt, then execute exactly it;
   UWF input uses the rubber-rim mask A2 (`imaging/uwf_rubber_rim_mask.py`). Uncertain calls are never resent.
6. **Grade and annotations** (`workflow.py`): `POST /v1/cases/{id}/review`, `PUT .../annotations`,
   AI-ROI decisions appended to `ai_annotation_reviews`; raw model output is never edited.
7. **Screening report** (`services/screening_report.py`): the grader chooses Refer / Not refer; a nurse
   prepares, a physician signs; print page saves as PDF.
8. **Referrals** (`services/referral_outbox.py`): signed Refer decisions only; FHIR R4 / CSV export;
   connector off by default (file drop or HTTPS webhook set by the administrator).
9. **Gold-100** (`services/gold_labels.py`): the expert grades blind; the AI value is revealed only afterwards.
10. **Export** (`services/dataset.py`): confirmed grade folders `grouped_by_grade/`, AI-predicted folders
    `ai_predicted_unverified/` (never clinical grades), manifests and snapshots.

## 3. Sign-in and roles

Active when `DR_SUPPORT_AUTH_FILE` points at the accounts file (`services/pilot_auth.py`). Every `/v1/` and
`/v2/` route needs a session (model API token routes excepted). Roles: physician, nurse, expert, researcher,
admin; the server refuses writes a role may not make (`role_denial`). Admin pages: accounts and policy,
read-only database view (`pilot_admin.py`), AI server choice with consent gate (`server_mode.py`), referral
connector.

## 4. Data model

One JSON document per case with `revision`; every write sends the revision and a mismatch returns 409
"Case changed; reload". New fields are additive JSON defaults. Main fields: `admission`, `global` (raw AI grade),
`lesion` (raw PRISM), `clinician_review` and `grade_status`, `human_annotations`, `ai_annotation_reviews`,
`screening_report`, `gold_label`, `referral_delivery`, `events`. PostgreSQL migrations are forward-only and
checksummed in `dr_support/persistence/migrations.py`.

## 5. Safety rules you must not break

- Originals are never moved, renamed, rewritten or deleted.
- The person's grade and annotations are authoritative; a later AI result never resets a confirmed grade.
- An empty AI result means "reviewed", not "no lesions"; AI scores are not calibrated probabilities.
- No automatic referral rule (only the existing `M1_DR_GRADE_4_REFERRAL`); Refer exists as the grader's choice.
- An ungradable image is never filed or reported as normal.
- Model identities and pins (`providers/retfound.py`, `providers/prism.py`, `prism_assets.json`) are provenance.
- Only public or consented images go to dr-train; real use runs on the hospital package.
- No secrets, patient data, weights or databases in Git, logs, chat or the browser.

## 6. Run and test

See [`README.md`](../README.md) and [`developer/DR_TRAIN_ACCESS.md`](developer/DR_TRAIN_ACCESS.md).
Backend `pytest -q` (offline, mocked models), `ruff check dr_support tests`; frontend `npm test`,
`npm run typecheck`; root smoke `npm test`; docs `python scripts/docs/check_docs.py`. Work on a
`feat/`, `fix/` or `docs/` branch in its own worktree; never on `main` (AGENTS.md lifecycle).

## 7. Which documents to trust

| Kind | Documents |
| --- | --- |
| Binding rules | `AGENTS.md`, `CLAUDE.md`, `DESIGN.md` |
| Current state | `HANDOFF.md` (English), `GOAL.md` (Thai) |
| Developer reference | this file, `docs/developer/*.md`, `deployment/*/README.md`, `scripts/release/README.md` |
| End users and IT | the three Thai PDFs in `docs/pdfs/` (see [`README.md`](README.md)) |
| History | Git tag `archive/docs-before-cut-20261101`: old manuals, milestone specs and receipts, plans, ADRs, full HANDOFF and GOAL. Evidence, not runbooks. |

When code and a document disagree, the code and its tests win; fix the document.

## 8. scripts/ index

| Folder | Live entry points | Notes |
| --- | --- | --- |
| `scripts/windows/` | `release-*.ps1` behind the root `*.bat` launchers | no-code workstation start, stop, check, backup, restore |
| `scripts/demo/` | one-click "DR Screening Demo" (`start-dr-train-demo.*`, `remote-start-gateway.sh`) | owner workstation only |
| `scripts/model-server/` | `regular_service.py`, `regular_authority.py` (dr-train gateway); `setup.sh`, `start.sh`, `healthcheck.sh` (GPU host); `admin/create-restricted-user.sh` | `m1_session.py` is the GPU child the gateway starts; the other `m1_*.py` and `demo_session.py` come from the closed M1 GPU windows but are still imported or tested, so check imports before removing |
| `scripts/qa/` | `m1_server_app.py` (`serve-regular` review app launcher), `check_export_folder.py` | the monitors and supervisor are used by the gateway; `qualify_*`, `batch_runtime/`, `m1_local_acceptance.py`, `m1_recorded_source_projection.py` are historical M1 evidence tools |
| `scripts/release/` | `build_release.py` (workstation and Model API ZIPs) | see its README |
| `scripts/audit/` | `check_repo_hygiene.py`, deployment and Gold plan validators | offline checks used by tests |
| `scripts/docs/` | `check_docs.py`, `capture_manual_screenshots.py`, `generate_manifest_example.py` | the Thai PDF builder comes in a later step (the old Quarto `build_docs.py` is in the archive tag) |
