# S2A Image Admission Specification

**Status:** Normative milestone specification  
**Milestone:** S2A1 — Image Admission Gate  
**Project:** DR Support Screening POC  

## 1. Purpose

S2A1 adds a conservative admission layer between the active Workspace input folder and the DR inference pipeline.

The admission layer must answer four questions in order:

1. Is this file a usable image?
2. Is it plausibly a retinal fundus image?
3. Is image quality acceptable, unresolved, or known to be inadequate?
4. Is the image currently eligible for DR inference?

S2A1 is a safety and data-quality milestone. It is not a new diagnostic model.

## 2. Scope

S2A1 includes:

- discovering supported image files from the active Workspace input folder;
- validating that files can be safely decoded;
- extracting basic image metadata;
- deterministic-first image admission;
- explicit separation of modality admission from image-quality state;
- auditable admission metadata and reason codes;
- clinician-friendly UI wording;
- manual review/override capability where needed;
- a centralized backend inference guard;
- compatibility with existing S1/S2 workflows and current demo fixtures.

S2A1 does not include:

- patient identity resolution;
- OCR;
- name/HN/DOB extraction;
- left/right eye resolution;
- patient grouping;
- longitudinal grouping;
- DICOM or PACS;
- XAI;
- model replacement, fine-tuning, or calibration;
- RETFound changes;
- PRISM-DR changes;
- CVAT workflow redesign;
- multi-database storage;
- automatic medical diagnosis of image quality.

Patient identity and laterality belong to S2A2.

## 3. Core Safety Principles

1. **Uncertain means review, not rejection.**
2. **Non-fundus and ungradable are different concepts.**
3. **Invalid files never reach DR inference.**
4. **Images with unresolved modality never reach DR inference by default.**
5. **Deterministic heuristics must be conservative.**
6. **No source file is deleted, moved, renamed, rewritten, or recompressed by admission.**
7. **The original admitted image remains immutable.**
8. **Technical rules are auditable but not exposed directly in the primary clinician UI.**
9. **Local paths remain local and are not sent to remote model providers.**
10. **Human review is authoritative for manual overrides.**

## 4. Conceptual Pipeline

```text
Active Workspace
      |
      v
Input Folder
      |
      v
File Discovery
      |
      v
Decode / Metadata Validation
      |
      v
Modality Admission
      |
      +---- FUNDUS_ACCEPTED
      +---- NEEDS_REVIEW
      +---- REJECTED_NON_FUNDUS
      +---- REJECTED_INVALID
      |
      v
Quality State
      |
      +---- GRADABLE
      +---- UNGRADABLE
      +---- NEEDS_REVIEW
      +---- NOT_EVALUATED
      |
      v
Inference Eligibility Guard
      |
      +---- eligible -> existing DR inference flow
      +---- blocked  -> clinician-facing note / review flow
```

Admission and quality are separate axes. The system must not collapse them into one generic status.

## 5. Internal State Model

### 5.1 `modality_admission`

Allowed values:

- `FUNDUS_ACCEPTED`
- `NEEDS_REVIEW`
- `REJECTED_NON_FUNDUS`
- `REJECTED_INVALID`

`FUNDUS_ACCEPTED` means there is sufficient evidence that the image is a retinal fundus image suitable to enter the DR workflow, subject to the quality state. It does not mean normal retina, no DR, clinically gradable, or diagnostically reliable.

`NEEDS_REVIEW` means the file is readable but the system lacks sufficient evidence to safely admit or reject it. This is the default state for ambiguity.

`REJECTED_NON_FUNDUS` means the image is confirmed not to be eligible for the retinal DR workflow. In S2A1, manual confirmation is preferred over aggressive automatic rejection.

`REJECTED_INVALID` means the file cannot be safely processed as a supported image, for example decode failure, corrupt file, unsupported format, or invalid dimensions.

### 5.2 `quality_state`

Allowed values:

- `GRADABLE`
- `UNGRADABLE`
- `NEEDS_REVIEW`
- `NOT_EVALUATED`

`GRADABLE` should only be assigned from an authorized source, reviewer, or future validated QC component.

`UNGRADABLE` means the image remains retinal but is known to be inadequate for the intended assessment.

`NEEDS_REVIEW` means there is a quality concern requiring human confirmation.

