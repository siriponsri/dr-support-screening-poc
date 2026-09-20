# S2A1 Image Admission Handoff

This implementation follows `docs/S2A_IMAGE_ADMISSION_SPEC.md` without changing
the S1 viewer, S2 workspace contract, or model/provider contracts.

## Runtime behavior

- `POST /v1/admissions/scan` scans only the active Workspace `input_folder`.
- Discovery is top-level, deterministic by case-folded filename, local-only,
  non-destructive, and resilient to one-file failures.
- Supported decoder formats are JPEG/JPG, PNG, and TIFF/TIF. Decode success is
  required for readable admission; extension alone never creates an image case.
- Readable files receive conservative modality and quality decisions. Ambiguity
  becomes `NEEDS_REVIEW`; automatic logic never assigns `REJECTED_NON_FUNDUS`.
- Unsupported, corrupt, unreadable, and invalid files remain auditable cases
  with `REJECTED_INVALID` and cannot be served or inferred.

## Persistence and compatibility

Admission data is stored as additive JSON fields in the existing SQLite case
records. No table rewrite or source-file mutation is performed. Existing cases
without admission data receive:

- modality: `FUNDUS_ACCEPTED`;
- quality: `NOT_EVALUATED`;
- method: `LEGACY_COMPAT`;
- reason: `LEGACY_ADMITTED`.

This keeps existing public/synthetic fixtures readable without asserting
clinical gradability.

## Inference and review

The review API applies one eligibility predicate to both `/v1/infer/global` and
`/v1/infer/lesion-roi`:

```text
FUNDUS_ACCEPTED and (GRADABLE or NOT_EVALUATED)
```

The standalone model API applies the same conservative check to decoded CFP
payloads at `/v1/predict/dr` and `/v1/predict/lesions`. Its frozen request and
response envelopes remain unchanged; unsupported UWF requests still return the
existing `UNSUPPORTED` result without entering DR inference.

Manual decisions use `POST /v1/cases/{image_id}/admission`. Each decision keeps
the previous state, new state, reviewer, timestamp, note, and reason codes in
`admission_history` and the normal case event stream.

The primary React UI renders plain-language status labels and short notes. Raw
states and reason codes remain in the API record for audit/debugging and are not
used as primary clinician copy.
