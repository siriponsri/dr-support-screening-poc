# S2A2 Patient / Eye Resolver Specification

**Status:** Normative milestone specification  
**Milestone:** S2A2 — Patient / Eye Resolver  
**Project:** DR Support Screening POC  

## 1. Purpose

S2A2 links admitted retinal images to a pseudonymous patient key and eye side before the Clinical Worklist milestone.

The resolver must combine available evidence conservatively:

1. filename / path-safe metadata;
2. existing local mapping, if present;
3. optional OCR fallback;
4. manual clinician confirmation.

The resolver is not a medical identity system and must not silently invent patient identity.

## 2. Scope

S2A2 includes:

- filename-based patient candidate parsing;
- filename-based laterality parsing;
- optional OCR fallback when filename/metadata is insufficient;
- deterministic reconciliation of multiple evidence sources;
- pseudonymous `patient_key`;
- laterality values `LEFT`, `RIGHT`, `UNKNOWN`;
- support for multiple captures per patient and per eye;
- conflict and unresolved states;
- clinician-friendly confirmation UI;
- audit history for automatic and manual resolution;
- compatibility with S1, S2, and frozen S2A1.

S2A2 does not include:

- production EMR/HIS integration;
- DICOM patient identity;
- PACS;
- diagnosis;
- model comparison;
- XAI;
- dataset export logic;
- full S3 worklist grouping/filter UX;
- external OCR as a mandatory dependency.

## 3. Core Principles

1. **Patient != image.**
2. **Laterality != identity.**
3. **OCR failure is not workflow failure.**
4. **No text is a valid condition.**
5. **Filename/metadata first, OCR fallback second.**
6. **Conflicting evidence must require confirmation.**
7. **Clinician UI must not expose internal resolver enums or OCR error codes.**
8. **Remote inference must not receive patient identity, raw OCR text, local paths, names, HN, or DOB.**
9. **Human confirmation is authoritative.**

## 4. Conceptual Flow

```text
Admitted retinal image
        |
        v
Filename / Safe Metadata Parser
        |
        v
Enough evidence?
   | YES                 | NO
   v                     v
Resolver             Optional OCR Fallback
   |                     |
   +----------+----------+
              v
      Evidence Reconciliation
              |
              +---- RESOLVED
              +---- NEEDS_CONFIRMATION
              +---- UNLINKED
              +---- CONFLICT
              |
              v
      Patient / Eye Assignment
              |
              v
       Manual confirmation
```

## 5. Internal Resolution States

Allowed values:

- `RESOLVED`
- `NEEDS_CONFIRMATION`
- `UNLINKED`
- `CONFLICT`

`RESOLVED` means sufficient non-conflicting evidence exists for the patient key and, separately, any known laterality.

`NEEDS_CONFIRMATION` means a plausible candidate exists but evidence is not strong enough for automatic assignment.

`UNLINKED` means no usable patient candidate exists. This is not an error.

`CONFLICT` means evidence sources disagree materially. The system must not auto-resolve a conflict.

## 6. Patient Identity Model

Use a pseudonymous key such as:

```text
PAT0001
PAT0002
P000042
```

S2A2 must not require real patient names for normal workflow.

Suggested logical fields:

```text
patient_key
patient_resolution_state
patient_resolution_method
patient_reason_code
patient_candidate
patient_confidence_or_strength
```

## 7. Laterality Model

Allowed values:

- `LEFT`
- `RIGHT`
- `UNKNOWN`

Laterality resolution is independent from patient resolution.

A resolved patient may validly remain:

```text
patient = PAT0001
laterality = UNKNOWN
```

Support multiple images per eye:

```text
PAT0001
├─ LEFT
│  ├─ capture 1
│  └─ capture 2
└─ RIGHT
   └─ capture 1
```

## 8. Filename Parsing

Support explicit, conservative patterns such as:

```text
PAT0001_L1.jpg
PAT0001_R1.jpg
PAT0001_LEFT_01.png
PAT0001_RIGHT_01.png
PAT0001-L.jpg
PAT0001-R.jpg
```

