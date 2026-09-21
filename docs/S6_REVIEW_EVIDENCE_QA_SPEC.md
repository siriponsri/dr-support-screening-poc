# S6 — Review Evidence & QA

Status: DRAFT — owner-approved single-lane milestone  
Repository: `siriponsri/dr-support-screening-poc`

## 1. Goal

S6 should make the clinician review workflow easier to inspect, explain, and audit without changing frozen dataset semantics or adding new model research.

S6 is intentionally a **single-lane milestone**. The owner prefers direct execution on `main` to reduce branch/worktree overhead.

### Owner execution override

For **S6 only**, implementation may proceed directly on a clean, synchronized `main` in staged commits.

This override is intentionally limited to S6. It does not waive:
- preflight Git checks,
- test requirements,
- frozen S1–S5 semantics,
- source/provenance safety,
- PHI protections,
- human-review authority.

If the repository's general branch policy conflicts with this section, this S6 owner override is the authoritative instruction for this milestone only.

## 2. Current baseline

S5 — Medical Image Ingestion & Data Integrity is complete/frozen on main.

Observed owner smoke after S5:
- PNG preview works.
- TIFF preview works.
- DICOM rows can still appear as `No preview / Cannot analyze` in the Worklist.
- An ancillary `sources.csv` file can appear as a non-image case in the Worklist.
- PRISM ROI overlays do not yet expose their per-detection confidence value clearly enough for clinician review.

These are S6 integration/usability items, not a request to redesign the S5 imaging architecture.

## 3. S6 scope

S6 has four bounded deliverables:

1. **DICOM review-path completion**
2. **Workspace non-image hygiene**
3. **PRISM ROI evidence + confidence display**
4. **Review evidence / QA summary**

Do not expand S6 into model research or a large UI redesign.

## 4. DICOM review-path completion

### 4.1 Problem

A valid `.dcm` source may be admitted but still reach the Worklist as:
- `No preview`
- `Cannot analyze`
- `This file could not be read as a supported image.`

S6 must trace the final integrated path and remove any remaining gap between:

```text
workspace scan
→ admitted source
→ DICOM handler
→ display derivative
→ Worklist thumbnail/review viewer
→ optional analysis payload
```

### 4.2 Required behavior

For a **supported single-frame ophthalmic DICOM**:
- retain exact original source bytes,
- retain authoritative `source_sha256`,
- keep safe DICOM metadata policy,
- create/reuse deterministic browser-safe display derivative,
- Worklist thumbnail should use the display derivative,
- Review viewer should use the display derivative,
- analysis may use a model-compatible derivative only when the existing model contract permits it,
- `analysis_sha256` must hash the exact bytes actually sent to the Model API.

For unsupported DICOM:
- multi-frame must remain explicit `Needs review` / unsupported,
- missing codec must remain explicit `DICOM_CODEC_REQUIRED`,
- corrupt/decode failure must fail safely,
- never silently select frame 1,
- never expose raw DICOM header/PHI.

### 4.3 Integration rule

Do not create another DICOM pipeline.

Reuse the existing S5:
- imaging contracts,
- DICOM handler/registry,
- derivative service,
- display endpoint.

The fix should be at the smallest remaining adapter/UI boundary.

## 5. Workspace non-image hygiene

### 5.1 Problem

Ancillary workspace files such as `sources.csv` should not become clinician-review cases.

### 5.2 Required behavior

Only supported image-source candidates should enter the clinical Worklist.

Files such as:
```text
.csv
.json
.md
.txt
```
may exist inside a workspace for provenance or fixture metadata but must not be presented as retinal-image cases.

They may be:
- ignored,
- recorded as ancillary workspace files,
- or surfaced only in technical audit/details,

but not as `Cannot analyze` clinical rows.

Do not weaken explicit handling of truly unsupported image formats where the application intentionally reports them.

## 6. PRISM ROI evidence and confidence

### 6.1 Terminology

PRISM-DR produces lesion detections.

The numeric score shown beside an ROI is a **model detection confidence score**.

It must **not** be described as:
- calibrated probability,
- probability of disease,
- diagnostic certainty,
- RETFound explanation.

Use wording such as:
```text
MA 0.82
HE 0.76
EX 0.64
SE 0.71
```

Canonical lesion labels remain:
```text
MICROANEURYSM
HEMORRHAGE
HARD_EXUDATE
SOFT_EXUDATE
```

Display labels may be:
```text
Microaneurysm
Hemorrhage
Hard exudate
Soft exudate
```

### 6.2 ROI overlay

Each AI-generated PRISM ROI should expose:
- lesion class,
- confidence score,
- source = AI,
- model identifier/revision when available.

Preferred visual treatment:
```text
┌──────── ROI ────────┐
│ MA · 0.82           │
└─────────────────────┘
```

Keep the overlay compact so it does not obscure the retinal image.

Recommended formatting:
- 2 decimal places by default,
- raw score retained internally,
- no percent sign unless the UI explicitly labels it as a score,
- do not threshold or hide detections differently merely because the score is now visible.

