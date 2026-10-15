# M1 — Experimental PRISM UWF Assistance in Split Runtime

**Status:** Owner-directed bounded implementation and qualification contract
**Decision date:** 2026-10-14
**Implementation branch:** `feat/m1-prism-uwf-integration`

## 1. Owner decision and boundary

The owner accepts a two-runtime architecture. This decision resolves the
previous `PRISM_SHARED_RUNTIME_INCOMPATIBLE` stop; it does not authorize
containers, a gateway, Tailscale, clinical validation, hospital-data use, or
production deployment.

- **USPEC runtime:** preserve the already-qualified Python 3.12.11, Torch
  2.11.0+cu128, TorchVision 0.26.x, timm 1.0.22 Tesla T4 environment
  unchanged; future local service port `7861`.
- **PRISM runtime:** create a dedicated isolated environment outside this Git
  repository at `/teamspace/studios/this_studio/dr-screening/runtime/prism-venv`;
  future local service port `7862`. Install only dependencies required by the
  locked inference imports plus the Model API application runtime. Record all
  installed versions. Never install PRISM requirements into or otherwise
  mutate the USPEC interpreter.
- Both may use the Tesla T4 only after PRISM independently qualifies. The
  intended deployment may later use two services under one stack; no
  container/gateway implementation is part of this work.

PRISM identity remains `prism-dr-5fold`, task `lesion-roi`, locked source
revision `79637440a535e4f8118e939d3787121f82180125`, with all 21 repository-
locked weight identities verified before loading. External source and weights
are read-only and are never copied into Git.

## 2. Capability and routing contract

The global grading routes are explicit and modality-bound:

| Confirmed modality | Task | Required model |
|---|---|---|
| CFP | `global` | `retfound-aptos5` |
| UWF | `global` | `uspec-uwf-grading` |

Neither model may be substituted across modalities. RETFound remains CFP-only;
USPEC remains UWF-only. PRISM is never a global grader.

PRISM preserves its legacy CFP behavior and may additionally advertise UWF
lesion assistance as **EXPERIMENTAL** only. Metadata must retain
`trained_domain=CFP`, `clinical_validation_status=NOT_VALIDATED_FOR_UWF` (or
`NOT_ESTABLISHED`), the fixed model ID/revision/task, and the existing academic
and research restrictions. No UWF-training, clinical-accuracy, commercial
rights, or production claim is made.

USPEC metadata reflects the accepted engineering runtime qualification and
may use `release_status=RESEARCH_ONLY` for public/synthetic research/demo
workflow. Rights remain `UNVERIFIED`; clinical validation remains
`NOT_ESTABLISHED`; production authorization remains disabled/not authorized.
Backend discovery, backend routing, and frontend capability gates must agree.

## 3. PRISM UWF preprocessing and failure state machine

Primary clinician-visible model states are only **AI READY** and
**AI UNAVAILABLE**. `PREPARED` and `FALLBACK` are internal processing modes
shown only in Processing details.

Every decodable image attempts PRISM inference after model load. FOV evidence
failure or native ROI failure alone must not turn AI unavailable. AI is
unavailable only for fatal decode, asset/load, CUDA/runtime, or unrecoverable
inference failure.

### PREPARED

When `uwf_white_rim_fov_v1` produces source-bound, trusted `READY` evidence:

```text
immutable Original RGB
→ black only high-confidence external-FOV/camera-rim pixels with its mask
→ preserve ambiguous peripheral anatomy
→ run native PRISM ROI cropper
→ lesion preprocessing and inference
```

A successful native ROI is used and the result records `processing_mode=PREPARED`.
The clinician overlay must use the exact same backend mask evidence used for
that inference input, bound to the original source hash and dimensions.

### FALLBACK

For uncertain/unavailable/invalid FOV evidence, do not apply its mask:

```text
immutable Original RGB
→ attempt native PRISM ROI
→ if ROI succeeds, infer on its crop
→ if ROI fails, explicitly bypass ROI and infer on full-frame Original RGB
```

