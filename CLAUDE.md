# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

`AGENTS.md` (imported above) is binding: git/worktree policy (no implementation writes on `main`), merge gate, frozen-behavior STOP rules, and definition of done. The `.agents/skills/` directory it mentions does not currently exist in this checkout. Before any work, read `HANDOFF.md` and `GOAL.md` (see "Where to read" below).

## What this is

Retinal Review Workbench: a clinician-controlled diabetic retinopathy (DR) review and research-dataset workspace. FastAPI backend (`dr_support/`) + React/Vite/Chakra UI (`frontend/`, served at `/app/`). AI is optional assistance from a separate Linux GPU "Model API"; the human grade/annotation is always authoritative. Not a diagnostic device.

## Commands (Windows / PowerShell, repo root)

Setup: `uv sync --python 3.12 --extra test --extra dicom --extra browser-test`, then `npm.cmd ci` at root and in `frontend/`, then `npm.cmd run build` in `frontend/`. Use `npm.cmd` if PowerShell blocks `npm.ps1`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q                                   # backend
.\.venv\Scripts\python.exe -m pytest -q tests\test_workflow.py -k <name>  # single test
.\.venv\Scripts\python.exe -m ruff check dr_support tests                 # rules E9,F; line length 110
npm.cmd test                                   # root API smoke test (tests/api_smoke.test.cjs)
.\.venv\Scripts\python.exe scripts\docs\check_docs.py                     # docs link/ID checks
git diff --check
```

Frontend (in `frontend/`): `npm.cmd test` (Vitest, jsdom), `npx vitest run tests/review.test.tsx` for one file, `npm.cmd run typecheck`, `npm.cmd run build`, `npm.cmd run dev` (Vite on 5173, proxies `/v1`, `/health` to `127.0.0.1:8000`).

Run the app: `.\START_DR_SCREENING.bat` (→ `http://127.0.0.1:8000/app/`), stop with `.\STOP_DR_SCREENING.bat`. It runs `python -m dr_support.run` with `APP_PROFILE=review`, `MODEL_RUNTIME=remote`, and needs a prebuilt `frontend/dist`.

Test environment caveats:
- `tests/api_smoke.test.cjs` boots legacy `dr_support.api:app` and walks the synthetic case through AI and a grade correction over HTTP.
- PostgreSQL tests skip unless `DR_SUPPORT_TEST_DATABASE_URL` and a matching `DR_SUPPORT_TEST_DATABASE_NAME` (must contain a `test` token) are set; fixtures create/drop only a `dr_support_test_*` schema.
- Frontend build warns about a >500 kB chunk; expected.

## Architecture

**Runtime profiles** (`dr_support/app.py`, invariants enforced at startup, never silent fallback):
- `review` + `MODEL_RUNTIME=remote` — clinician workstation; model calls go to `REMOTE_MODEL_URL`.
- `model_api` + `local` — GPU host (`scripts/model-server/start.sh`), serves `/v1/predict/*`; CUDA enforced; refuses unverified assets.
- `full` + `local` — dev/demo only, includes synthetic fixtures and public samples.
- `dr_support.api:app` is a legacy entry point that skips these invariants (used only by the root API smoke test).

**Backend layout.** `api/_factory.py:create_app` is the composition root (incl. `apply_scan`); it installs `api/model_connection.py` (Model API connection, model lists), `api/inference.py` (`infer()`, PRISM preview, `/v1` and `/v2` inference) and `api/batches.py` (daily batch); `workflow.py` builds the shared case helpers and installs the route groups in `workflow_routes/` (cases, images, review, confirm, annotations, cvat) in order; `services/` holds domain logic (admission, resolver, dataset export, workspaces, model gateway, PRISM preparation/binding, M1 workspace context); `contracts/` holds Pydantic contracts; `imaging/` holds integrity, DICOM, derivatives and coordinate mapping; `providers/` holds RETFound, PRISM, remote HTTP clients and `mock` (synthetic only); `presentation.py` derives the bounded lesion-review view and `annotation_set_hash`.

