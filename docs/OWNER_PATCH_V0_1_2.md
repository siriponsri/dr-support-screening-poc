# Owner Patch — v0.1.2

Status: `PASS_WITH_WARNINGS` pending owner visual re-check and final annotation confirmation.

## Fixed

- Annotation overlay now uses imported CVAT corrections after sync instead of continuing to show only the original AI pre-label.
- AI pre-label remains visible as dashed/faded provenance when imported corrections exist.
- Imported rectangle, ellipse, polygon, polyline and points are rendered in the POC.
- START.cmd now falls back to an installed `uv` Python 3.12 when `py -3.12` is unavailable.
- Version bumped to 0.1.2.

## Preserved

- Raw provider output and bounded AI review subset remain unchanged.
- Imported annotations remain `IMPORTED_REQUIRES_REVIEW` until explicit confirmation.
- CVAT token remains environment-only.
- Mask sync remains unsupported and fails explicitly.

## Required owner acceptance

1. Start v0.1.2 using the existing local state or re-run the synthetic task.
2. Sync corrections.
3. Verify the corrected solid overlay differs from the dashed AI box.
4. Enter reviewer name and confirm imported annotations.