`NOT_EVALUATED` means no explicit quality determination has been made.

Weak deterministic heuristics must not silently claim clinical gradability.

## 6. Inference Eligibility

Eligible by default:

```text
modality_admission == FUNDUS_ACCEPTED
AND
quality_state IN {GRADABLE, NOT_EVALUATED}
```

Blocked by default when:

```text
modality_admission IN {
  NEEDS_REVIEW,
  REJECTED_NON_FUNDUS,
  REJECTED_INVALID
}
```

or:

```text
quality_state IN {
  UNGRADABLE,
  NEEDS_REVIEW
}
```

The backend must enforce this rule. Frontend hiding alone is not sufficient.

## 7. Manual Override

Authorized manual review may change admission or quality state.

Every override must retain:

- previous state;
- new state;
- reviewer identity or local reviewer label;
- timestamp;
- short reason or note.

The original automatic decision/reason must remain auditable.

## 8. File Discovery

Discovery operates only inside the active Workspace input folder.

Requirements:

- local-only;
- deterministic ordering where practical;
- no destructive file operation;
- avoid unsafe recursive link/junction loops;
- one bad file must not crash the entire scan;
- unsupported files must not become inference cases.

The implementation must audit the current project before deciding whether scanning is recursive or top-level-only.

## 9. Supported Formats

The implementation must audit actual decoder support before freezing the exact list.

Common raster formats may include:

- JPEG/JPG;
- PNG;
- TIFF/TIF if supported by the current local image stack.

Format support must be based on successful decoding, not extension alone.

Do not add DICOM in S2A1.

## 10. Deterministic Admission Rules

| Check | Strong outcome | Conservative fallback |
|---|---|---|
| File cannot be opened | `REJECTED_INVALID` | — |
| Unsupported non-image file | `REJECTED_INVALID` | — |
| Decoder fails | `REJECTED_INVALID` | — |
| Width/height invalid or zero | `REJECTED_INVALID` | — |
| Clearly unusable image structure | `REJECTED_INVALID` | `NEEDS_REVIEW` if ambiguous |
| Extremely small dimensions | `NEEDS_REVIEW` | Do not call non-fundus |
| Extreme aspect ratio | `NEEDS_REVIEW` | Do not call non-fundus |
| Nearly blank / near-uniform image | `NEEDS_REVIEW` | Do not claim ungradable automatically |
| Strong positive fundus plausibility evidence | `FUNDUS_ACCEPTED` | `NEEDS_REVIEW` |
| Weak/conflicting fundus evidence | `NEEDS_REVIEW` | — |
| Strong non-fundus evidence | Prefer manual confirmation | `NEEDS_REVIEW` |

### 10.1 Positive fundus plausibility

A deterministic fundus plausibility rule may combine weak signals such as:

- coherent retinal field;
- dark peripheral/background pattern;
- plausible retinal color/texture distribution;
- image geometry compatible with known CFP/UWF examples.

However:

- no single color threshold may decide admission;
- a circular field must not be required;
- a black border must not be required;
- filenames must not decide modality;
- camera-specific assumptions must not silently reject unfamiliar devices.

### 10.2 Automatic non-fundus rejection

S2A1 must be biased against false rejection.

If deterministic logic cannot justify a conservative automatic non-fundus decision, suspicious images must be routed to `NEEDS_REVIEW`.

`REJECTED_NON_FUNDUS` must remain available for manual review decisions.

## 11. Quality Rules

S2A1 supports quality states but does not need to implement a medical-quality classifier.

Deterministic checks may identify quality concerns and route an image to `quality_state = NEEDS_REVIEW`.

Examples:

- extreme darkness;
- extreme brightness;
- near-empty image;
- severe decode artifacts;
- dimensions below a policy minimum.

These must be described as quality concerns, not definitive clinical gradability judgments.

Existing trusted `ungradable` dataset labels may be imported as `UNGRADABLE` with provenance.

## 12. Required Admission Metadata

Each discovered/admitted image record must support, directly or through an additive related record:

```text
image_id
source_reference
filename
file_extension
file_size_bytes
width
height
channels_or_mode
modality_admission
quality_state
admission_method
admission_reason_code
quality_reason_code
created_at
updated_at
reviewed_by
reviewed_at
review_note
```