### 6.3 Evidence list

The review side panel/list should show the same information:
```text
Microaneurysm     0.82
Hemorrhage        0.76
Hard exudate      0.64
```

Selecting an evidence item should focus/highlight the corresponding ROI when current viewer architecture supports it safely.

The overlay and evidence list must reference the same annotation/detection identity.

## 7. AI vs clinician review evidence

S6 should make review changes inspectable without creating a new scientific claim.

Useful states include:
```text
AI suggested
Clinician confirmed
Clinician added
Clinician removed
Label changed
Geometry changed
```

Provide a compact summary such as:
```text
Confirmed   5
Added       2
Removed     1
Corrected   3
```

Do not interpret these counts as model accuracy metrics.

A confirmed AI annotation remains distinguishable from a human-authored annotation in provenance.

## 8. Review QA / audit

Expose only information useful to clinician review and traceability:
- review status,
- reviewer identity/key already supported by the product,
- review timestamp,
- annotation source,
- model identifier/revision,
- unresolved items,
- confirmation status,
- source/derivative lineage where useful in technical details.

Avoid another KPI dashboard.

Technical metadata should live in a details/audit area rather than dominate the Worklist.

## 9. Frozen semantics

S6 must preserve:
- S1 viewer semantics except bounded evidence enhancements,
- S2 workspace behavior,
- S2A1 admission safety,
- S2A2 patient/eye resolver semantics,
- S3 Worklist compactness and five-column structure,
- S4 dataset eligibility/training-ready semantics,
- S5 source/derivative provenance,
- authoritative source SHA,
- canonical annotation coordinates,
- human review authority,
- CVAT round-trip semantics,
- AI-only dataset state.

Do not change patient identity or eye laterality automatically because of DICOM metadata.

DICOM laterality remains evidence only.

## 10. Scientific boundaries

Do not claim:
```text
PRISM lesion ROI = RETFound explanation
```

PRISM lesion evidence and RETFound grade suggestion are separate model outputs.

Do not add in S6:
- Grad-CAM,
- saliency,
- attention maps,
- RETFound attribution,
- calibration claims,
- new models,
- fine-tuning,
- local adaptation,
- model comparison,
- PACS/DICOMweb,
- autonomous diagnosis/referral.

PRISM confidence is an uncalibrated model score unless separate calibration evidence exists.

## 11. UI requirements

Keep the current clinical/minimal design.

Do not:
- create a large dashboard,
- increase Worklist density,
- add horizontal scrolling,
- add decorative gradients/glassmorphism,
- put model/debug metadata in primary rows.

Prefer enhancing the existing Review workspace.

Suggested composition:
```text
Retinal Viewer
└─ lesion overlays
   └─ class + confidence

Evidence panel
├─ lesion evidence
├─ AI vs clinician changes
└─ review QA

Technical details / audit
└─ model revision + provenance + lineage
```

## 12. Tests

At minimum add focused coverage for:

### DICOM
- supported single-frame DICOM reaches thumbnail/display path,
- DICOM Review viewer opens when decode is supported,
- corrupt DICOM fails safely,
- multi-frame remains explicit unsupported/review,
- no PHI leaks to public response.

### Workspace hygiene
- `.csv` metadata file does not become a clinician case,
- supported image files still appear normally,
- intentional unsupported-image behavior is not accidentally removed.

### PRISM evidence
- detection confidence survives API serialization,
- confidence maps to the correct ROI,
- confidence is shown in review UI,
- score formatting is deterministic,
- human edits do not rewrite the original model score silently.

### Review diff / QA
- added/removed/changed/confirmed states are deterministic,
- provenance remains distinguishable,
- S4 eligibility remains unchanged.

## 13. Validation

Before completion run:
```text
backend tests
Ruff
frontend tests
frontend typecheck
frontend build
git diff --check
```

Also manually smoke:
```text
1. Open PNG
2. Open TIFF
3. Open supported DICOM
4. Confirm CSV is absent from clinical Worklist
5. Analyze one compatible fundus image
6. Confirm PRISM ROI shows class + numeric confidence
7. Edit/confirm one ROI
8. Confirm review evidence/diff updates
9. Confirm dataset semantics are unchanged
```

Known deprecation warnings from current dependencies are non-blocking for S6 and may be deferred to S8 unless they become functional failures.

## 14. Completion criteria

S6 is complete when:
- supported DICOM can reach the review display path,
- ancillary non-image files do not pollute the clinical Worklist,
- PRISM ROI confidence is visible and correctly bound to each detection,
- AI vs clinician changes are inspectable,
- basic review QA/provenance is visible,
- no S1–S5 frozen semantics regress,
- tests/build pass,
- main is clean and synchronized.

Then mark:
```text
S6 — Review Evidence & QA
COMPLETE / FROZEN
```

Next milestone:
```text
S8 — Production & Deployment Hardening
```
