# S5 — Medical Image Ingestion & Data Integrity

**Status:** Normative milestone specification  
**Project:** DR Support Screening POC  
**Depends on:** frozen S1–S4

## 1. Purpose

S5 makes image ingestion format-aware and clinically safer without changing the clinician workflow.

Current raster admission supports JPEG, PNG and TIFF-family files. S5 adds a defensible ophthalmic DICOM path while making source identity, derivative identity, duplicate detection and source-change detection explicit.

PACS is not a file format. Direct PACS/DICOMweb networking is deferred until local DICOM ingestion is proven.

## 2. Hero flow

```text
immutable source bytes
      |
      +-- source SHA-256 / format / dimensions / safe metadata
      |
      +-- decoded master when required
      |      |
      |      +-- display derivative
      |      |
      |      +-- analysis payload
      |
      +-- export provenance back to the source
```

The app must never silently replace the authoritative source with a derivative.

## 3. Source classes

### Raster baseline

```text
JPEG: .jpg .jpeg
PNG:  .png
TIFF: .tif .tiff
```

### DICOM target

S5 targets ophthalmic photography first.

Priority object classes:

- Ophthalmic Photography 8 Bit Image Storage
- Ophthalmic Photography 16 Bit Image Storage

Wide-field objects may be ingested if frame and pixel semantics are explicit, but S5 must not claim model support where current RETFound/PRISM behavior is unsupported.

### Non-scope

- OCT interpretation pipeline
- PACS/DICOMweb networking
- DICOM C-FIND/C-STORE
- arbitrary multi-frame frame selection
- DICOM write-back
- model training/calibration

## 4. Identity model

Do not overload one hash with multiple meanings.

### Source identity

```text
source_sha256 = SHA256(exact source-file bytes)
```

This is authoritative for source integrity and S4 lineage.

### Analysis identity

```text
analysis_sha256 = SHA256(exact bytes sent to the Model API)
```

For ordinary JPEG/PNG this may equal source SHA. For TIFF/DICOM requiring conversion it may differ.

### Display identity

Display derivatives must have their own hash and lineage and must never replace `source_sha256`.

### Existing image_id

Do not silently redefine existing `image_id` semantics across frozen databases. Any evolution must be additive and backward compatible.

## 5. Fidelity policy

1. Never rewrite/recompress the source file.
2. Reuse source bytes directly when viewer/model compatibility safely permits.
3. When decode/conversion is required, create the highest-fidelity deterministic representation practical.
4. Supported 8-bit color ophthalmic DICOM may use lossless PNG as decoded/display derivative when semantics allow.
5. Higher bit-depth content should retain bit-depth facts and a high-fidelity master representation where practical.
6. Display/model derivatives may differ from master but transformations must be recorded.
7. Never describe a derivative as recovering information already lost in a lossy source transfer syntax.

## 6. DICOM privacy and metadata

DICOM may contain PHI and quasi-identifiers.

Default behavior:

- parse locally;
- never send raw DICOM headers to the remote Model API;
- never persist/export/log a full DICOM dataset;
- extract an explicit technical allowlist only;
- never expose patient name, HN/MRN, DOB, accession data, person/institution fields, free text or private tags in primary UI;
- raw UIDs are not exported by default; pseudonymous/hashed technical references may be used when needed.

Useful technical metadata may include:

```text
SOP class category
transfer syntax category
rows / columns
samples per pixel
photometric interpretation
bits allocated / bits stored
number of frames
laterality candidate when explicitly present
```

DICOM laterality is evidence, not an irreversible assignment.

## 7. DICOM decoding

Use `pydicom` as parser boundary.

Compressed Pixel Data requires explicit tested decoder support. Prefer a tested decoder stack compatible with the repository's Python constraints.

Missing codecs must produce a specific readiness state, not a generic crash.

Exercise where fixtures/runtime permit:

- uncompressed Little Endian
- JPEG Baseline
- JPEG Lossless
- JPEG-LS
- JPEG 2000 lossless/lossy

Do not claim support for a transfer syntax unless the current runtime actually decodes it.