**Persistence.** Each case is one JSON document with a `revision`; every mutation sends the client revision and a mismatch returns `409 Case changed; reload`. Normal operation is PostgreSQL JSONB scoped by `workspace_id` (`DR_SUPPORT_CASE_STORE=postgres`, `DR_SUPPORT_DATABASE_URL`), with forward-only checksummed migrations in `persistence/` (`SchemaMigrator`); a changed or gapped history fails rather than being rewritten. Legacy SQLite (`store.py`) remains for compatibility tests and fixtures. New case fields are added as JSON defaults (additive), not table rewrites. PostgreSQL unavailability never falls back to SQLite. Workspace FK is `ON DELETE RESTRICT`: profile removal never cascades into review data.

**Case pipeline.**
1. *Admission* (`services/admission.py`): scans only the workspace input folder, top level; content SHA-256 is case identity (duplicates collapse to aliases). Manual admission decisions survive rescans; vanished files become `SOURCE_MISSING`, never deleted. `retinal_modality` starts `UNKNOWN` and inference requires clinician-confirmed `CFP`.
2. *Resolver* (`services/resolver.py`): filename-first patient key/eye; OCR is off by default; conflicts are never auto-resolved; runs once and never overwrites a manual decision.
3. *Confirm Image* → *Confirm DR Grade* (`ACCEPT`/`CORRECT_GRADE`) → annotations (`PUT` replaces the whole human set) and AI-ROI decisions (append to `ai_annotation_reviews`; raw model output is never modified) → *Finish image* (`CONFIRM_ANNOTATIONS` stores the annotation-set hash; any later change reverts the state to requires-confirmation).
4. *Inference*: `DerivativeService` builds a deterministic analysis image with its own SHA and a `CoordinateMapping`; all geometry stays in original-image pixels. Source SHA ≠ analysis SHA for TIFF/DICOM/UWF-masked inputs. A later AI result never resets a confirmed human grade. PRISM review requests require a prepared one-use input receipt (see `docs/developer/MODEL_SERVER_OPERATIONS.md` section 3).
5. *Dataset export* (`services/dataset.py`, with `dataset_common.py`, `dataset_snapshot.py`, `dataset_grouped.py`): DR-ready and Lesion-ready are separate; see `docs/developer/DATASET_MANIFEST.md`.

**Clinical semantics to preserve:** an empty AI detection or empty human set means "reviewed", not "no lesions"; RETFound softmax is uncalibrated; the hospital's own `Refer/Not-refer` label is deliberately not stored in the Workbench; the only referral shown is the owner-confirmed `M1_DR_GRADE_4_REFERRAL` rule in `referral.py` (derived solely from a confirmed physician grade), and no other referral rule may be added without an approved clinical definition; the software never browses hospital storage. Pinned model identities live in `providers/retfound.py`, `providers/prism.py`, `providers/prism_assets.json`; changing them is a provenance change.

**Frontend.** `frontend/src/routes.tsx` defines the pages (Worklist, Review, Clinician Review, Annotation Editor `/edit/:imageId`, Datasets, Models, Settings) under `AppShell` with `NavigationGuardProvider` and `WorkspaceProvider`. `@` aliases `src`. API client and UI-only preferences live in `src/lib/`; tokens in `src/theme/` must follow `DESIGN.md`. The annotation editor autosaves (900 ms debounce) and flushes drafts before any ROI decision or Finish so revisions don't race.

## Where to read before substantial work

- [HANDOFF.md](HANDOFF.md) and [GOAL.md](GOAL.md) (Thai): **read first.** HANDOFF is the short current engineering checkpoint (main state, dr-train state, standing owner rules, open owner decisions, how to resume). GOAL is the current goal: phase 1 done, what remains, phase 2 deferred. Reading them is not authorization to resume paused work, run GPU work or change dr-train.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): system map, case flow, roles, data model, safety rules, which documents to trust, `scripts/` index.
- `docs/developer/`: configuration, dr-train access, model server operations (regular gateway, Model API, PRISM receipts), security, dataset manifest (export contract), backup and restore.
- `DESIGN.md`: visual/interaction source of truth.
- `deployment/*/README.md`: Docker packages (web app, hospital server) and other deployment paths.
- History (full old HANDOFF and GOAL, M1 master plan, milestone specs and receipts, manuals, ADRs): Git tag `archive/docs-before-cut-20261101`. Evidence, not runbooks.