Project-observed patterns such as these may also be supported:

```text
FI3010_L1_APR.jpg
BK9881_R1_APR.jpg
```

Rules:

- parsing must be explicit and testable;
- do not infer identity from arbitrary substrings;
- do not infer laterality from ambiguous isolated letters unless the pattern is explicitly recognized;
- preserve original filenames unchanged;
- filename parsing must not depend on OCR availability.

## 9. OCR Fallback

OCR is optional and should run only when filename/metadata evidence is insufficient or needs confirmation.

OCR may produce candidates such as:

```text
patient identifier
laterality
capture date
```

S2A2 does not require full demographic extraction.

OCR outcomes must distinguish internally:

- usable candidate text found;
- no text detected;
- text detected but unusable;
- OCR unavailable;
- OCR request failed.

These are not clinician-facing error labels.

### OCR adapter boundary

The architecture should allow optional OCR providers.

An external provider such as Typhoon OCR may be supported as an optional adapter, but S2A2 must not make the application depend on it.

Recommended modes:

```text
OFF
LOCAL_ONLY
REMOTE_OPT_IN
```

If remote OCR is enabled:

- explicit configuration/authorization is required;
- credentials stay server-side;
- secrets never reach the frontend;
- prefer a text/header crop instead of the full image when sufficient;
- do not send patient-identifying content unless the deployment owner has approved that data flow.

## 10. Deterministic Reconciliation

| Filename evidence | OCR evidence | Result |
|---|---|---|
| Patient + eye resolved | not needed | `RESOLVED` |
| Patient resolved, no eye | not needed or optional | Patient `RESOLVED`, eye `UNKNOWN` |
| Patient resolved | no text | `RESOLVED` |
| Patient resolved | OCR agrees | `RESOLVED` |
| Patient resolved | OCR disagrees | `CONFLICT` |
| No patient | OCR gives plausible patient | `NEEDS_CONFIRMATION` |
| No patient | OCR gives no text | `UNLINKED` |
| No patient | OCR unavailable/fails | `UNLINKED` |
| Ambiguous filename | OCR agrees with candidate | `NEEDS_CONFIRMATION` unless explicitly safe |
| Laterality conflict | filename/OCR disagree | Patient may remain resolved; eye requires confirmation |

The implementation must remain conservative.

## 11. Minimal Demo Dataset

A four-image demo can use public/de-identified fundus images copied under synthetic filenames:

```text
DEMO001_L1.jpg
DEMO001_L2.jpg
DEMO001_R1.jpg
UNKNOWN_001.jpg
```

Expected grouping:

```text
DEMO001
├─ Left
│  ├─ Capture 1
│  └─ Capture 2
└─ Right
   └─ Capture 1

Unlinked
└─ UNKNOWN_001.jpg
```

This demonstrates:

- one patient != one image;
- multiple captures per eye;
- left/right separation;
- an unlinked image without treating it as an error.

## 12. Clinician-Facing UI

Do not expose raw internal values such as:

```text
RESOLVED
CONFLICT
OCR_FAILED
NO_TEXT_DETECTED
UNRESOLVED_LATERALITY
```

Recommended mapping:

| Internal situation | UI label | Short note |
|---|---|---|
| Patient resolved | Patient matched | Patient information was matched for this image. |
| Candidate requires review | Please confirm patient | Patient information was found but needs confirmation. |
| No patient evidence | Patient not linked | Choose a patient to continue. |
| Conflicting identity evidence | Patient information needs review | The available patient information does not match. |
| Laterality unresolved | Eye side needs confirmation | Choose Left or Right. |
| OCR unavailable/no text | No primary error | Continue with available information. |

Primary UI should prefer short labels and direct actions.

## 13. Manual Confirmation

Authorized users must be able to:

- confirm a proposed patient;
- choose/create a pseudonymous patient key;
- change patient assignment;
- choose Left / Right / Unknown;
- resolve a conflict;
- leave an image unlinked.

