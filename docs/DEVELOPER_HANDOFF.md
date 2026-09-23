# Developer handoff

Use this checklist to take over ownership of Retinal Review Workbench. It points to the right documents and does not repeat them.

## 1. Read first (in this order)

1. [`AGENTS.md`](../AGENTS.md): branch and worktree policy, protected areas, and the definition of done.
2. [`README.md`](../README.md): the navigation portal and quick start.
3. [Developer Technical Guide](DEVELOPER_TECHNICAL_GUIDE.pdf) (source: [`developer-manual/`](developer-manual/index.qmd)): architecture and internals.
4. [`technical/FEATURE_IMPLEMENTATION_MAP.md`](technical/FEATURE_IMPLEMENTATION_MAP.md) and [`technical/WHERE_TO_CHANGE_WHAT.md`](technical/WHERE_TO_CHANGE_WHAT.md).
5. [`adr/`](adr/README.md): why things are the way they are.
6. [`DESIGN.md`](../DESIGN.md) (UI source of truth) and [`DATASET_MANIFEST.md`](DATASET_MANIFEST.md) (export-schema source of truth).
7. The [Clinician User Manual](CLINICIAN_USER_MANUAL.pdf) and the [Deployment & Operations Manual](DEPLOYMENT_OPERATIONS_MANUAL.pdf): what users and operators actually do.
8. The [Team Image Sampling Requirements](IMAGE_SAMPLING_REQUIREMENTS.pdf) and its [register](image-sampling-requirements/REQUIREMENTS_TRACEABILITY.md): the image intake boundary and open owner decisions.

## 2. Reproduce locally (first day)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test,dicom]"
npm ci
cd frontend; npm ci; npm test; npm run typecheck; npm run build; cd ..
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check dr_support tests
.venv\Scripts\python.exe -m dr_support.fetch_samples   # needed by the root UI smoke test
npm test
```

Then run `START.cmd` and open `http://127.0.0.1:8000/app/`. Create a synthetic Workspace in **Settings**. Inference stays disabled until a Model API is configured.

Baseline on `main` `ec74af8` (2026-09-23):

| Check | Result |
|:--|:--|
| Backend tests | 179 passed |
| Ruff | clean |
| Frontend tests | 66 passed in 14 files |
| Typecheck | clean |
| Frontend build | OK (large-chunk warning only) |
| Root `npm test` | Needs the HRF samples and the Windows `.venv\Scripts\python.exe` path |

## 3. Ownership transfer checklist

- [ ] GitHub repository admin rights and branch protection for `main`.
- [ ] Access to the hospital GPU host (`/opt/dr-support-screening-poc`, service `dr-support-model-api`, `/etc/dr-support/model-server.env`). Rotate `REMOTE_MODEL_TOKEN` on handover.
- [ ] CVAT Online project and credentials, if used. Rotate `CVAT_TOKEN`.
- [ ] Licence position for RETFound and PRISM-DR (research / non-commercial terms; see `THIRD_PARTY_NOTICES.md`).
- [ ] Documentation toolchain installed: Quarto with XeLaTeX, mermaid-cli, and Playwright Chromium (`scripts/docs/build_docs.py` header).
- [ ] Walk through the product demo (`PRESENT_DEMO.cmd`) and the technical briefing (`PRESENT_TECHNICAL.cmd`) with the previous owner.
- [ ] Review the open owner decisions (Team Image Sampling Requirements, chapter 9) and the limitations listed below.

## 4. Protected behaviour (do not change without a spec)

- Admission semantics.
- Patient/eye resolver semantics.
- Model/provider identities and the remote contract.
- Annotation provenance.
- Original-image coordinates.
- Clinician-review semantics (three confirmations).
- The dataset export schema.
- The image-intake boundary (ADR-0006).

## 5. Known limitations and open items

- No authentication. The reviewer name is self-declared. The workstation binds to localhost only.
- The Workbench stores no source `Refer`/`Not-refer` class and no sex. How the team links them to images is an **open owner decision** (IMG-SAMP-013).
- Screenshot capture tooling was removed from `main` in `ec74af8`. The manual screenshots are committed assets.
- The root UI smoke test (`tests/ui.test.cjs`) is Windows-path specific and depends on the public samples.
- There is no near-duplicate detection and no automatic dataset split (by design).
- `CHANGELOG.md` was removed in `ec74af8`. Record releases in commit messages or restore a changelog if the owner wants one.

## 6. Where things are generated

| Output | Command |
|:--|:--|
| Every PDF, decks, diagrams | `python scripts/docs/build_docs.py all` |
| Documentation QA | `python scripts/docs/check_docs.py` |
| Frontend bundle (`frontend/dist`, gitignored) | `cd frontend && npm run build`, on `main` after merges |