Local source references may contain sensitive context. They must not be sent to remote model services or unnecessarily exposed in the primary clinician UI.

## 13. Internal Reason Codes

Reason codes are for audit/debugging, not the primary clinician UI.

Examples:

```text
DECODE_FAILED
UNSUPPORTED_FORMAT
INVALID_DIMENSIONS
VERY_SMALL_IMAGE
EXTREME_ASPECT_RATIO
NEAR_UNIFORM_IMAGE
FUNDUS_PLAUSIBLE
FUNDUS_UNCERTAIN
MANUAL_ACCEPT
MANUAL_NON_FUNDUS
QUALITY_REVIEW_REQUIRED
DATASET_UNGRADABLE_LABEL
```

The final vocabulary may differ, but it must remain stable, explicit, and testable.

## 14. Clinician-Facing UI Rules

### 14.1 Do not expose internal enums

The primary clinician UI must not display raw internal values such as:

```text
REJECTED_NON_FUNDUS
REJECTED_INVALID
FUNDUS_ACCEPTED
DECODE_FAILED
EXTREME_ASPECT_RATIO
```

Instead, map internal states to short plain-language labels and notes.

### 14.2 Recommended mapping

| Internal state | Clinician label | Short note |
|---|---|---|
| `FUNDUS_ACCEPTED` | Ready for analysis | Retinal image accepted for automated analysis. |
| `NEEDS_REVIEW` | Needs review | Please confirm this image before analysis. |
| `REJECTED_NON_FUNDUS` | Cannot analyze | This image is not eligible for retinal DR analysis. |
| `REJECTED_INVALID` | Cannot analyze | This file could not be read as a supported image. |
| quality `NEEDS_REVIEW` | Image quality review | Please confirm image quality before analysis. |
| `UNGRADABLE` | Image quality issue | Image quality is not suitable for automated assessment. |
| `NOT_EVALUATED` | — | Do not imply that quality has been assessed. |

Exact copy may be refined, but the semantic distinctions must remain.

### 14.3 UI density

Primary UI should show:

- short status label;
- one short explanatory sentence when needed;
- a review action where appropriate.

Do not show by default:

- deterministic thresholds;
- rule formulas;
- raw reason-code names;
- multi-line technical diagnostics.

Technical details may be available in an audit/details view.

### 14.4 Color

Color is supplemental only.

Do not use:

- Medicine Green to mean clinically normal;
- Red Soil to mean disease;
- lesion colors for admission states.

Follow `DESIGN.md`.

## 15. Manual Review Actions

For unresolved images, the UI may offer concise actions such as:

- Accept as retinal fundus image;
- Mark as non-fundus;
- Mark image quality as acceptable;
- Mark image quality as inadequate;
- Leave unresolved.

Clinicians must not need to understand internal rule terminology.

## 16. Backend Inference Guard

The inference eligibility check must be centralized or otherwise guaranteed to apply to all current DR inference entry points.

Requirements:

- direct API calls cannot bypass the guard;
- blocked inference returns a clear non-diagnostic status/error;
- RETFound internals remain unchanged;
- PRISM-DR internals remain unchanged;
- remote provider contracts remain unchanged.

The implementation must audit current inference routes before choosing the guard location.

## 17. Compatibility

S2A1 must preserve:

- S1 fullscreen viewer behavior;
- annotation create/move/resize;
- lock/unlock;
- Coordinate Inspector;
- original-image coordinates;
- clinician-review semantics;
- CVAT behavior;
- RETFound behavior;
- PRISM-DR behavior;
- Remote Model API behavior;
- S2 Workspace Manager behavior;
- SQLite authoritative storage;
- legacy `/ui/`;
- `/app/` base path.

Existing synthetic/public demo fixtures and persisted cases must remain readable.

Legacy records without S2A1 fields require an explicit backward-compatible default. That default must not silently assert clinical gradability.

## 18. Persistence and Migration

Persistence changes must be additive.

Requirements:

- no destructive schema rewrite;
- existing review data preserved;
- legacy defaults documented;
- migration idempotent;
- existing S2 database opening tested;
- fresh database creation tested.

## 19. Auditability

The system must be able to answer:

- what state was assigned?
- when?
- by what method?
- why?
- automatic or manual?
- who changed it?
- what was the prior state?

