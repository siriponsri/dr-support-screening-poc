# Release Checklist

This checklist covers release-engineering evidence. A package marked ready here
is not production, clinical, hospital-data, model, or training authorization.

## No-code package gates

- [ ] `FIRST_RUN.bat`, `START_DR_SCREENING.bat`, `STOP_DR_SCREENING.bat`, and
      `CHECK_SYSTEM.bat` work from an extracted workstation package.
- [ ] Workstation package includes a prebuilt `frontend/dist` and normal users
      do not run npm commands.
- [ ] Workstation package includes a verified `frontend/dist/build-identity.json`
      bound to the release source commit and frontend source digest.
- [ ] Model API package contains software/contracts only; no weights, secrets,
      databases, patient data, or runtime state.
- [ ] `RELEASE_MANIFEST.json` records source version/commit and
      `SHA256SUMS.txt` is verified after package creation.
- [ ] No-code readiness checks verify configured PostgreSQL connectivity and do
      not imply managed review readiness for missing configuration or SQLite
      compatibility mode.
- [ ] USPEC artifact manifest records expected identity only; acquisition and
      runtime qualification remain deferred.

## Product tree

- [ ] README describes the current product and links resolve.
- [ ] Current operating documentation under `docs/` points to one supported workstation path.
- [ ] Accepted milestone specifications, owner evidence, and receipts remain for traceability; no obsolete task packets or duplicate operating guides remain.
- [ ] No secrets, PHI, model weights, runtime databases, or local-state artifacts are tracked.
- [ ] Logo and final architecture/workflow diagrams use Retinal Review Workbench branding.

## Runtime

- [ ] Clean clone installs the review workstation dependencies and builds `frontend/dist`.
- [ ] `START_DR_SCREENING.bat` opens the review workstation at `/app/`.
- [ ] One-time model setup verifies pinned RETFound and PRISM-DR assets and ends with `READY`.
- [ ] Normal Model API startup performs read-only verification and does not download.
- [ ] `/health` reports `PASS` with verified assets and `/v1/models` reports every advertised capability with task, modality, readiness, and release metadata; at least one actionable descriptor is required for AI readiness.
- [ ] Offline restart and local inference have been exercised after setup.

## Clinical workflow

- [ ] PNG/TIFF and supported ophthalmic DICOM display.
- [ ] MRI/non-fundus DICOM shows `Unsupported modality`, not a generic decoder failure.
- [ ] Review keeps the retinal image primary and has no desktop horizontal scrollbar.
- [ ] PRISM class and confidence are visible; overlays can be toggled and filtered.
- [ ] Clinician review completes without confirming every AI ROI.
- [ ] Models & Audit shows read-only evidence and provenance.
- [ ] Dataset export produces the documented manifest and CSV files.
- [ ] Quarto manual source, final UI screenshots, HTML site, and PDF were regenerated from the final UI.
- [ ] Offline owner demonstration opens in Chromium/Edge, uses current focused screenshots, and passes keyboard/reduced-motion smoke checks.
- [ ] Dataset export documents `s4.dataset-manifest.v2`, three confirmation states, and separate DR-ready/Lesion-ready semantics.

## Validation commands

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check dr_support tests
cd frontend
npm test
npm run typecheck
npm run build
cd ..
npm test
git diff --check
```
