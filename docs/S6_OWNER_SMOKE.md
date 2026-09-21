# S6 Owner Smoke Notes

## A. File handling
- [ ] PNG appears and previews
- [ ] TIFF appears and previews
- [ ] Supported ophthalmic DICOM appears and previews
- [ ] Corrupt DICOM fails safely
- [ ] Multi-frame DICOM is not silently reduced to frame 1
- [ ] `sources.csv` does not appear as a clinical case

## B. PRISM evidence
- [ ] Analyze a compatible fundus image
- [ ] ROI shows lesion class
- [ ] ROI shows numeric confidence, e.g. `MA · 0.82`
- [ ] Evidence list shows the same confidence
- [ ] Selecting evidence maps to the same ROI where supported
- [ ] Confidence is not described as diagnostic probability

## C. Human review
- [ ] Confirm an AI ROI
- [ ] Add one annotation
- [ ] Remove/reject one AI annotation
- [ ] Change a label or geometry
- [ ] Review evidence summarizes the corresponding changes
- [ ] Model-vs-human provenance remains distinguishable

## D. Regression
- [ ] Worklist remains compact
- [ ] Patient/eye workflow unchanged
- [ ] Dataset AI-only/training-ready semantics unchanged
- [ ] Export still uses authoritative source identity

## Agent validation evidence (2026-09-21)

- Backend integration tests cover PNG/TIFF, supported single-frame DICOM display,
  corrupt/multi-frame DICOM safety, ancillary-file exclusion, and dataset
  provenance/eligibility regressions.
- Browser smoke used the synthetic fixture at `/app/#/review/SYNTH_001` and
  verified the `MA 0.80` overlay, matching evidence item, source lineage,
  confirmation action, and updated `Confirmed 1` / `0 AI suggestions unresolved`
  state at desktop and 390x844 mobile viewports.
- Automated validation passed: backend `231 passed, 9 skipped`, frontend `61
  passed`, typecheck, production build, Ruff, root smoke, and `git diff --check`.
