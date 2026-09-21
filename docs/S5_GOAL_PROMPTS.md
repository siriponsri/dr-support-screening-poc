# Compact S5 Goal Prompts

## S5F Foundation

```text
/goal S5F — IMAGING FOUNDATION

Branch: feat/s5f-imaging-foundation

Read AGENTS.md plus:
docs/S5_MASTER_SPEC.md
docs/S5_FOUNDATION_SPEC.md

Before editing report repo/worktree/branch/HEAD/status.
If not on exact branch, STOP.

Implement only additive shared imaging contracts/hooks.
Preserve raster behavior, image_id compatibility, S1-S4 semantics,
Model API contract and S4 export.

No real DICOM decoding, frontend changes, PACS, or model changes.

Add focused compatibility/identity-lineage tests.

Validate, commit, push.
Do NOT merge main or delete worktree/branch.

Return SHA, changed files, contract summary, tests, overlap.
```

## S5A Integrity

```text
/goal S5A — SOURCE INTEGRITY

Branch: feat/s5a-integrity-core

Read AGENTS.md plus:
docs/S5_MASTER_SPEC.md
docs/S5A_INTEGRITY_CORE_SPEC.md

Before editing report repo/worktree/branch/HEAD/status.
If wrong branch, STOP.

Implement JPEG/PNG/TIFF source integrity:
authoritative source SHA, duplicate-content detection,
source-change detection, safe missing/decode states, no source mutation.

Consume S5F contracts.
Do not implement DICOM decoder or frontend.
Preserve admission and S4 semantics.

Test duplicate bytes, same filename changed bytes, TIFF,
corrupt/unsupported, deterministic scan and regression.

Validate, commit, push.
Do NOT merge main or delete worktree/branch.

Return SHA, changed files, tests, limitations, overlap.
```

## S5B DICOM

```text
/goal S5B — OPHTHALMIC DICOM INGEST

Branch: feat/s5b-dicom-ingest

Read AGENTS.md plus:
docs/S5_MASTER_SPEC.md
docs/S5B_DICOM_INGEST_SPEC.md

Before editing report repo/worktree/branch/HEAD/status.
If wrong branch, STOP.

Implement conservative local ophthalmic DICOM ingestion using S5F:
Part-10 recognition, source SHA, safe metadata allowlist,
single-frame decode, explicit codec readiness,
bit-depth/transfer-syntax provenance, no raw PHI/header dump.

No silent multi-frame frame selection.
No PACS/DICOMweb.
No frontend.
Never modify source DICOM.

Prefer optional DICOM dependencies.

Add synthetic/de-identified tests for uncompressed and available compressed
transfer syntaxes, corrupt and multi-frame behavior.

Validate, commit, push.
Do NOT merge main or delete worktree/branch.

Return SHA, dependency changes, tested transfer syntaxes, tests, limitations.
```

## S5C Derivatives

```text
/goal S5C — DISPLAY & ANALYSIS DERIVATIVES

Branch: feat/s5c-derivative-delivery

Read AGENTS.md plus:
docs/S5_MASTER_SPEC.md
docs/S5C_DERIVATIVE_DELIVERY_SPEC.md

Before editing report repo/worktree/branch/HEAD/status.
If wrong branch, STOP.

Implement deterministic display/analysis derivative delivery using S5F.

Preserve source SHA separately from derivative/analysis SHA.
Model API image_sha256 MUST hash exact transmitted image_b64 bytes.
Retain source->analysis lineage.

Add browser-safe display path for non-native sources without replacing originals.
Never silently downscale/recompress solely for payload limits.
Preserve/mapping-test annotation coordinates.

Keep Worklist compact and S1-S4 behavior unchanged.
Do not implement DICOM parser internals or PACS.

Validate viewer/API/model-proxy regression, commit, push.
Do NOT merge main or delete worktree/branch.

Return SHA, changed files, lineage design, tests, limitations, overlap.
```
