# S5B — Ophthalmic DICOM Ingestion

**Branch:** `feat/s5b-dicom-ingest`  
**Base:** post-S5F main

## Goal

Add conservative local DICOM recognition, safe metadata extraction and high-fidelity pixel decoding for ophthalmic photography.

## Primary target

Where fixtures permit, support:

- Ophthalmic Photography 8 Bit Image Storage
- Ophthalmic Photography 16 Bit Image Storage

Do not claim OCT/UWF model support merely because DICOM parsing succeeds.

## Parser

Use `pydicom`.

Prefer standards-conformant Part 10 files. Avoid broadly forcing arbitrary bytes into DICOM interpretation.

## Pixel codecs

Compressed DICOM support requires explicit tested decoders.

A compatible optional stack may include:

```text
pydicom
pylibjpeg
pylibjpeg-libjpeg
pylibjpeg-openjpeg
```

Add only what is needed and compatible with repository Python constraints.

Missing decoder:

```text
DICOM_CODEC_REQUIRED
```

not a generic crash.

## Safe metadata allowlist

Never persist/export/log a full DICOM header.

Technical allowlist may include:

```text
SOP class category
transfer syntax category
rows / columns
samples per pixel
photometric interpretation
bits allocated / bits stored
number of frames
laterality candidate if explicitly available
```

Do not expose:

```text
PatientName
PatientID / MRN / HN
DOB
AccessionNumber
institution/person names
private tags
free-text fields
```

Raw UIDs should not appear in default clinician/export payloads.

## Frame policy

```text
NumberOfFrames == 1 -> normal decode path
NumberOfFrames > 1  -> DICOM_MULTIFRAME_UNSUPPORTED
```

No silent first-frame selection.

## Fidelity

- source DICOM bytes are immutable;
- source SHA retained;
- pixel decode deterministic;
- bit-depth facts retained;
- high-fidelity master produced only when needed;
- 8-bit color fundus may use lossless PNG derivative;
- higher-bit-depth master must not be silently crushed to 8-bit as the authoritative master;
- never claim recovery of details lost by lossy source compression.

## Laterality

DICOM laterality is resolver evidence only and must flow through existing S2A2 conflict/confirmation semantics.

## Dependencies

Prefer a `[dicom]` optional dependency group rather than forcing all review installations to install codecs.

## Preferred ownership

```text
dr_support/imaging/dicom*.py
DICOM contracts/helpers
pyproject.toml DICOM extras
tests/test_dicom*.py
```

Avoid frontend and S5A duplicate engine.

## Test matrix

Use synthetic/de-identified fixtures only.

Where available:

```text
Part 10 uncompressed
JPEG Baseline
JPEG Lossless
JPEG-LS
JPEG 2000 lossless
JPEG 2000 lossy
corrupt DICOM
multi-frame
```

Each result must be explicit: supported, codec-required, unsupported, or decode-failed.