Both paths record `processing_mode=FALLBACK`; neither may claim PREPARED. An
invalid/unavailable ROI alone is not fatal. FALLBACK displays Original with no
fabricated boundary and reports “Fallback processing used” in Processing
details.

Only high-confidence camera/device rim and outside-field material may be
removed. Preserve ambiguous anatomy; no ethnicity-based rule, aggressive
ellipse crop, or lesion suppression. Canny is supporting evidence only.

Raw PRISM detections are preserved. If and only if trusted FOV evidence exists,
attach one boundary class per raw result: `INSIDE_ANALYSIS_FIELD`,
`NEAR_CAMERA_RIM`, `OUTSIDE_ANALYSIS_FIELD`, or `INVALID_BOX`. Never suppress a
raw detection solely for its edge position. Without trusted FOV evidence do not
fabricate a boundary class.

## 4. Review UI and Bridge compatibility

Integrate `PrismAnalysisFieldOverlay` into the real Review workflow without
altering the P3-0 image-first viewer, original-pixel geometry, human authority,
or the manual AI-off path. The source image remains dominant; the prepared
analysis field uses a subtle transparent tint, dark translucent outside-field
veil and clean contour, with no hatch or anatomical-segmentation implication.

- PREPARED shows the exact analysis field used for model input.
- FALLBACK shows Original and no boundary.
- The primary status is AI READY after successful inference or AI UNAVAILABLE
  after fatal failure; internal processing mode is secondary detail only.
- UWF use remains visibly experimental and not validated for UWF.
- Keep existing Bridge v1 behavior compatible. If additional processing,
  boundary, or result evidence requires a new wire shape, version it
  additively and prove old clients fail safely; preserve every raw detection.

## 5. PRISM-only service profile

`MODEL_API_PROVIDER_SET=prism` is additive. It verifies only PRISM assets and
constructs only the PRISM provider, with no RETFound or USPEC asset requirement.
The dedicated PRISM interpreter serves `127.0.0.1:7862`, uses
`INFERENCE_DEVICE=cuda:0`, and receives explicit locked source/weight paths.
Existing `legacy`, `uspec`, and `combined` provider sets keep their contracts.

Before any checkpoint deserialization, recheck byte identity and inspect the
exact selected Torch/Ultralytics loader path and its security behavior. Do not
bypass restricted loading or install into the qualified USPEC environment.

## 6. Qualification and acceptance evidence

Use synthetic/public inputs only. Independently record source cleanliness and
exact SHA, 21/21 weight hashes, runtime package versions, safe loader path,
Tesla T4/CUDA, load time, VRAM, first and warm latency, processing mode, ROI
outcome, raw lesion-output structure/classes/counts, trusted-FOV boundary
metadata, and health before/after inference. Exercise:

1. legacy CFP smoke where practical;
2. UWF PREPARED with trusted FOV and successful native ROI;
3. UWF FALLBACK with external FOV uncertain/unavailable;
4. controlled native ROI failure followed by full-frame inference.

After independent PRISM qualification, run the two services sequentially:

```text
USPEC synthetic UWF on 127.0.0.1:7861
→ PRISM synthetic UWF on 127.0.0.1:7862
→ USPEC synthetic UWF again
```

Record both service health, routing/provider identity, USPEC output stability,
PRISM success, CUDA error/OOM status, and combined GPU residency. If sustained
two-model residency is not bounded safely, test serialized operation without
changing either model runtime.

Required validation includes FOV, PRISM, global routing/capability, USPEC,
Bridge/remote, Review/overlay tests, backend Ruff/tests, frontend tests,
typecheck/build, and `git diff --check`. A passing engineering qualification
is not sensitivity/specificity, clinical validation, rights clearance, or
production authorization.

## 7. Exit criteria

The terminal marker `PRISM_UWF_SPLIT_RUNTIME_QUALIFIED` and deployment
recommendation `SPLIT_RUNTIME_CONFIRMED` may be reported only if the isolated
PRISM runtime and all four PRISM inference paths qualify, the sequential
USPEC→PRISM→USPEC two-service smoke passes, the application/tests pass, and Git
integration/cleanup completes under `AGENTS.md`. Otherwise report the exact
failed gate and do not claim completion.
