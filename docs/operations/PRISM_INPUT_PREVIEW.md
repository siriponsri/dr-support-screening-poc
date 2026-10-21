# PRISM input preview qualification boundary

Status: frontend preparation view and synthetic regressions only. No CPU preview
endpoint, immutable server cache or preview-bound inference route is implemented
by this change. PRISM submission from Review is paused. Global grading remains
an explicit separate action; historical PRISM evidence remains inspectable.
No model inference, database operation or clinical confirmation is performed by
opening the preview.

## What the clinician sees

**Preview PRISM input** stays in the single Review page. With the current API it
reports unavailable; an inspection-only case mask is never substituted for a
missing authoritative preparation response. A future compatible response can
show Original and the planned API submission side by side, with a conditional
FOV overlay, opacity, zoom, textual coverage legend and provenance disclosure.
The original image and original coordinates are preserved.

The supplied plan is accepted for display only after matching image ID, source
file hash, case revision, model version and preparation context. PNG assets must
be same-origin API paths and match their declared encoded SHA256 and dimensions.
Source, candidate mask/version, model, plan, case or revision changes immediately
hide old assets. Abort/generation cleanup suppresses late cross-case responses.
Expiry, missing bytes, hash mismatch or image decode failure invalidates display.
Browser verification covers encoded preview PNGs; server RGB/wire hashes remain
attestations, not independently verified final model tensors.

## Conditional is different from applied

The main-lane proposal `prism-pre-submission-preview.proposed.v1` established:

- CPU preparation can freeze the wire bytes and derive candidate FOV geometry.
- Native YOLO ROI executes inside PRISM inference. Before that work its state is
  `NOT_RUN`; the native bounding box and exact final lesion crop/tiles are unknown.
- External FOV is `CONDITIONAL_ON_NATIVE_ROI_SUCCESS`, never `APPLIED` in a
  preflight view. If native ROI fails, the locked baseline discards the FOV
  candidate and uses full Original. No v4/boundary candidate is adopted here.
- Optical FOV describes the photographic field, not validated retinal anatomy.
  Artifact exclusion and lesion boxes are separate concepts. Retained pixels do
  not imply a normal clinical result. Uncertain pixels are not silently excluded.

The provisional frontend DTO `prism-input-preview.v1` is an **adapter proposal**,
not a claim that the main API already emits it. It is an optional
`CaseRecord.prism_input_preview` read-only field. It accepts only API-submission
scope, `native_roi_status=NOT_RUN` and `internal_roi=NOT_PREVIEWED`. Claims that a
mask is already applied or that final model input is known are rejected. Its
`READY` means display metadata is complete, never permission to execute inference.

## Required main-lane fields and gates

Adopt one reviewed schema before enabling the path. Map the main proposal to the
UI adapter explicitly, including:

1. Immutable source file SHA256; dimension-bound decoded source RGB SHA256.
2. Actual frozen encoded wire SHA256, byte count, media type and dimensions.
   A lossless PNG preview of its decoded image has its own encoded PNG hash;
   neither hash substitutes for the other.
3. Source-to-wire coordinate mapping and transform/representation ID, version
   and hash. The UI adapter currently accepts one six-coefficient affine map
   `[a,b,c,d,e,f]`: `x'=a*x+c*y+e`, `y'=b*x+d*y+f`. Multi-stage crop/resize/tiling
   must be described separately by the backend; do not infer it from CSS.
4. FOV status/reason, canonical mask version/hash and separate encoded mask PNG
   hash. Original-coordinate **colored transparent overlay** uses green retained,
   red excluded and amber uncertain, plus textual percentages. A raw L-mode mask
   cannot be relabelled as this colored overlay. NONE has no hash/excluded pixels.
5. Conditional candidate RGB hash when actually computed; otherwise explicitly
   absent. Candidate application status, `NOT_RUN`, null native box, false exact
   lesion-input availability and null final crop/tensor hash before inference.
6. Model ID/version, source revision, all checkpoint hashes and preprocessing/
   configuration identity, immutable plan ID/hash, expiry, source/revision and
   preparation identity. The adapter's model-version check does not replace
   backend verification of the full pin set.

The current UI intentionally sends **zero** PRISM POST requests, even when the
provisional fixture plan is valid. Never fall back to the legacy lesion route.
Before restoring execution, implement and qualify atomic server binding across
all the above fields, source admission, authorized origin and unchanged baseline.
Reject changed/expired plans with conflict; do not silently regenerate different
pixels after acknowledgement. Persist accepted plan identity in run provenance.
Preview acknowledgement must never create a clinician grade or annotation review.

For an exact final-input preview, a later two-stage design must explicitly budget
native ROI inference: prepare/freeze wire and ROI/crop/tiles, return hashes and
transforms, then acknowledge and infer using that immutable result. This feature
is not implemented or qualified. The existing 47-request allocation is exhausted;
no hidden ROI forward, warmup or automatic retry is permitted in this task.

## Qualification and rollback

Synthetic tests cover missing/QC-only plans, Original fallback wording, conditional
FOV, distinct wire/preview hashes, malformed transforms, expiry, changed source/
mask/model, deferred cross-case responses, byte mismatch and decode failure.
They also assert that grading-only analysis never calls the PRISM route. Offline
browser captures intercept every request and reject mutations. These checks are
engineering evidence, not clinician UAT or real model qualification.

Rollback is a review-branch revert of this bounded UI commit. Do not revert the
previous workflow/provenance or hygiene commits, alter server thresholds, or
silently restore unbound PRISM submission as a workaround. No DB migration or
data cleanup is associated with this change.
