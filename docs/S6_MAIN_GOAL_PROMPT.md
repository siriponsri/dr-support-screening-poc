# S6 Main Execution Prompt

```text
/goal S6 — REVIEW EVIDENCE & QA

Repository:
siriponsri/dr-support-screening-poc

Authoritative branch:
main

OWNER OVERRIDE FOR S6:
Implement this milestone directly on a clean synchronized main.
Do not create feature branches/worktrees for S6.
Use staged commits on main instead.

Follow AGENTS.md except where this explicit S6 owner override changes the branch/worktree rule.

Read first:
- docs/S6_REVIEW_EVIDENCE_QA_SPEC.md
- relevant existing S1–S5 contracts/implementation
- current Worklist/Review frontend
- S5 imaging registry/DICOM/derivative path
- PRISM result serialization and annotation model
- S4 dataset eligibility/export logic

Before editing report:
- repository root
- branch
- HEAD
- git status --short --branch
- origin/main synchronization

Require:
- branch = main
- clean working tree
- main synchronized with origin/main

If not, STOP.

GOAL

Complete S6 in one lane and keep it bounded.

Priority 1 — DICOM review path
- Trace the remaining integrated failure where valid `.dcm` may appear as No preview / Cannot analyze.
- Reuse S5 DICOM handler + derivative/display path.
- Supported single-frame ophthalmic DICOM must reach Worklist thumbnail and Review viewer.
- Preserve source bytes, authoritative source SHA, provenance, safe metadata and exact analysis hashing.
- Keep multi-frame / codec-required / corrupt states explicit.
- Do not create another DICOM pipeline.

Priority 2 — workspace hygiene
- Ancillary files such as `sources.csv` must not become clinician-review cases.
- Preserve deliberate unsupported-image handling.
- Do not hide real ingestion failures.

Priority 3 — PRISM ROI confidence
- Show PRISM per-detection confidence numerically with the ROI and in the evidence list.
- Prefer 2 decimal places.
- Bind score to the exact detection/annotation identity.
- Preserve raw score internally.
- Call it detection confidence/model score, not calibrated probability.
- Do not claim PRISM is an explanation for RETFound.

Priority 4 — Review Evidence & QA
- Add compact inspection of AI vs clinician changes:
  confirmed / added / removed / label changed / geometry changed.
- Show useful provenance:
  model identifier/revision, annotation source, review state/timestamp where already supported.
- Keep technical metadata out of the primary Worklist.
- Use the existing Review workspace; avoid a new dashboard unless strictly required.

FROZEN

Do not change:
- S3 five-column Worklist structure
- patient/eye resolver semantics
- S4 training-ready / AI-only semantics
- S5 source/derivative identity
- canonical annotation coordinate semantics
- human review authority
- CVAT round-trip behavior
- model grading logic

DO NOT ADD

- Grad-CAM
- saliency/attention
- RETFound attribution
- new models
- calibration claims
- fine-tuning
- model comparison
- PACS/DICOMweb
- broad architecture refactors

EXECUTION

Use staged commits directly on main:

Commit 1:
DICOM review-path + workspace hygiene

Commit 2:
PRISM ROI confidence + evidence UI

Commit 3:
AI-vs-clinician diff + review QA + tests/docs

You may adjust commit grouping if implementation dependencies require it,
but keep the work bounded to S6.

For each stage:
- inspect existing implementation first
- make the smallest coherent change
- run focused tests before continuing

FINAL VALIDATION

Run:
- full backend tests
- Ruff
- frontend tests
- frontend typecheck
- frontend build
- git diff --check

Add focused tests for:
- DICOM thumbnail/display
- corrupt/multiframe safe behavior
- ancillary CSV excluded from clinician Worklist
- PRISM confidence serialization/display
- ROI-score identity mapping
- AI/human diff state
- S4 eligibility regression

Manual smoke checklist:
1. PNG displays
2. TIFF displays
3. supported DICOM displays
4. CSV absent from clinical Worklist
5. PRISM ROI shows class + numeric confidence
6. evidence item focuses/matches ROI where supported
7. clinician edit produces correct diff/provenance
8. dataset semantics unchanged

Known dependency deprecation warnings are not blockers unless functional.

When all validation passes:
- update only necessary S6 documentation/status
- push main
- verify main == origin/main
- verify clean working tree

Return:
- starting main SHA
- final main SHA
- commit list
- changed files
- DICOM root cause/fix
- workspace filtering behavior
- PRISM confidence behavior
- review evidence/QA behavior
- validation results
- remaining non-blocking limitations

Then mark:
S6 — Review Evidence & QA
COMPLETE / FROZEN

Do not start S8 in this run.
```
