# WS05 — Multi-format Medical Image Acceptance Workspace

**Workspace name:** `WS05_MULTI_FORMAT_INTEGRITY`

## Purpose

Demonstrate what the current build actually supports across ingestion, decoding, display, analysis and provenance.

Use only public/synthetic/de-identified data.

## Suggested raster files

```text
PAT0501_L1.jpg
PAT0501_L2.jpeg
PAT0501_R1.png
PAT0501_R2.tif
PAT0501_RIGHT_03.tiff
```

Where useful, encode one public retinal image into JPEG/PNG/TIFF variants. These will normally have different source SHA values even if visually equivalent.

## Exact duplicate fixture

Create a byte-for-byte copy:

```text
PAT0502_L1.jpg
PAT0502_L2.jpg
```

Expected:

```text
same source SHA
duplicate-content evidence
no automatic deletion
```

## Source mutation fixture

1. scan `PAT0503_L1.jpg`;
2. record source SHA;
3. replace bytes while keeping filename;
4. rescan.

Expected:

```text
SOURCE_CHANGED
previous clinical state is not silently attached to new bytes
```

## DICOM fixtures

Synthetic/de-identified only.

Preferred set:

```text
OPH_8BIT_UNCOMPRESSED.dcm
OPH_8BIT_JPEG_BASELINE.dcm
OPH_8BIT_JPEG2000_LOSSLESS.dcm
OPH_16BIT_UNCOMPRESSED.dcm
OPH_MULTIFRAME.dcm
CORRUPT.dcm
```

Include compressed variants only when transfer syntax and fixture provenance are known.

## Capability matrix

Fill from observed behavior, not assumptions.

| Source | Ingest | Decode | Viewer | Analysis | Source provenance |
|---|---|---|---|---|---|
| JPEG | TBD | TBD | TBD | TBD | TBD |
| PNG | TBD | TBD | TBD | TBD | TBD |
| TIFF | TBD | TBD | TBD | TBD | TBD |
| DICOM uncompressed | TBD | TBD | TBD | TBD | TBD |
| DICOM JPEG Baseline | TBD | TBD | TBD | TBD | TBD |
| DICOM JPEG 2000 lossless | TBD | TBD | TBD | TBD | TBD |
| DICOM 16-bit | TBD | TBD | TBD | TBD | TBD |
| DICOM multi-frame | TBD | TBD | TBD | TBD | TBD |

Allowed labels:

```text
Supported
Needs review
Codec required
Unsupported
Not tested
```

## Owner smoke

1. Open WS05.
2. Scan folder.
3. Every file gets a clear outcome; one bad file must not crash the scan.
4. Open supported JPEG/PNG.
5. Open TIFF.
6. Open supported DICOM through display derivative.
7. Verify source-format details live outside the primary Worklist.
8. Confirm no patient demographics/private DICOM fields appear.
9. Analyze one normal CFP raster through Lightning.
10. Analyze one supported DICOM-derived CFP if marked compatible.
11. Confirm source SHA and analysis SHA are distinguishable.
12. Edit/reload annotation and confirm coordinates do not drift.
13. Export S4 manifest.
14. Verify exported identity traces to authoritative source bytes.
15. Verify duplicate/source-changed cases are not silently treated as clean independent ground truth.

## PACS

PACS/DICOMweb is explicitly out of WS05.

Future connector milestone may add:

```text
QIDO-RS -> discover
WADO-RS -> retrieve
```

after S5 freezes local DICOM ingestion.