## 8. Frame policy

No silent frame selection.

```text
single-frame -> normal S5 decode path
multi-frame  -> metadata ingest + explicit unsupported/review state
```

A later milestone may add frame/series selection.

## 9. Integrity states

Technical/audit states may include:

```text
OK
DUPLICATE_CONTENT
SOURCE_CHANGED
SOURCE_MISSING
UNSUPPORTED_FORMAT
DICOM_CODEC_REQUIRED
DICOM_MULTIFRAME_UNSUPPORTED
DECODE_FAILED
DERIVATIVE_FAILED
```

Primary clinician UI must translate these into concise wording.

No integrity scan may delete source data or clinician review state.

## 10. Duplicate content

Different source references may contain byte-identical content.

S5 must detect identical `source_sha256` values.

Do not delete or merge automatically.

If current content-keyed case identity collapses aliases, preserve duplicate source references in integrity metadata and document that limitation.

## 11. Source mutation

Same source reference/filename but changed bytes:

```text
old source SHA != new source SHA
```

must surface `SOURCE_CHANGED`.

Previous review/annotations must not silently transfer to the changed bytes.

## 12. Derivative lineage

Every derivative should answer:

```text
Which source produced this?
Which transform produced this?
What is the output hash?
What are output dimensions?
What coordinate mapping applies?
```

Recommended fields:

```text
source_sha256
derivative_sha256
purpose = DISPLAY | ANALYSIS | MASTER
format
width
height
bit_depth where known
transform_id / transform_description
coordinate_space
created_at
```

## 13. Coordinate integrity

Stored lesion geometry remains tied to the canonical review-image pixel space.

If a derivative changes dimensions:

- persist an explicit mapping;
- never store derivative-local coordinates as original;
- map PRISM outputs back to canonical review coordinates before persistence.

Display-only resize must never mutate stored annotations.

## 14. Model API compatibility

Existing remote model contract remains valid.

The Model API field `image_sha256` continues to mean:

> SHA-256 of exact bytes contained in `image_b64`.

When a DICOM/TIFF source is converted before inference, send the derivative hash in the request and retain local lineage:

```text
source_sha256 -> analysis_sha256 -> model-result provenance
```

Do not send raw DICOM PHI to the Model API.

## 15. S4 compatibility

S4 remains authoritative for dataset semantics.

For derived DICOM/raster cases:

- exported source identity should trace to source SHA;
- derivative lineage is additive;
- AI-only remains AI-only;
- HUMAN/CVAT provenance remains unchanged;
- no automatic training-ready promotion.

## 16. Capability reporting

Report separately:

```text
FORMAT / TRANSFER SYNTAX
INGEST
DECODE
VIEW
ANALYSIS
PROVENANCE
```

A capability is `Supported` only if exercised by the current environment/fixture.

Otherwise use `Not tested`, `Codec required`, `Needs review` or `Unsupported`.

## 17. Performance

- no inference during folder scan;
- avoid full pixel decode merely to list large DICOM when metadata inspection suffices;
- decode when derivative generation is needed;
- cache derivatives by source hash + transform version;
- invalidate cache when source lineage changes.

## 18. Security

- no raw PHI/header dumps;
- no tokens in exports;
- safe error messages;
- source paths remain local technical details;
- source files remain read-only from the application's perspective.

## 19. Acceptance

S5 is complete when:

1. JPEG/PNG/TIFF baseline still works.
2. Supported ophthalmic DICOM can be recognized and decoded locally.
3. Original DICOM bytes remain untouched.
4. Browser gets a safe display representation where needed.
5. Analysis uses an explicit payload with its own SHA.
6. Source-to-analysis lineage is auditable.
7. Duplicate content is detectable.
8. Source mutation is detectable.
9. Multi-frame DICOM is not silently reduced to one frame.
10. No raw PHI/header dump reaches UI/export/model API.
11. S4 manifest continues to reference authoritative source identity.
12. Annotation coordinates remain correct.
13. WS05 capability matrix is owner-verified.
14. S1–S4 regressions remain green.
