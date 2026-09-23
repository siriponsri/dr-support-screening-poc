---
status: Accepted (retrospective)
date: 2026-09-23
---

# ADR-0003: Keep the source immutable and send a separate, hashed analysis derivative to models

## Context and problem statement

DICOM and TIFF inputs cannot be sent to models or browsers as-is, yet dataset records must trace back to the exact admitted bytes and to original-pixel coordinates.

## Considered options

- Convert in place
- Keep the source immutable; create deterministic display and analysis derivatives with their own SHA-256 and coordinate mapping

## Decision outcome

The source file is never modified, and its SHA-256 is the case identity. `imaging/derivatives.py` prepares deterministic display and analysis representations (`transform_id`, derivative SHA-256, `CoordinateMapping`). Lesion boxes are mapped back to original pixels. An analysis payload above 20 MB (base64) is refused; it is never silently downscaled.

### Consequences

- Good: full lineage (source SHA → analysis SHA → model evidence); coordinates stay in original pixels.
- Bad: two identities to explain (Developer Technical Guide ch. 7); large images need a validated representation.

## More information

`dr_support/imaging/derivatives.py`, `tests/test_derivatives.py`.
