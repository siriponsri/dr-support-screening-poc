# S5C — Display / Analysis Derivatives & Delivery

**Branch:** `feat/s5c-derivative-delivery`  
**Base:** post-S5F main

## Goal

Make non-browser-native/high-fidelity sources usable by the existing viewer and remote-model workflow without confusing source identity with derivative identity.

## Display path

Prefer an additive display endpoint such as:

```text
GET /v1/images/{image_id}/display
```

Exact route may change after audit.

Behavior:

- JPEG/PNG may reuse original bytes when safe;
- TIFF/DICOM may use deterministic browser-safe derivatives;
- source remains untouched;
- cache keyed by source SHA + transform version;
- return correct media type;
- failures return safe actionable messages.

Do not remove the existing source-image route.

## Analysis path

Before remote inference choose an explicit analysis payload.

Record:

```text
source_sha256
analysis_sha256
transform description
source dimensions
analysis dimensions
coordinate mapping
```

Model API `image_sha256` MUST hash the exact bytes encoded in `image_b64`.

Do not send source DICOM SHA in that field when transmitting a derived PNG.

## Coordinate policy

If analysis dimensions equal canonical review dimensions:

```text
identity mapping
```

If dimensions change:

```text
explicit reversible mapping required
```

PRISM boxes must be mapped back to canonical review coordinates before persistence/display.

## Payload size

Do not silently downscale/recompress solely to satisfy the current remote payload cap.

If a high-resolution payload exceeds the contract and no validated safe transform exists, surface an explicit limitation.

## UI

Keep clinician workflow unchanged.

Needed behavior only:

- viewer transparently loads a supported display representation;
- compact warning when source cannot be displayed/decoded;
- original format and derivative facts may appear in Details/Audit;
- Worklist remains S3-density compatible.

## S4

Dataset export continues to use authoritative source SHA.

Derivative hashes are additive provenance.

## Preferred ownership

```text
dr_support/imaging/derivatives*.py
display/imaging API route
minimal route registration
frontend viewer image-source adapter
frontend/src/lib/api.ts additive imaging types
focused derivative tests
```

Do not implement DICOM parsing internals or duplicate detection.

## Acceptance

- JPEG/PNG viewer regression green;
- TIFF display verified;
- supported DICOM display verified after S5B integration;
- model payload hash equals exact transmitted bytes;
- source→analysis lineage retained;
- no annotation coordinate drift;
- current Lightning CFP flow remains functional.
