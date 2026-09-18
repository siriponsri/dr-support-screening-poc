# Live CVAT Acceptance — Owner Smoke Test

Date: 2026-09-18

CVAT Online project: `445923`
Task: `2603407`
Job: `4489044`

Observed live round-trip evidence on `SYNTH_001`:

- AI pre-label rectangle before CVAT edit: `[250.0, 160.0, 264.0, 176.0]`
- CVAT-imported rectangle after clinician edit: `[244.5546875, 145.220703125, 277.2546875000007, 179.12070312500146]`
- Backend review state after sync: `IMPORTED_REQUIRES_REVIEW`

This proves the live backend path `POC -> CVAT -> human edit -> sync back` changed geometry and preserved the original AI suggestion.

## v0.1.2 UI correction

v0.1.1 continued drawing the original bounded AI pre-label after sync even though the corrected geometry was present in `annotations`. v0.1.2 fixes the presentation layer:

- original AI rectangles remain visible as dashed/faded provenance;
- imported CVAT geometry is rendered as the primary solid overlay;
- rectangle, polygon, ellipse, points and polyline imported shapes are rendered;
- imported annotations still require explicit clinician confirmation;
- mask remains explicitly unsupported.

Owner should repeat `Sync corrections` once after installing v0.1.2 and visually verify the solid imported rectangle before confirming annotations.