Do not overwrite the only record of an earlier decision.

## 20. Error and Degraded Behavior

Expected degraded states include:

- input folder inaccessible;
- file disappears during scan;
- decoder unavailable;
- unsupported format;
- corrupt image;
- metadata extraction failure;
- admission-rule internal error.

One bad file must not crash the entire workspace scan.

Clinician-facing messages should remain short, for example:

- `File could not be read.`
- `Image needs review before analysis.`
- `Input folder is unavailable.`

Technical exception text belongs in logs/audit surfaces.

## 21. Testing Requirements

Tests must cover:

### File handling
- valid supported image;
- non-image file;
- corrupt image;
- invalid dimensions where representable;
- very small image;
- extreme aspect-ratio image;
- near-uniform image.

### Admission behavior
- strong valid fundus fixture can be accepted;
- ambiguous image -> `NEEDS_REVIEW`;
- invalid file -> `REJECTED_INVALID`;
- automatic logic does not aggressively classify ambiguity as non-fundus;
- manual non-fundus decision is supported;
- modality and quality remain independent.

### Quality behavior
- `FUNDUS_ACCEPTED + UNGRADABLE` is representable;
- `FUNDUS_ACCEPTED + NOT_EVALUATED` is representable;
- deterministic concern may become quality `NEEDS_REVIEW`;
- deterministic concern does not silently become a medical gradability claim.

### Inference guard
- `FUNDUS_ACCEPTED + GRADABLE` may infer;
- `FUNDUS_ACCEPTED + NOT_EVALUATED` may infer under current compatibility policy;
- modality `NEEDS_REVIEW` is blocked;
- `REJECTED_NON_FUNDUS` is blocked;
- `REJECTED_INVALID` is blocked;
- `UNGRADABLE` is blocked;
- quality `NEEDS_REVIEW` is blocked;
- direct API calls cannot bypass the guard.

### Compatibility
- existing demo fixtures still work;
- existing S2 workspace databases remain readable;
- S1 viewer tests remain unaffected;
- workspace switching remains unaffected.

## 22. Acceptance Criteria

S2A1 is complete only when:

1. Active Workspace input can be scanned without destructive file operations.
2. Invalid/non-image files cannot enter DR inference.
3. Ambiguous images are routed to review rather than aggressively rejected.
4. Non-fundus and ungradable remain separate states.
5. Admission metadata is persisted and auditable.
6. Backend inference eligibility is enforced centrally.
7. Clinician UI uses plain-language labels rather than internal enums.
8. Technical reason codes remain available for audit/debugging.
9. Manual review/override is auditable.
10. Existing S1/S2 behavior remains compatible.
11. Existing demo fixtures remain usable.
12. Focused and regression tests pass.
13. Frontend artifacts are rebuilt from the authoritative `main` worktree after integration, according to `AGENTS.md`.
14. Owner manual smoke testing confirms the clinician-facing workflow is understandable.

## 23. Explicitly Deferred to S2A2

S2A2 will address identity and eye grouping after S2A1 is stable.

Deferred items:

- filename-based patient-key parsing;
- local OCR of image header regions;
- OCR confidence/review workflow;
- pseudonymous patient key;
- laterality resolution;
- left/right grouping;
- multiple captures per eye;
- filename/OCR conflict detection;
- patient-level Worklist grouping.

S2A1 must not invent patient identity fields merely to anticipate S2A2 unless a minimal neutral extension point is clearly required.

## 24. Explicitly Deferred Beyond S2A

Outside S2A:

- PostgreSQL/MySQL/MongoDB storage;
- DICOM/PACS/DICOMweb;
- validated automated fundus quality model;
- XAI/heatmaps;
- model comparison or local fine-tuning;
- dataset/ROI training manifest;
- production PHI identity management.

## 25. Agent Execution Rule

This specification defines **what the milestone must achieve**.

Implementation agents decide **how to implement it** only after auditing the current repository.

If this specification conflicts with frozen S1/S2 behavior or would require an unsafe breaking change:

1. stop;
2. report the conflict;
3. propose the smallest compatible amendment;
4. wait for owner approval before changing this specification.

Do not silently weaken the safety rules or rewrite the specification to match an implementation shortcut.
