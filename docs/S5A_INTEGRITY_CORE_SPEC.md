# S5A — Raster & Source Integrity Core

**Branch:** `feat/s5a-integrity-core`  
**Base:** post-S5F main

## Goal

Harden raster ingestion and source integrity while preserving S2A1 semantics.

## Scope

1. Preserve JPEG/PNG/TIFF ingestion.
2. Validate extension and decoded format coherently.
3. Record authoritative source SHA independent of derivatives.
4. Detect byte-identical duplicates across source references.
5. Detect source mutation when the same logical source later has changed bytes.
6. Surface missing/unreadable sources safely.
7. Never modify originals.
8. Preserve existing fundus/quality rules unless a frozen-contract conflict is found.

## Duplicate behavior

Same SHA across different filenames:

```text
DUPLICATE_CONTENT
```

Do not delete files automatically.

If current content-keyed identity collapses aliases, retain/report all aliases as integrity metadata.

## Source-change behavior

Same logical source reference + different SHA:

```text
SOURCE_CHANGED
```

Previous clinician state must not silently transfer to new bytes.

If durable mutation detection needs additive persisted metadata, use backward-compatible JSON defaults/migration.

## Preferred ownership

```text
dr_support/services/admission.py
dr_support/imaging/* integrity modules
dr_support/store.py additive defaults if necessary
tests/test_admission.py
tests/test_integrity.py
```

Avoid DICOM decoder internals and frontend/viewer files.

## Acceptance

- raster scan regression green;
- TIFF remains readable where Pillow supports it;
- duplicate bytes detected;
- source mutation detected;
- no source deletion/recompression;
- deterministic scan;
- no inference during scan;
- S4 preview/export remains functional.
