# S2A2 Patient / Eye Contract

Status: frozen additive contract for the S2A2 implementation.

This contract is subordinate to `docs/S2A2_PATIENT_EYE_RESOLVER_SPEC.md` and
does not change the S1 viewer, S2 workspace, S2A1 admission, or model contracts.

## Case fields

The fields below are additive JSON fields in the existing SQLite `cases.data`
record. Older records default to an unlinked state when read.

| Field | Values / shape | Meaning |
| --- | --- | --- |
| `patient_key` | pseudonymous string or `null` | Effective patient assignment; never a real name, HN, or DOB. |
| `patient_resolution_state` | `RESOLVED`, `NEEDS_CONFIRMATION`, `UNLINKED`, `CONFLICT` | Patient evidence state. |
| `patient_resolution_method` | `NONE`, `FILENAME`, `OCR`, `FILENAME_AND_OCR`, `MANUAL` | Provenance of the effective patient decision. |
| `patient_reason_code` | internal string | Audit reason; not primary UI copy. |
| `patient_candidate` | string or `null` | Candidate awaiting confirmation. |
| `patient_confidence_or_strength` | string or `null` | Non-numeric evidence strength when supplied. |
| `laterality` | `LEFT`, `RIGHT`, `UNKNOWN` | Effective eye side, independent of patient resolution. |
| `laterality_resolution_state` | `RESOLVED`, `NEEDS_CONFIRMATION`, `UNLINKED`, `CONFLICT` | Eye evidence state. |
| `laterality_resolution_method` | `NONE`, `FILENAME`, `OCR`, `FILENAME_AND_OCR`, `MANUAL` | Provenance of the effective eye decision. |
| `laterality_reason_code` | internal string | Audit reason; not primary UI copy. |
| `laterality_candidate` | `LEFT`, `RIGHT`, `UNKNOWN`, or `null` | Candidate awaiting confirmation. |
| `resolver_state` | `RESOLVED`, `NEEDS_CONFIRMATION`, `UNLINKED`, `CONFLICT` | Combined display/workflow state. |
| `resolver_evidence` | filename/OCR snapshot or `null` | Original automatic evidence; raw OCR text is never stored. |
| `resolution_history` | append-only event list | Automatic and manual resolution audit trail. |

`UNKNOWN` is a valid laterality value. A clinician can explicitly save it; it
does not imply that the patient is unresolved.

## API

`GET /v1/cases` and `GET /v1/cases/{image_id}` include the additive fields plus
`resolver_ui`, a clinician-safe projection. The primary React UI uses this
projection and does not render internal states, reason codes, or OCR statuses.

Manual confirmation uses:

```text
POST /v1/cases/{image_id}/resolver
```

Request fields:

```json
{
  "revision": 0,
  "reviewer": "Local clinician",
  "patient_action": "CONFIRM | SET | LEAVE_UNLINKED | KEEP",
  "patient_key": "PAT0001",
  "laterality_action": "SET | KEEP",
  "laterality": "LEFT | RIGHT | UNKNOWN",
  "note": "optional audit note"
}
```

The endpoint uses the existing optimistic revision guard. `CONFIRM` uses the
safe candidate, `SET` accepts a validated pseudonymous key, and
`LEAVE_UNLINKED` clears only the patient assignment. Eye changes never change
the patient assignment. Every accepted mutation records previous value, new
value, reviewer, timestamp, note, and automatic evidence.

## Filename rules

Parsing is full-stem and case-insensitive; the original filename is unchanged.
The patient token is a complete alphanumeric prefix containing letters and
digits, not an arbitrary substring. Supported forms are:

```text
PAT0001_L1.jpg       PAT0001_R1.jpg
PAT0001_LEFT_01.png PAT0001_RIGHT_01.png
PAT0001-L.jpg        PAT0001-R.jpg
FI3010_L1_APR.jpg    BK9881_R1_APR.jpg
PAT0001.jpg          PAT0001_CAPTURE_02.jpg
```

An explicit eye pattern resolves `LEFT` or `RIGHT`; a patient-only pattern
leaves the eye `UNKNOWN`. A non-matching or ambiguous suffix never silently
assigns an eye. `unknown_001.jpg` remains unlinked unless optional OCR proposes
a candidate, which still requires confirmation.

## Reconciliation

| Evidence | Patient result | Eye result |
| --- | --- | --- |
| Filename agrees or stands alone | `RESOLVED` | `RESOLVED` when known, otherwise `UNKNOWN` / unresolved |
| Filename patient only | `RESOLVED` | `UNKNOWN` until explicitly set |
| OCR candidate without filename patient | `NEEDS_CONFIRMATION` | `NEEDS_CONFIRMATION` when OCR supplies eye |
| Filename and OCR disagree | `CONFLICT` | Patient may remain resolved; conflicting eye is `CONFLICT` |
| No text, unavailable OCR, or OCR failure | no added evidence | no added evidence; image remains usable |

Patient and eye states are computed independently. Multiple image records may
share one patient key and one eye without being deduplicated; S3 owns grouping
and navigation.

## OCR boundary and privacy

The `OCRAdapter.extract(image, filename)` protocol is optional and returns
structured candidate evidence only. The default `DisabledOCRAdapter` performs
no network call. Adapter outcomes are `USABLE_CANDIDATE`, `NO_TEXT_DETECTED`,
`TEXT_UNUSABLE`, `OCR_UNAVAILABLE`, or `OCR_REQUEST_FAILED`.

Future adapters may be selected as `OFF`, `LOCAL_ONLY`, or an explicitly
authorized `REMOTE_OPT_IN` deployment. Credentials remain server-side; raw OCR
text is not returned to the frontend, persisted, or written to normal logs.
RETFound and PRISM-DR payload construction remains unchanged and contains no
patient, laterality, or OCR fields.
