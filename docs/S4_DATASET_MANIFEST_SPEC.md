# S4 Dataset Manifest Specification

**Status:** Normative milestone specification  
**Milestone:** S4 — Dataset Manifest & Export  
**Project:** DR Support Screening POC

## 1. Purpose

S4 makes the reviewed Workspace data exportable as a reproducible, auditable dataset manifest.

The primary product output is a curated dataset, not the AI prediction itself.

S4 must preserve the distinction between:

- original image identity;
- AI suggestions;
- clinician-authored annotations;
- clinician-confirmed/corrected grades;
- imported/reviewed annotation sources;
- unresolved or excluded cases.

S4 is metadata/export infrastructure. It must not retrain models, rewrite images, or change the clinical review workflow.

---

## 2. Frozen dependencies

Do not change the semantics of:

- S1 viewer and original-image coordinate space;
- S2 Workspace Manager;
- S2A1 admission/inference guard;
- S2A2 patient/eye resolver;
- PRE-S3 Model Gateway;
- S3 Worklist state ownership;
- RETFound / PRISM-DR outputs;
- CVAT round-trip semantics;
- existing human annotation geometry;
- original source images.

If S4 requires changing a frozen contract, STOP and report.

---

## 3. Core principles

1. **Original image identity is immutable.**
   Use the existing image SHA-256 as the primary content fingerprint.

2. **AI suggestion != ground truth.**
   AI-only outputs must never become training ground truth automatically.

3. **Human and AI provenance stay separate.**
   Do not overwrite source provenance when a clinician reviews/corrects an item.

4. **Export is non-destructive.**
   Do not move, rename, recompress, or delete source images.

5. **Training eligibility is conservative.**
   Unresolved/AI-only data may be exported for audit but should not silently become training-ready.

6. **Coordinates remain in original-image pixel space.**

7. **No raw PHI in exported manifests.**
   Export pseudonymous patient keys only.

8. **Export must be deterministic enough to reproduce which records were included and why.**

---

## 4. S4 output model

Use a normalized dataset snapshot rather than one giant duplicated table.

Recommended export:

```text
dataset-export-<timestamp>/
├─ manifest.json
├─ images.csv
└─ annotations.csv
```

S4 does **not** need to copy image files.

A future packaging milestone may create portable image bundles.

### `manifest.json`

Contains snapshot-level metadata such as:

```text
schema_version
export_id
created_at
workspace_id
workspace_name
image_count
annotation_count
generator_version / app version if available
files
```

Do not include:

- access tokens;
- raw OCR text;
- real patient name/HN/DOB;
- absolute source paths unless explicitly required for a local-only technical export.

Default clinician export should be portable and path-safe.

---

## 5. `images.csv`

One row per admitted image/case.

Required logical fields:

```text
image_id
filename
image_sha256
width
height
modality

patient_key
laterality
patient_resolution_method
laterality_resolution_method

modality_admission
quality_state
queue_state

ai_grade
ai_model_id
ai_model_version
ai_confidence

clinician_grade
grade_review_source
review_status
reviewer
reviewed_at

human_annotation_count
ai_lesion_count

verification_status
include_in_training
eligibility_reason
```

Implementation may refine names, but semantics must remain explicit.

### Privacy

`patient_key` is pseudonymous only.

Do not export:

```text
raw OCR text
real name
HN
DOB
full local source path
remote API token
```

---

## 6. `annotations.csv`

One row per lesion annotation/suggestion.

Required logical fields:

```text
annotation_id
image_id
label
shape_type
geometry_json
annotation_source
reviewer
created_at

model_id
model_version
score

verification_status
include_in_training
```

### Sources

At minimum distinguish:

```text
AI
HUMAN
CVAT_IMPORTED
```

If existing provenance provides a more precise safe source label, preserve it.

Do not relabel AI suggestions as HUMAN merely because a clinician viewed the case.

### Shape support

Preserve existing shapes:

```text
rectangle
polygon
point
circle
```

AI PRISM detections may remain rectangles.

Geometry must remain in original-image pixels.

---

## 7. Canonical lesion labels

Keep the frozen four-label taxonomy:

```text
MICROANEURYSM
HEMORRHAGE
HARD_EXUDATE
SOFT_EXUDATE
```

Do not add dynamic/custom lesion classes in S4.

Clinician-facing display names do not alter stored canonical values.

A future Lesion Taxonomy Registry may extend this explicitly.

---

## 8. Verification semantics

S4 must represent what is known without inventing certainty.

Recommended normalized verification values:

