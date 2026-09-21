# S5F — Imaging Foundation Contract

**Branch:** `feat/s5f-imaging-foundation`

This is a short sequential prerequisite. Merge it before creating S5A/S5B/S5C.

## Goal

Create additive shared imaging contracts/hooks without implementing full DICOM decoding, duplicate detection, or frontend changes.

## Freeze these concepts

```text
source_sha256
source_format
source_media_type
source dimensions
display derivative
analysis derivative
derivative lineage
integrity status
```

## Recommended architecture

Prefer new bounded modules rather than further growing `admission.py`.

Example:

```text
dr_support/imaging/
  __init__.py
  contracts.py
  registry.py
```

Exact names may change after repository audit.

Provide a small handler/adapter boundary so later lanes can register:

```text
raster handler
dicom handler
display derivative builder
analysis derivative builder
```

without each lane rewriting scanning logic.

## Compatibility

- existing `BridgeImage` consumers remain functional;
- do not destructively redefine image_id;
- source SHA and derivative SHA are distinct;
- JPEG/PNG source-image routes continue to work;
- no S4 semantic change in this foundation lane.

## Tests

Prove:

- existing raster behavior remains;
- source-vs-derivative identity is representable;
- derivative lineage requires a source identity;
- unsupported handler fails conservatively;
- no PHI-oriented fields are introduced into public contracts.

## Non-scope

No real DICOM decoder.  
No frontend changes.  
No PACS.  
No model behavior changes.

## Completion

Validate, commit and push. Main then reviews/merges this branch before the three parallel S5 implementation lanes are created.
