# Release Checklist

## Product tree

- [ ] README describes the current product and links resolve.
- [ ] Only final operational documentation remains under `docs/`.
- [ ] No drafts, milestone specifications, owner audit notes, temporary smoke reports, or duplicate README files remain.
- [ ] No secrets, PHI, model weights, runtime databases, or local-state artifacts are tracked.
- [ ] Logo and final architecture/workflow diagrams use Retinal Review Workbench branding.

## Runtime

- [ ] Clean clone installs the review workstation dependencies and builds `frontend/dist`.
- [ ] `START.cmd` opens the review workstation at `/app/`.
- [ ] One-time model setup verifies pinned RETFound and PRISM-DR assets and ends with `READY`.
- [ ] Normal Model API startup performs read-only verification and does not download.
- [ ] `/health` reports `PASS` with verified assets and `/v1/models` reports both model descriptors.
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
