# PRISM input preview qualification boundary

Status: CPU preview/receipt routes and a one-use binding service are implemented
and tested with in-memory stores and fake providers. Existing production local/
remote PRISM adapters do not implement the frozen-plan protocol and therefore
return503 rather than enable submission. No real provider qualification is
claimed. Global grading remains separate; historical evidence stays inspectable.
Opening the panel makes no model request. Explicit preparation performs CPU work
only; submission through a qualified adapter would execute model work and needs
its own authorized workload budget.

## What the clinician sees

**Preview PRISM input** stays in the single Review page. **Prepare / refresh API
input** obtains a server receipt or an explicit unavailable error. An inspection-
only case mask is never substituted for missing preparation. A compatible response can
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

The additive DTO `prism-input-preview.v1` is returned by the preparation route.
The optional `CaseRecord.prism_input_preview` field remains a display-fixture/
compatibility input; case GET does not create receipts or run preparation.
The DTO accepts only API-submission
scope, `native_roi_status=NOT_RUN` and `internal_roi=NOT_PREVIEWED`. Claims that a
mask is already applied or that final model input is known are rejected. Its
`READY` means display metadata is complete. Submission additionally requires
`submission_binding_enforced=true`, verified displayed assets, explicit input
acknowledgement and an unconsumed matching server receipt. A checkbox alone grants
no authority and never confirms a grade or lesion annotation.

## Implemented endpoints and provider boundary

- POST `/v1/cases/{image_id}/prism-input-preview`: revision/model request;
  CPU-only frozen source/wire, candidate mask, transform and model/config pins.
- GET `/v1/cases/{image_id}/prism-input-preview/{token}/assets/{name}`: private
  opaque same-origin original/input/overlay PNGs, `Cache-Control: no-store`.
- POST `/v1/cases/{image_id}/prism-input-preview/{token}/infer`: receipt fields
  must match exactly. Returns verified result, APPLIED/STALE_RESULT and invocation
  receipt. Failure consumes the token too; no implicit retry.
- Legacy v1/v2 review PRISM inference is rejected409. Global grading and synthetic
  mock-lesion routes are unchanged. No gateway/model-API route is changed here.

The process-local cache holds at most16 plans/128MiB encoded inputs and assets,
with300second monotonic expiry. Restart/eviction requires a new preview. The
qualified review configuration is one worker; `WORKERS` other than1 fails closed.
Do not override deployment worker arguments to claim distributed locking.
Submission checks expiry again after waiting for the provider lock. Source,
wire, mask, model pins, configuration, transform, admission, revision and workspace
are rechecked immediately before provider execution. Sibling tokens are invalidated
when one is consumed, so concurrent calls cannot replay the same preparation.

A trusted provider must implement `prism_preview_protocol=prism-wire-binding.v1`,
`prism_preview_identity()` (no network/model work),
`prepare_prism_preview_candidate(wire)` (CPU only, locked baseline FOV), and
`infer_bound_prism(request, wire, mask_png, binding, plan_sha256)`. The last method
must atomically verify full pins and consume the exact frozen wire/mask before
any forward; it must return an exact accepted-input receipt and typed result.
No current adapter has these methods. Adding an attribute or echoing a hash is
not runtime qualification: that adapter must be reviewed/tested at its actual
transport and preprocessing boundary before clinical-facing availability.

The service never imports OpenCV, Torch or model runtimes. The existing FOV
algorithm is not reimplemented or replaced. Synthetic adapters supply binary
masks for tests; v4/other mask versions, empty/nonbinary/wrong-size masks and
UNCERTAIN masks represented as READY are rejected. Successful post-run native ROI
must report the same applied mask identity; failed native ROI must discard the
candidate and report FALLBACK. Mismatched result or processing provenance is not
saved. Inference history stores the accepted binding separately from human labels.
Result saving pins the original store/provider and retains optimistic stale-result
handling; clinician edits can continue while the provider runs. Full admission
metadata stays server-side; only its hash and minimal policy fields enter the
provider receipt, avoiding unnecessary filenames/private paths.

## Required main-lane fields and gates

The route implements the following mapping from the main proposal. The real
provider adapter must still implement and qualify the execution side:

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

Display-only fixture plans cannot enable submission. A compatible backend receipt
can enable the protected route after verified assets and acknowledgement; the
server rechecks all identity fields regardless of client UI state. Current actual
providers remain unavailable, and there is no legacy-route fallback. Changed/
expired plans conflict; no silent regeneration is used after acknowledgement.

For an exact final-input preview, a later two-stage design must explicitly budget
native ROI inference: prepare/freeze wire and ROI/crop/tiles, return hashes and
transforms, then acknowledge and infer using that immutable result. This feature
is not implemented or qualified. The existing 47-request allocation is exhausted;
no hidden ROI forward, warmup or automatic retry is permitted in this task.

## Qualification and rollback

Synthetic tests cover missing/QC-only plans, Original fallback wording, conditional
FOV, distinct wire/preview hashes, malformed transforms, expiry, changed source/
mask/model, deferred cross-case responses, byte mismatch and decode failure.
They also assert that grading-only analysis never calls the legacy PRISM route.
In-memory HTTP tests exercise one-use submission with fake providers only. Offline
browser captures intercept every request and never click model submission. These checks are
engineering evidence, not clinician UAT or real model qualification.

Rollback requires reviewing this binding delta with the prior UI commit. Do not revert the
previous workflow/provenance or hygiene commits, alter server thresholds, or
silently restore unbound PRISM submission as a workaround. No DB migration or
data cleanup is associated with this change.