```text
UNVERIFIED
AI_ONLY
HUMAN_AUTHORED
CLINICIAN_REVIEWED
CONFIRMED
EXCLUDED
```

The implementation should map existing authoritative case state into the smallest compatible vocabulary.

Do not rewrite frozen clinical state merely to fit these names.

If existing state cannot support a proposed distinction, document the limitation rather than infer it.

---

## 9. `include_in_training`

This field is a conservative export recommendation, not an irreversible decision.

### Must be false for

- AI-only lesion suggestions not explicitly verified;
- unresolved admission cases;
- rejected/non-fundus/invalid cases;
- quality state `UNGRADABLE` or `NEEDS_REVIEW`;
- queue state `EXCLUDED`;
- records with missing required provenance/hash;
- unresolved conflicts that affect label validity.

### Image-level grade

May be true only when an authoritative clinician review has produced a final grade and the case is otherwise eligible.

Examples include existing clinician actions that accept or correct a grade.

### Human lesion annotations

Human-authored annotations may be eligible when:

- source is explicitly HUMAN;
- reviewer provenance exists;
- geometry is valid in original-image coordinates;
- case itself is eligible.

If repository state cannot distinguish a draft from a final human annotation, S4 must report that limitation and use a conservative default.

### AI/CVAT lesion annotations

AI suggestions remain false unless existing review state explicitly verifies/accepts them.

Imported CVAT annotations that still require review remain false.

A confirmed reviewed annotation set may become eligible when the existing contract clearly supports that state.

Do not add a hidden auto-promotion rule.

---

## 10. Eligibility reason

When `include_in_training=false`, provide a concise machine-readable reason.

Examples:

```text
AI_ONLY_UNVERIFIED
ADMISSION_UNRESOLVED
NON_FUNDUS
INVALID_IMAGE
QUALITY_REVIEW_REQUIRED
UNGRADABLE
QUEUE_EXCLUDED
NO_FINAL_CLINICIAN_GRADE
ANNOTATION_NOT_VERIFIED
MISSING_PROVENANCE
```

These are export/audit values, not primary clinician UI labels.

---

## 11. Dataset page

`Datasets` currently exists as a reserved page.

S4 may turn it into a compact dataset/export surface.

Recommended layout:

```text
Datasets

Dataset manifest
<short explanation>

Scope        Active Workspace
Images       24
Annotations  83

[All records] [Training-ready] [Needs review] [Excluded]

table / concise list

[Export manifest]
```

Avoid dashboard KPI cards.

The page should emphasize:

- what will be exported;
- what is training-ready vs not;
- why records are excluded/not ready;
- export action.

Do not duplicate the full Worklist.

A simple table may use columns such as:

```text
IMAGE | PATIENT / EYE | CLINICIAN GRADE | ANNOTATIONS | DATASET STATUS
```

Keep the page formal and compact.

---

## 12. Dataset status UI

Clinician-facing wording should be simple.

Examples:

```text
Ready for dataset
Needs review
Excluded
AI only
No clinician grade
```

Do not show raw eligibility reason codes by default.

Technical reasons may appear in details/tooltips.

---

## 13. Export behavior

Export is scoped to the active Workspace.

Preferred behavior:

```text
Datasets
 -> Export manifest
 -> backend builds snapshot
 -> writes manifest files under Workspace output folder
 -> returns safe export summary
```

Requirements:

- no source-image mutation;
- no source-image deletion;
- do not overwrite an unrelated previous export;
- use a unique export directory or explicit snapshot ID;
- export only metadata supported by authoritative current records;
- export failure must not modify case state;
- repeated export must not alter review/annotation records.

The UI may show:

```text
Export created
24 images · 83 annotations
```

Avoid exposing long local paths in the main success message.

---

## 14. Snapshot provenance

Each export should be traceable.

`manifest.json` should include where practical:

```text
schema_version
export_id
created_at
workspace_id
workspace_name
application_version / commit if available
images_csv_sha256
annotations_csv_sha256
```

The agent should prefer existing app/version metadata rather than inventing a new release mechanism.

---

## 15. API surface

Audit current architecture before freezing exact routes.

A minimal additive design may include:

```text
GET  /v1/dataset/manifest
POST /v1/dataset/export
```

Possible behavior:

- GET returns a preview/summary and normalized rows or paged records;
- POST creates the snapshot in the Workspace output folder.

Do not overload `/v1/cases/{id}/export` into the dataset-wide export unless the current architecture clearly supports it.

Do not change existing case export semantics without explicit approval.

---

## 16. State ownership

Build the manifest from existing authoritative records:

- image/admission metadata;
- SHA-256;
- patient/laterality resolver fields;
- queue state;
- AI global result;
- AI lesion result;
- human annotations;
- clinician review;
- CVAT/import review state;
- provenance/history where needed.

Do not add duplicate persistent dataset status fields merely for UI convenience if status can be derived safely.

A derived manifest service/view model is preferred.

---

## 17. Compatibility

S4 must preserve:

- current SQLite case storage;
- legacy readable case records;
- S3 Worklist behavior;
- AI Review;
- Annotation Editor;
- CVAT workflow;
- model inference behavior;
- Workspace switching.

Dataset export must remain valid when AI is not configured.

A dataset may contain human-reviewed records without any AI result.

---

## 18. S4 performance

Manifest preview/export should not:

- run model inference;
- call OCR;
- call CVAT automatically;
- decode full-resolution images when existing metadata/hash is sufficient.

Use existing persisted metadata where possible.

For large datasets, avoid requiring the frontend to hold every annotation row merely to display summary counts.

---

## 19. Validation

Focused tests must cover:

### Image manifest
- one row per case/image;
- stable image SHA-256;
- dimensions/modality preserved;
- pseudonymous patient/laterality exported;
- no raw PHI or token fields;
- clinician final grade mapped correctly;
- AI-only grade distinguished from clinician grade.

### Annotation manifest
- one row per annotation;
- HUMAN source preserved;
- AI source preserved;
- four canonical lesion labels preserved;
- rectangle/polygon/point/circle geometry exported;
- original-image coordinates preserved.

### Eligibility
- AI-only lesion -> not training-ready;
- excluded case -> not training-ready;
- unresolved admission -> not training-ready;
- ungradable -> not training-ready;
- clinician-reviewed final grade may be training-ready when otherwise eligible;
- imported annotations requiring review -> not training-ready;
- confirmed annotation state may be training-ready only when existing state supports it.

### Export
- creates unique snapshot;
- writes `manifest.json`, `images.csv`, `annotations.csv`;
- no source images modified;
- failed export leaves case state unchanged;
- output files parse successfully;
- CSV/JSON escaping handles long filenames/notes safely.

### UI
- Datasets page no longer placeholder;
- clear All / Ready / Needs review / Excluded views;
- export action works;
- no technical enums in primary UI.

### Regression
- backend tests;
- Ruff;
- frontend tests;
- typecheck;
- production build;
- root smoke;
- relevant S1/S2/S2A1/S2A2/PRE-S3/S3 compatibility.

---

## 20. Non-scope

Do not implement in S4:

- copying/exporting original image files into a portable dataset package;
- image recompression/resizing;
- DICOM/PACS;
- OCR changes;
- dynamic lesion taxonomy;
- model training/fine-tuning;
- model benchmarking;
- XAI;
- train/validation/test split generation;
- automatic class balancing;
- production PHI identity vault.

These belong to later/future milestones.

---

## 21. Branch/worktree guardrail

Follow `AGENTS.md`.

Before any implementation write report:

```text
repository root
active worktree path
current branch
current HEAD
git status --short --branch
```

If the implementation shell is on `main`, STOP.

Use the bounded worktree:

```text
feat/s4-dataset-manifest
```

S4 should avoid editing S3-owned Worklist files.

Preferred S4 ownership:

```text
dr_support/contracts/...
dr_support/services/...dataset/manifest...
dataset/export API surface
frontend/src/pages/DatasetsPage.tsx
dataset-specific frontend/backend tests
docs/S4_...
```

If a shared file must be edited, minimize overlap and report it before integration.

Required lifecycle:

```text
feature worktree
 -> implement/test
 -> commit + push
 -> integration review
 -> merge into main
 -> validate main
 -> rebuild frontend/dist on main if frontend changed
 -> push main
 -> remove worktree
 -> delete local + remote branch
```

Do not patch implementation directly on main.

---

## 22. Acceptance criteria

S4 is complete when:

1. Active Workspace can produce a normalized dataset manifest.
2. Every exported image has immutable identity/provenance fields.
3. AI and human labels remain distinguishable.
4. Lesion geometry remains in original-image coordinates.
5. Training eligibility is conservative and explainable.
6. AI-only data is never silently promoted to training ground truth.
7. Excluded/unresolved/ungradable records are not training-ready.
8. Dataset export contains no raw PHI/secrets by default.
9. `manifest.json`, `images.csv`, and `annotations.csv` are produced successfully.
10. Source images and case records are not mutated by export.
11. Datasets page provides a compact preview/status/export workflow.
12. S3 Worklist and frozen earlier milestones remain compatible.
13. Main is clean/synchronized and temporary branch/worktree is deleted.