Every manual change must preserve:

- previous effective value;
- new value;
- timestamp;
- reviewer/local user label;
- reason or note where appropriate;
- original automatic evidence/provenance.

## 14. Privacy Boundary

S2A2 may eventually encounter PHI.

Therefore:

- patient keys used by review/model workflows should be pseudonymous;
- real name/HN/DOB/raw OCR text must not be sent to RETFound, PRISM-DR, or other remote inference services;
- raw OCR text should not be copied into general application logs;
- OCR credentials remain server-side;
- local source paths remain local;
- engineering/demo tests should use public/de-identified or synthetic identifiers.

A future production identity vault is outside S2A2.

## 15. Persistence

Persistence must be additive and backward compatible.

Suggested logical fields:

```text
patient_key
patient_resolution_state
patient_resolution_method
patient_reason_code
laterality
laterality_resolution_method
laterality_reason_code
resolved_by
resolved_at
resolution_note
```

Automatic evidence and manual overrides must remain auditable.

Legacy S2A1 records without identity fields must remain readable and should default to an unresolved/unlinked state.

## 16. Compatibility

S2A2 must preserve:

- S1 viewer behavior;
- annotation geometry;
- S2 Workspace Manager;
- S2A1 admission/inference guard;
- SQLite authoritative storage;
- RETFound behavior;
- PRISM-DR behavior;
- CVAT integration;
- existing demo/public cases;
- `/ui/`;
- `/app/`.

Patient/eye resolution must not weaken the S2A1 admission gate.

## 17. Testing Requirements

Tests must cover:

### Filename parsing
- patient + LEFT;
- patient + RIGHT;
- multiple captures;
- patient with unknown laterality;
- unknown filename;
- mixed case/extensions;
- known project naming pattern.

### Reconciliation
- filename resolved, OCR absent;
- filename resolved, OCR agrees;
- filename resolved, OCR conflicts;
- filename absent, OCR candidate;
- filename absent, OCR no text;
- OCR unavailable/failure;
- patient resolved with laterality unresolved;
- laterality conflict without losing valid patient identity.

### Manual review
- confirm patient;
- change patient;
- choose laterality;
- resolve conflict;
- leave unlinked;
- history preserved.

### Privacy
- patient/OCR data not sent to remote inference payloads;
- secrets absent from frontend/API responses;
- raw OCR text absent from normal logs where feasible.

### Compatibility
- S2A1 inference guard still applies;
- existing persisted records load;
- current workspaces remain functional.

## 18. Acceptance Criteria

S2A2 is complete when:

1. admitted retinal images can be linked to pseudonymous patients;
2. multiple images can belong to one patient;
3. multiple captures can belong to one eye;
4. left/right/unknown laterality are represented safely;
5. filename parsing works for frozen supported patterns;
6. OCR is optional fallback rather than mandatory dependency;
7. no text/OCR failure does not break workflow;
8. conflicts require manual confirmation;
9. clinician UI uses plain-language labels/actions;
10. manual changes are auditable;
11. patient identity data does not enter remote DR inference payloads;
12. legacy S2A1 data remains readable;
13. regression validation passes;
14. owner smoke test confirms grouping and manual correction are understandable.

## 19. Deferred to S3

S3 Clinical Worklist will consume S2A2 outputs and add:

- patient grouping;
- eye grouping;
- linked/unlinked filters;
- review-status filters;
- search;
- worklist navigation;
- compact patient/eye presentation.

S2A2 should provide the data contract needed by S3 but must not build the full S3 worklist.

## 20. Agent Execution Rule

This specification defines **what S2A2 must achieve**.

Implementation agents decide **how** only after auditing the current repository.

If this specification conflicts with frozen S1/S2/S2A1 behavior or requires unsafe PHI handling:

1. stop;
2. report the exact conflict;
3. propose the smallest compatible amendment;
4. wait for owner approval before changing this specification.

Do not silently weaken privacy, auditability, or clinician-facing semantics.
