# DR Screening M1 — Phase 3 Execution r3.0
## AI Models, Model API, Qualification, MONAI Evaluation, and Research Comparators

**Document revision:** Execution r3.0  
**Prepared:** 2026-10-04  
**Document status:** `OWNER_DIRECTED_EXECUTION_SPEC`  
**Implementation status:** `READY_FOR_OWNER_REVIEW` (execution receipt recorded; owner acceptance pending)  
**Repository:** `siriponsri/dr-support-screening-poc`  
**Authoritative repository baseline:** `50cf7124ec95c56b9821d34e57141a1d8d3919a4`  
**Phase 1:** `DONE`  
**Phase 2:** `DONE`  
**P3-0 Clinical UX & Design System Freeze:** `DONE / UX FREEZE ACCEPTED`  
**Phase 3:** `NOT_STARTED`  
**Phase 4:** `NOT_STARTED`  
**Phase 5:** `NOT_STARTED`

**Supersedes for execution:** `docs/milestone/m1/M1_PHASE3_MODELS_MODEL_API.md` Candidate r2.2 as the active Phase 3 execution plan.  
**Historical r2.2 remains evidence:** do not delete or rewrite its historical claims/evidence.  
**Execution name:** `M1 Phase 3 — Qualified AI Assistance and Model API`

> Phase 3 introduces and qualifies AI assistance behind the already-frozen clinician workstation. The model must adapt to the Phase 2/P3-0 clinical, persistence, provenance, and UX contracts. The clinician workflow must not become more complicated merely because more model outputs become available.

---

# 1. Authority and required reading

Before the first implementation write, MAIN/IMPLEMENT/REVIEW must read completely:

1. `AGENTS.md`
2. `DESIGN.md`
3. `README.md`
4. `THIRD_PARTY_NOTICES.md`
5. `docs/milestone/m1/M1_MASTER_PLAN.md`
6. `docs/milestone/m1/M1_PHASE2_UWF_LABELING.md`
7. `docs/milestone/m1/M1_PHASE2_FINAL_CLOSEOUT_PATCH.md`
8. `docs/milestone/m1/PRE_PHASE3_CLINICAL_UX_DESIGN_FREEZE.md`
9. `docs/milestone/m1/PRE_PHASE3_CLINICAL_UX_FREEZE_EVIDENCE.md`
10. historical `docs/milestone/m1/M1_PHASE3_MODELS_MODEL_API.md` r2.2
11. `docs/milestone/m1/M1_PHASE4_DATASET_REVIEW_EXPORT.md`
12. `docs/milestone/m1/M1_PHASE5_E2E_VALIDATION.md`
13. ADR-0002 through ADR-0006
14. `docs/operations/MODEL_SERVER.md`
15. `docs/operations/CONFIGURATION.md`
16. current Model API, provider, derivative, persistence, review, Models & Audit, and model-connection source/tests affected by the chosen implementation.

Instruction priority remains:

```text
explicit owner instruction
→ AGENTS.md / frozen repository requirements
→ this Execution r3.0
→ applicable repository skills / implementation choices
```

If code reality conflicts with this spec in a way that changes clinical semantics, privacy/security, authoritative persistence/provenance, source-image integrity, original-pixel geometry, or frozen P3-0 UX behavior:

```text
STOP
→ report exact conflict
→ identify smallest compatible amendment
→ wait for owner decision
```

Routine implementation details inside these boundaries belong to MAIN/IMPLEMENT and do not require owner approval.

---

# 2. Why r3.0 is required

The historical Phase 3 r2.2 was prepared against the 2026-09-28 planning baseline and correctly established several important boundaries:

- NB01/USPEC is the preferred UWF grading direction.
- RETFound is a CFP comparator/fallback, not the preferred UWF grader.
- PRISM is CFP-domain and not validated for UWF.
- model artifact integrity, runtime compatibility, API integration, hardware qualification, domain validation, and rights are separate readiness dimensions.
- manual review must continue when AI is unavailable.
- explanation evidence is AI provenance, not a physician label.
- hospital-origin authorization is separate from modality/model choice.
- online/in-place learning from new hospital labels is prohibited.

Those principles remain.

However, the repository has materially advanced since r2.2:

```text
Phase 1 PostgreSQL authority           DONE
Phase 2 UWF labeling workflow          DONE
P3-0 UX/design freeze                  DONE
Model connection Settings              implemented
P3-0 clinician UX contracts            frozen
Source origin WORKSPACE evidence       present locally
Manual AI-off path                     accepted
```

At the same time, current code still reflects the pre-Phase-3 model stack:

```text
RETFound + PRISM only
CFP-only real-model inference gate
Bridge v1 strict schemas
legacy two-model connection probe
legacy Model Server setup/assets
hard-coded RETFound/PRISM Model Audit UI
no qualified native UWF model provider
no qualified explanation payload
```

Execution r3.0 reconciles the current repository with the historical research evidence before implementation begins.

---

# 3. Fresh repository audit — current facts at baseline 50cf7124

This section is a source-code audit, not an implementation result.

## R3-A01 — The clinician workstation / Model API split is already protected

ADR-0002 and current `dr_support/app.py` enforce:

```text
APP_PROFILE=review
MODEL_RUNTIME=remote
```

for clinician workstations, and:

```text
APP_PROFILE=model_api
MODEL_RUNTIME=local
```

for the GPU Model API.

The review workstation must not begin loading Phase 3 weights locally.

**Decision:** preserve this architecture.

## R3-A02 — The current real provider registry contains only RETFound and PRISM

Current local Model API provider construction returns:

```text
retfound-aptos5
prism-dr-5fold
```

The remote workstation adapter mirrors those two providers.

Current `/v1/models`, Model Connection probing, Review, and Models & Audit behavior are therefore built around those two legacy IDs.

**Gap:** USPEC cannot become the preferred UWF grader merely by placing a checkpoint on disk.

## R3-A03 — Real-model UWF inference is currently intentionally blocked

Current review inference applies:

```text
is_inference_eligible(..., require_cfp_source=True)
```

and current Model API handlers explicitly return `UNSUPPORTED` for non-CFP requests to RETFound and PRISM.

Current admission UI correctly states for UWF:

```text
No qualified UWF AI model is enabled.
Clinical review can continue manually.
```

**Decision:** do not weaken this gate until a UWF capability passes its own Phase 3 qualification.

## R3-A04 — Bridge v1 is too strict for silent Phase 3 field additions

Current Pydantic contracts use:

```text
extra = forbid
```

and `schema_version = bridge.v1`.

`GlobalResult` currently contains:

```text
model ID/version
modality
state
grade
probabilities
confidence
warnings
Provenance
```

`LesionResult` currently contains:

```text
model ID/version
modality
state
original-image width/height
lesions
warnings
Provenance
```

There is no typed versioned explanation payload, invocation identity, analysis-transform binding, domain-validation status, or release-mode field.

**Decision:** Phase 3 must not silently mutate `bridge.v1`.

A versioned compatibility extension is required.

## R3-A05 — Source origin is locally truthful but the Model API wire contract is not

Current admitted workspace images keep:

```text
source_origin = WORKSPACE
```

but `BridgeImage.source_type` remains compatibility `PUBLIC`, while remote Model API request/provenance schemas allow only:

```text
PUBLIC
SYNTHETIC
```

The review inference gate currently prevents `WORKSPACE` origin from being transmitted, which is the correct safety behavior.

**Decision:** preserve the block. Do not “solve” it by relabeling workspace/hospital data as PUBLIC.

Hospital inference remains separately gated by data-steward/owner authorization and a truthful versioned origin/permission contract.

## R3-A06 — The current Model Gateway probe hard-codes the legacy pair

`services/model_gateway.py` currently expects:

```text
retfound-aptos5 → global
prism-dr-5fold  → lesion-roi
```

and rejects a remote descriptor set that does not contain both.

**Gap:** a future USPEC-only or capability-oriented Model API would fail connection verification even if healthy.

**Decision:** Phase 3 must make Model Gateway discovery capability-based while preserving legacy compatibility.

## R3-A07 — Current Models & Audit UI is hard-coded to RETFound and PRISM

The frontend currently filters/display-labels these two specific IDs and presents:

```text
RETFound — Score-level decision context
PRISM-DR — Localized visual evidence
```

Current Review status also filters these two models.

**Decision:** Phase 3 must remove model-ID-specific primary-flow assumptions.

The clinician-facing workflow should consume **capabilities**, while Models & Audit may show exact provider/model identity.

## R3-A08 — Existing UI says “probability” / “confidence” for legacy softmax values

The current bridge contract normalizes the 5-class vector and stores `confidence=max(vector)`. Models & Audit renders a “Probability distribution” and “Confidence / model score”.

Historical r2.2 correctly states that research grading scores are experimental and must not be presented as calibrated clinical probabilities.

**Decision:** Phase 3 UI must use wording such as:

```text
model score distribution
model top score
```

unless a separately validated calibration protocol exists.

Do not call raw softmax/model scores clinical risk probabilities.

## R3-A09 — Current AI result persistence is “latest result” oriented

Current inference stores the newest `global` or `lesion` payload on the case and adds an `INFERENCE` event.

For a new global result, current code can reset current grade-review fields to pending.

That behavior is unsafe for Phase 3 retries, late responses, model comparisons, or repeated inference after physician review.

**Decision:** Phase 3 needs invocation/revision binding and append-only AI run lineage.

A new/late model result must never silently erase or reset an already confirmed physician decision.

## R3-A10 — Current model asset verification is legacy-provider specific

`model_assets.py`, `.env.example`, Model Server setup, and documentation verify only RETFound/PRISM assets.

Current server startup with:

```text
MODEL_REQUIRE_VERIFIED_ASSETS=1
```

calls legacy `verify_assets('all')`.

**Gap:** no deterministic installed-bundle registry for USPEC or future providers.

## R3-A11 — Current `.[models]` environment is not acceptable as an automatic Phase 3 runtime

Current `pyproject.toml` pins the optional model stack to:

```text
torch 2.5.1
torchvision 0.20.1
timm 0.9.2
ultralytics 8.4.8
sahi 0.12.6
...
```

Current PyTorch security advisory GHSA-63cw-57p8-fm3p reports affected PyTorch versions through 2.9.1 and patched versions beginning at 2.10.0 for that issue.

Historical r2.2 already required a pre-deserialization security gate.

**Decision:** no Phase 3 checkpoint may be loaded merely because the optional
model dependencies install successfully.

Phase 3 must qualify a dedicated Model API runtime and exact transitive loader paths before first load.

## R3-A12 — Current repo PRISM and r2.2 research PRISM are not automatically the same adapter

The current repository `dr_support/providers/prism.py`:

- uses the ROI cropper;
- loads 4 lesion classes × 5 folds;
- applies current repo preprocessing/fusion;
- is CFP-only.

Historical r2.2 describes a separate research-export `offline_detector.py` where 20 specialist weights are used and the ROI cropper asset was reported present but unused in that call path.

**Decision:** treat them as two distinct implementations until proven equivalent.

Do not silently mix:

```text
legacy repo PRISM provider
+
research package adapter
+
research ROI cropper
```

into an undocumented hybrid.

## R3-A13 — No qualified native UWF lesion localizer is present in the current repo

PRISM is not UWF-qualified.

MONAI Model Zoo does not provide a project-qualified UWF DR localization model for this repository.

**Decision:** Phase 3 may complete the native-UWF localization track as:

```text
DEFERRED_NO_QUALIFIED_CANDIDATE
```

if no approved candidate exists.

Do not build a new detector from scratch merely to make the phase green.

## R3-A14 — P3-0 is now a frozen integration boundary

Phase 3 must preserve:

```text
one-primary-action
image-first hierarchy
compact/progressive annotation controls
hidden backend-state terminology
optional Advanced workflow
compact reviewer treatment
brand/status/lesion color separation
responsive/accessibility baseline
manual AI-off operation
```

AI evidence must fit into this design.

The UI must not expand into a model-debug console in the clinician path.

---

# 4. Phase 3 objective

Phase 3 must deliver a **capability-oriented, versioned, provenance-safe Model API** and qualify the best available AI assistance without blocking the physician labeling workflow or overstating model validity.

The preferred M1 grading direction remains:

```text
NB01 / USPEC UWF grading
```

The lesion direction remains:

```text
native UWF localization if a qualified candidate exists
otherwise explicit deferred native track
+
optional PRISM CFP-domain comparator/fallback under strict warning
```

Research/engineering comparators:

```text
MONAI engineering foundation evaluation
Clef/Clef-Flash structured multimodal decision-model comparator
```

These comparators are non-blocking.

---

# 5. Phase 3 completion philosophy

Phase 3 does **not** have one boolean “AI ready” state.

Every capability must report separate dimensions.

## 5.1 Required readiness dimensions

For each provider/capability record:

```text
artifact_status
trust_status
security_status
runtime_status
api_status
hardware_status
domain_status
clinical_validation_status
rights_status
release_status
```

Suggested values may include:

```text
NOT_PRESENT
VERIFIED_BYTES
HASH_MISMATCH

TRUSTED_SOURCE_RECORDED
TRUST_UNVERIFIED

SECURITY_REVIEWED
SECURITY_BLOCKED

NOT_LOADED
LOADED
RUNTIME_FAILED

CONTRACT_VERIFIED
CONTRACT_BLOCKED

NOT_MEASURED
QUALIFIED_PROFILE

UWF_RESEARCH_CANDIDATE
CFP_DOMAIN
NOT_VALIDATED_FOR_UWF
GENERAL_MULTIMODAL

NOT_ESTABLISHED
RESEARCH_EVALUATED

UNVERIFIED
RESEARCH_ALLOWED
APPROVED_SCOPE

DISABLED
RESEARCH_ONLY
COMPARATOR_ONLY
ASSISTIVE_ENABLED
PRIMARY_ENABLED
BLOCKED
DEFERRED
```

MAIN may refine exact enum names if they remain explicit and testable.

## 5.2 No readiness promotion by implication

Examples:

```text
correct SHA
≠ trusted source
≠ safe loader
≠ successful runtime
≠ UWF validation
≠ clinical validation
≠ production rights
```

and:

```text
good public-dataset metrics
≠ hospital performance
```

---

# 6. Capability model

Phase 3 should route clinician behavior by **capability**, not hard-coded provider ID.

Minimum capability IDs:

```text
dr_grade
core_lesion_localization
longitudinal_change
decision_comparator
```

`decision_comparator` is research-only and must not appear as a normal clinician action.

A model descriptor should be able to express at least:

```text
capability_id
task
model_id
model_version
runtime
supported_modalities
trained_domain
input_representation
taxonomy_or_class_order
preprocessing_version
postprocessing_version
artifact_digest
runtime_status
domain_status
clinical_validation_status
rights_status
release_status
explanation_types
warnings
```

The clinician flow normally consumes:

```text
best enabled capability
```

Models & Audit consumes the full descriptor.

---

# 7. Bridge evolution — preserve v1, add a versioned Phase 3 contract

## 7.1 Bridge v1 remains frozen legacy compatibility

Do not change the meaning of current `bridge.v1` fields.

Legacy CFP RETFound/PRISM tests and historical records must remain readable.

## 7.2 Phase 3 is authorized to introduce a versioned extension

Because `bridge.v1` uses strict `extra=forbid`, Phase 3 may introduce a new versioned contract rather than silently extending v1.

Preferred conceptual result envelope:

```text
schema_version
invocation_id
capability_id
task

model:
  id
  version
  artifact_digest
  trained_domain
  supported_modalities
  release_status

input:
  image_id
  source_sha256
  source_origin
  input_modality
  analysis_sha256
  representation_version
  transform_id
  mask_version
  request_case_revision

result:
  typed task result

explanation:
  optional typed evidence

runtime:
  device/runtime identity
  latency_ms

warnings:
  [...]

provenance:
  source / adapter / checkpoint / preprocessing identity
```

Exact code structure is an implementation decision.

## 7.3 Compatibility requirement

Choose one reviewed strategy:

```text
A. new versioned /v2 prediction endpoints
B. content/schema negotiation on existing endpoints
C. separate versioned explanation/context sidecar while keeping v1 prediction
```

Any choice must prove:

- legacy v1 remains compatible;
- new UWF provider receives required context;
- old clients fail safely rather than misparse;
- no silent schema drift.

---

# 8. Source-origin and authorization boundary

## 8.1 Descriptive origin

Phase 3 may carry truthful source origin such as:

```text
PUBLIC
SYNTHETIC
WORKSPACE
UNKNOWN
```

as descriptive provenance.

## 8.2 Permission is a different concept

Do not infer:

```text
WORKSPACE == authorized hospital inference
```

or:

```text
pseudonymous == public
```

## 8.3 Current allowed Phase 3 engineering lane

Until a separate data-steward/owner decision exists:

```text
PUBLIC       → allowed if other inference gates pass
SYNTHETIC    → allowed if other inference gates pass
WORKSPACE    → manual review only / remote model transmission blocked
UNKNOWN      → blocked
```

This allows Phase 3 engineering to proceed without authorizing hospital data.

## 8.4 Future hospital authorization

If later approved, use a separately reviewed authorization/permission representation.

Do not invent a permanent “HOSPITAL_APPROVED” enum in this run without an owner/data-steward decision.

---

# 9. Inference invocation and stale-response safety

Every real Phase 3 inference must be bound to the context that generated it.

Minimum context:

```text
invocation_id
case/image ID
source SHA-256
analysis SHA-256
analysis representation version
transform ID
model ID/version/artifact digest
task/capability
case revision at request time
timestamp
```

## 9.1 Persistence rule

AI result persistence must be additive/auditable.

Recommended case-level structure:

```text
inference_history[]
selected_ai_evidence
```

or an equivalent normalized persistence design.

Do not rely only on overwriting:

```text
case.global
case.lesion
```

without preserving previous model evidence.

## 9.2 Human-decision protection

A late/retried/new model result must not automatically:

- clear a confirmed human grade;
- erase human annotations;
- reset annotation completeness;
- invalidate human confirmation solely because AI changed;
- overwrite older raw AI history.

If the AI result arrives for a stale case/source/analysis revision:

```text
store as stale/audit evidence if appropriate
or reject it
```

but never apply it as current suggestion silently.

## 9.3 Idempotency

Retries for the same `invocation_id` must not create duplicate authoritative AI runs.

---

# 10. Shared UWF representation contract

Phase 2 selected the shared analysis representation.

Phase 3 consumes:

```text
immutable Original
→ selected Phase 2 analysis derivative / mask
→ provider-specific transform
→ model input
→ model result
→ original-pixel mapping where spatial
```

## 10.1 No silent double masking

Historical r2.2 reports an NB04 extra preprocessing/masking path.

Phase 3 must compare:

```text
Phase 2 selected representation only
vs
Phase 2 representation + candidate extra pre-mask
```

under the same fixture identity if the candidate adapter currently applies another mask.

Do not retain an extra mask merely because research code contains it.

Do not remove it merely because it looks redundant.

Choose using versioned measured evidence.

## 10.2 Any processing change is model behavior

Changing:

```text
mask
letterbox
crop
normalization
CLAHE
tile size
stride
NMS/fusion
```

creates a new behavior contract even when weights are unchanged.

Record a new preprocessing/adapter version.

---

# 11. P3-G — Preferred UWF grading: NB01 / USPEC

## 11.1 Evidence inherited from r2.2

Historical r2.2 records the research candidate:

```text
USPEC encoder
RGB 7 × 7 patch/MIL grading head
grade 0–4
grading_state.pt as trained inference candidate
USPEC_weights.pth as base/pretrained encoder
latest.pt as resume checkpoint when present
```

Expected inference-candidate metadata from the research package:

```text
grading_state.pt
expected size: 1,213,535,294 bytes
expected SHA-256:
8f07eb11859f638faee368a56c7c532ca946fee320f92f030a0cf25c63b769ac
```

Historical aggregate research metrics are background research evidence only:

```text
2,597-image internal research test
QWK ≈ 0.901644
macro F1 ≈ 0.723983
```

Do not present those metrics as hospital, clinical, or current runtime validation.

## 11.2 Artifact gate

Before load:

- independently observe the actual file;
- record size;
- calculate SHA-256;
- verify expected digest;
- record source/custodian/acquisition path;
- record rights/trust evidence separately;
- never commit the checkpoint;
- never rewrite expected hash to match observed bytes.

If hash mismatches:

```text
HASH_MISMATCH
→ stop use
→ preserve evidence
→ investigate source
```

## 11.3 Adapter contract

Historical research documentation reports a grading path using an RGB letterbox / patch-MIL pipeline.

Implementation must verify the exact adapter code before freezing values.

Do not rely only on this plan for crop/stride details.

After source verification, record exact:

```text
input representation
resize/letterbox
patch size
grid
stride
normalization
class order
aggregation
attention generation
output score transformation
```

## 11.4 Output contract

Clinician-facing suggestion:

```text
grade 0–4
```

separate from:

```text
Ungradable
Needs Second Review
```

which remain human workflow states unless a separately qualified model explicitly provides a different typed capability.

Raw class outputs should be stored as:

```text
model scores
```

unless calibration is separately established.

## 11.5 Explainability

If NB01 attention is enabled:

```text
attention grid / patch weights
```

is model explanation evidence only.

Required warning:

```text
MODEL_ATTENTION_NOT_LESION_LOCALIZATION
```

or equivalent clinician-safe wording.

The attention evidence must bind to:

```text
same source SHA
same analysis SHA
same transform
same model artifact
same invocation
```

No explanation payload → explicit unavailable state.

Never synthesize one.

## 11.6 UI behavior

In normal Review:

- show a compact AI grading suggestion only if the capability is enabled;
- clinician grade remains the authoritative action;
- explanation remains secondary/progressive;
- Models & Audit shows full technical identity;
- no new step is required to continue manually.

---

# 12. P3-L — Lesion localization track

Phase 3 separates three concepts.

## 12.1 Native UWF localization

Preferred target:

```text
qualified UWF Core-finding localization
```

Current baseline has no qualified candidate.

Allowed final state:

```text
DEFERRED_NO_QUALIFIED_CANDIDATE
```

This is not a Phase 3 engineering failure if documented honestly.

Do not train a new detector from scratch solely to satisfy Phase 3.

## 12.2 PRISM legacy-repo provider

Current repo provider:

```text
model_id = prism-dr-5fold
domain = CFP
4 Core lesion classes
5 folds/class
ROI cropper active
current repo preprocessing/fusion
```

It remains useful for:

```text
CFP
research comparison
contract testing
```

It is not UWF-native.

## 12.3 PRISM research-package adapter

Historical r2.2 describes a different candidate adapter/manifest.

Before using it:

- verify exact code;
- verify exact 21 assets and 20-specialist behavior;
- verify whether ROI cropper is actually called;
- freeze that adapter identity separately;
- compare with the repo legacy provider.

## 12.4 No silent hybrid

Prohibited:

```text
repo ROI cropper
+
research adapter specialist path
+
different fusion
```

without a new explicit adapter version and measured evidence.

## 12.5 UWF fallback/comparator

PRISM on UWF remains:

```text
model_domain = CFP
input_modality = UWF
validation_status = NOT_VALIDATED_FOR_UWF
usage_mode = RESEARCH_COMPARATOR
```

until the owner explicitly approves an assistive fallback mode.

Default after engineering integration:

```text
clinical release = DISABLED for UWF
```

unless separately approved.

## 12.6 Empty detections

Always:

```text
empty model proposals
≠ no lesions
≠ reviewed none found
≠ human negative
```

---

# 13. P3-M — MONAI engineering evaluation

MONAI is an engineering-framework candidate, not a DR model.

As of this planning revision, current MONAI documentation describes:

- a PyTorch-based medical-imaging framework;
- MONAI 1.6.1 release line;
- MONAI Bundle as a specification/file-structure for distributing model metadata, code/config, and reproducible workflows;
- Model Zoo integration through Bundle format.

The project does not currently have a MONAI UWF DR model to adopt.

## 13.1 Evaluate these adoption levels separately

```text
M0 — no adoption; keep current custom adapter stack

M1 — use selected MONAI transforms/metrics only

M2 — package new UWF grading capability as a MONAI Bundle
     while keeping existing Model API service

M3 — broader MONAI inference workflow integration

M4 — MONAI Label/UI replacement
     OUT OF SCOPE / REJECTED for M1
```

## 13.2 Preferred evaluation focus

Prioritize:

```text
MONAI Bundle metadata/config
reproducible preprocessing
model identity
inference command/config
evaluation utilities
future training/fine-tuning reproducibility
```

Do not replace the accepted Workbench UI.

## 13.3 Adoption gate

Adopt a MONAI component only if it:

- preserves exact model outputs within reviewed tolerance;
- does not force a less-safe runtime;
- reduces custom model glue or improves reproducibility;
- preserves original-image coordinate/provenance contracts;
- fits the Model API boundary;
- does not add significant deployment complexity without benefit.

Otherwise record:

```text
MONAI_EVALUATED_DEFERRED
```

Phase 3 does not fail if MONAI is deferred.

## 13.4 Bundle vs deployment

A MONAI Bundle is not by itself the hospital deployment architecture.

The existing Model API/service boundary remains authoritative unless a separate architecture decision changes it.

---

# 14. P3-C — Clef / Clef-Flash research comparator

Clef is **not** a replacement for USPEC or PRISM by default.

Current public Cloudflare material describes:

```text
Clef       multimodal decision model, 27B backbone class
Clef-Flash smaller multimodal decision model, 9B backbone class
typed schema-bound decisions
joint schema head
one logit per allowed option
image/text/JSON/video inputs
```

There is no project-qualified evidence that Clef is validated for UWF diabetic-retinopathy grading or retinal lesion localization.

## 14.1 Allowed research question

Can a general multimodal decision model produce useful **structured image-level decisions** on retinal images?

Candidate typed schema:

```text
gradable:
  yes / no

dr_grade:
  0 / 1 / 2 / 3 / 4

needs_second_review:
  yes / no

core_finding_presence:
  MA yes/no
  HE yes/no
  EX yes/no
  SE yes/no
```

## 14.2 Not allowed

Do not use Clef as:

- PRISM bounding-box replacement;
- lesion localizer without a localization head/protocol;
- clinical DR grader merely because it accepts images;
- source of new clinical rules;
- source of autonomous referral.

## 14.3 Comparator protocol

If resources permit:

1. run zero-shot structured decisions first;
2. use only public/synthetic or separately authorized research data;
3. evaluate against the same held-out labels used for the chosen comparator protocol;
4. report QWK/macro-F1/per-grade recall/confusion where labels support them;
5. evaluate gradability/second-review usefulness separately;
6. record latency/VRAM/runtime;
7. do not show output in clinician UI.

Fine-tuning is a separate owner-approved research action.

## 14.4 Resource gate

Do not assume the current target GPU can host Clef or Clef-Flash.

Measure first.

If impractical:

```text
CLEF_COMPARATOR = DEFERRED_RESOURCE_LIMIT
```

This is non-blocking.

---

# 15. Runtime and dependency qualification

## 15.1 Separate model-server runtime from workstation runtime

The review workstation should remain lightweight.

Phase 3 should establish a dedicated reproducible Model API dependency lock/profile rather than making clinician setup depend on a large GPU stack.

Possible implementations:

```text
dedicated lock/constraints file
dedicated model-server environment specification
container image
another repository-supported reproducible environment
```

MAIN chooses the smallest maintainable solution.

## 15.2 Security gate before deserialization

For every selected artifact record separately:

1. expected bytes/hash;
2. observed bytes/hash;
3. artifact source/trust/permission;
4. exact runtime/build;
5. actual loader path;
6. current applicable security advisories;
7. security decision;
8. compatibility/function result.

Do not treat `weights_only=True` as a complete security clearance.

## 15.3 Current PyTorch issue

The current repository optional model pin (`torch==2.5.1`) falls inside the affected range published for GHSA-63cw-57p8-fm3p.

Therefore:

```text
do not load Phase 3 checkpoints under the legacy default model environment
until exact runtime/loader remediation has been qualified
```

Do not choose the final PyTorch version from the advisory alone.

Choose a runtime only after compatibility testing with the selected USPEC/PRISM path.

## 15.4 Shared-environment decision

Historical research environments differ.

Phase 3 must determine whether:

```text
USPEC
PRISM
MONAI candidate
```

can safely share one process/environment.

If dependency or VRAM conflicts exist, acceptable architecture includes:

```text
one Model API facade
→ separate capability worker processes/environments
```

but do not build a multi-service platform unless evidence requires it.

---

# 16. Model API runtime policy

Preserve:

```text
one worker by default
explicit CUDA requirement for production-like model host
no silent CPU fallback
offline normal inference
bearer secret server-side only
```

## 16.1 Load strategy

Measure:

```text
cold load
warm inference
peak VRAM
steady VRAM
sequential capability load
combined capability memory
unload/reload recovery
```

Do not assume that lazy loading all models forever is safe.

Select one reviewed policy:

```text
keep primary grader resident
load lesion capability on demand
explicit unload when required
separate worker process
```

based on measured target-host behavior.

## 16.2 No mtime selection

Provider/bundle identity must be selected by:

```text
explicit registry/config
model ID
version
artifact digest
```

never:

```text
newest directory
latest mtime
first matching file
```

---

# 17. Installed model/capability registry

Introduce one deterministic source of runtime model truth.

The exact format may be Python config, JSON, TOML, or another reviewed repository-supported contract.

It must not contain model weights or secrets.

Minimum entry:

```text
capability_id
provider_id
model_id
version
artifact role
expected digest
adapter version
supported modality
trained domain
preprocessing version
explanation support
release mode
required runtime profile
```

Runtime-reported observed status is separate from committed expected metadata.

The registry must support:

```text
USPEC preferred UWF grader
RETFound CFP comparator
PRISM CFP localizer/comparator
optional research comparator entries
```

without requiring every entry to be enabled.

---

# 18. Model Gateway and connection settings

Phase 3 must close the previously deferred Model API live-success gate when a real approved Model API target exists.

## 18.1 Connection discovery

Replace the hard requirement that both RETFound and PRISM appear.

Connection is healthy when:

- `/health` is valid;
- `/v1/models` / capability discovery is valid;
- at least the required configured capability set is present;
- descriptor schema is valid.

Legacy pair remains accepted.

## 18.2 Settings UX

Keep existing server-side secret handling.

Do not:

- return token;
- store token in browser localStorage;
- expose token in logs.

The Settings page should show capability availability in plain language.

Do not expose every readiness enum in the primary Settings flow.

Detailed states belong in Models & Audit.

## 18.3 Gate C

Final Phase 3 evidence must state one:

```text
LIVE_MODEL_API_SUCCESS = PASS
```

or:

```text
LIVE_MODEL_API_SUCCESS = NOT_RUN / BLOCKED
reason = ...
```

Do not turn absence of an approved server into PASS.

---

# 19. Models & Audit target

P3-0 design remains frozen.

Models & Audit may become more technical than Review, but should remain structured.

Display per capability/provider:

```text
capability
model ID/version
runtime status
modality/domain
release status
artifact digest
preprocessing
last inference identity/time/latency
warnings
explanation availability
```

Use expandable technical detail.

## 19.1 Primary Review remains compact

Primary Review should show:

```text
AI grade suggestion — when enabled
localized suggestions — when enabled
short limitation status
optional Explainability
```

It must not show a grid of all research comparators.

## 19.2 Comparators stay out of normal clinical flow

RETFound comparator, PRISM research comparator, MONAI evaluation, and Clef research output belong in:

```text
Models & Audit
research evidence
developer/operator receipts
```

unless separately promoted.

---

# 20. Explanation evidence

Explanation evidence must be typed and model-specific.

## 20.1 USPEC

Possible:

```text
7 × 7 attention / patch weights
```

Required:

```text
source binding
analysis binding
model binding
adapter version
warning
```

## 20.2 Lesion provider

Localized boxes are model output, not the same concept as grade attention.

If the candidate adapter produces:

```text
boxes
review_boxes
```

keep those types distinct.

`review_boxes` are not accepted findings.

## 20.3 Absence

No explanation support:

```text
UNAVAILABLE
```

not fabricated fallback visualization.

---

# 21. Longitudinal boundary

No qualified learned longitudinal model currently exists.

Phase 3 default:

```text
learned longitudinal capability = DISABLED
```

Manual same-eye comparison may remain available under existing identity/chronology rules.

Do not infer chronology from:

```text
L1/L2
visit ordinal
filename sequence
```

without acquisition-order evidence.

No autonomous progression/risk/referral claim.

---

# 22. Rights and licensing

Keep separate rights status for every capability.

Current known repository notices include:

```text
RETFound repository: CC BY-NC 4.0
PRISM source: MIT
PRISM released weights: academic-use language upstream
Ultralytics component ecosystem: AGPL-3.0
```

These do not create commercial/clinical clearance.

For USPEC:

```text
production rights = UNVERIFIED
```

until evidence is supplied.

MONAI is an engineering dependency decision and does not transfer rights to the wrapped model.

Clef open-source licensing does not establish retinal clinical validity.

---

# 23. Workstreams and execution order

Phase 3 execution is divided into four substantive chunks.

Do not micro-review every file.

## CHUNK A — Contract, capability, and safety foundation

**IDs:** `P3-A1` through `P3-A8`

No Phase 3 checkpoint load is required for this chunk.

### P3-A1 — Baseline and artifact ledger

Create a versioned Phase 3 evidence/registry structure.

Record:

- expected USPEC artifact identity;
- RETFound/PRISM legacy identities;
- research PRISM candidate identity if material is accessible;
- role of each file;
- expected digest;
- rights/trust state;
- enabled/disabled status.

No weights in Git.

### P3-A2 — Capability registry

Replace model-ID-only assumptions with capability descriptors.

Preserve legacy IDs.

### P3-A3 — Versioned Bridge extension

Implement reviewed compatibility strategy for:

```text
invocation/context
analysis binding
source origin
capability identity
domain/release metadata
optional explanation
```

Preserve bridge.v1.

### P3-A4 — Dynamic Model Gateway

Connection probe must work with capability discovery and not require exactly the legacy pair.

### P3-A5 — AI invocation history / stale guard

Add auditable invocation identity and protect confirmed human decisions.

Test late/retry/duplicate/stale responses.

### P3-A6 — Source-origin safety

Preserve:

```text
WORKSPACE/UNKNOWN → blocked from model transmission
```

until separate authorization.

Public/synthetic fixtures remain usable.

### P3-A7 — Dynamic Models & Audit / Review integration

Remove hard-coded dependency on RETFound/PRISM for primary capability selection while preserving legacy history.

No UI redesign outside P3-0 contract.

### P3-A8 — Dedicated runtime specification

Create the reproducible Model API dependency/runtime lane and pre-load security checklist.

No unsafe checkpoint load.

### Chunk A acceptance

- bridge v1 regression tests pass;
- new contract tests pass;
- stale responses cannot reset human review;
- Models & Audit renders capability descriptors;
- manual AI-off flow unchanged;
- WORKSPACE source remains blocked;
- no weight loaded under unqualified runtime.

### Chunk A review

One independent exact-candidate substantive review.

---

## CHUNK B — Preferred UWF grading / USPEC qualification

**IDs:** `P3-B1` through `P3-B8`

### P3-B1 — Artifact receipt

Observe and verify `grading_state.pt`.

Record exact receipt.

If unavailable/mismatch:

```text
USPEC runtime = BLOCKED_ARTIFACT
```

continue other Phase 3 work.

### P3-B2 — Trust/security receipt

No deserialization before security gate.

### P3-B3 — USPEC adapter

Implement exact verified preprocessing/model/output path.

Do not import training-only optimizer logic into inference.

### P3-B4 — Shared representation validation

Prove the selected Phase 2 analysis derivative feeds the adapter correctly.

Resolve any double-mask difference by measured fixture comparison.

### P3-B5 — Golden oracle

Create sanitized/public/synthetic or approved research fixtures with expected:

```text
input SHA
analysis SHA
transform
class order
output shape
score constraints
grade
attention shape if applicable
```

Do not invent expected clinical performance.

### P3-B6 — Bridge + persistence

Integrate raw grading evidence with invocation/model/preprocessing lineage.

Do not overwrite physician review.

### P3-B7 — Explainability

Versioned attention evidence if technically available and validated.

### P3-B8 — UWF clinician UI

Show compact UWF grading suggestion with explicit research/validation limitation and manual continuity.

### Chunk B acceptance

At minimum:

```text
artifact/hash receipt
security receipt
successful controlled load
fixture inference
deterministic output contract
same-input repeatability within expected deterministic behavior
Bridge mapping
analysis binding
human-review preservation
error/manual path
attention warning if enabled
```

### Chunk B review

One independent exact-candidate substantive review.

---

## CHUNK C — Lesion/comparator and engineering-framework decisions

**IDs:** `P3-C1` through `P3-C7`

### P3-C1 — PRISM implementation reconciliation

Compare:

```text
current repo PRISM
historical research adapter
```

Record:

```text
ROI cropper usage
transforms
thresholds
fold loading
fusion
box mapping
runtime dependencies
```

Choose one explicit comparator identity.

No hybrid by accident.

### P3-C2 — CFP qualification preservation

Keep current CFP behavior regression-tested.

### P3-C3 — UWF comparator experiment

Only if allowed on public/research UWF data.

Result remains:

```text
NOT_VALIDATED_FOR_UWF
COMPARATOR_ONLY
```

unless owner later changes release policy.

### P3-C4 — Native UWF localizer decision

If no qualified candidate exists:

```text
DEFERRED_NO_QUALIFIED_CANDIDATE
```

with no fabricated replacement.

### P3-C5 — MONAI evaluation

Evaluate M0/M1/M2/M3 adoption levels.

Produce concise decision record:

```text
ADOPT
DEFER
REJECT
```

with exact reasons.

### P3-C6 — Clef/Clef-Flash comparator

Non-blocking.

Run only if environment/data/resources are appropriate.

No clinician display.

### P3-C7 — Longitudinal

Record learned track `DISABLED` unless evidence changes.

### Chunk C review

One independent review of exact candidate/decision evidence.

---

## CHUNK D — Target runtime, live Model API, offline, and final integration

**IDs:** `P3-D1` through `P3-D8`

### P3-D1 — Exploratory target-host qualification

On designated GPU host collect:

```text
GPU
driver
CUDA
Python
torch/torchvision
other model deps
artifact digest
cold-load time
warm latency distribution
VRAM peak/steady
failure recovery
```

### P3-D2 — Acceptance profile proposal

From exploratory measurements, propose a versioned operational profile.

Do not declare PASS from self-selected after-the-fact thresholds.

### P3-D3 — Owner freezes operating profile

Owner decision required for final qualification thresholds/topology.

Until then:

```text
PERFORMANCE = MEASURED_NOT_QUALIFIED
```

### P3-D4 — Final target-host qualification

Run against the frozen profile.

### P3-D5 — Offline operation

After approved setup:

- disable external network dependency where practical;
- `/health` works;
- capability discovery works;
- selected inference works;
- manual review still works on Model API outage.

### P3-D6 — Live Model API Gate C

Use the actual approved test server/URL/token.

Verify Settings test/save + inference path.

### P3-D7 — Frozen UX regression

Run required P3-0 viewport/accessibility/manual-flow checks on Phase 3 integration.

Do not redesign the UI.

### P3-D8 — Final Phase 3 audit

Run:

```text
code
contracts
model evidence
runtime
security
provenance
human-authority
offline
UX
docs
Git/Brain
```

### Chunk D review

One final exact-candidate integration review.

---

# 24. Performance qualification

Do not invent thresholds in this planning document.

## 24.1 Exploratory run

Measure first.

Suggested distributions:

```text
cold start
first inference
warm p50
warm p95
throughput under expected serial use
VRAM peak
VRAM steady
recovery after failed inference
```

## 24.2 Freeze profile after measurement

Owner chooses the acceptable operational profile only after exploratory evidence.

Record:

```text
profile ID
hardware
enabled capabilities
load strategy
latency/VRAM limits
timeout
concurrency
recovery expectation
```

## 24.3 Any profile change requires requalification

No retroactive PASS.

---

# 25. Model API health semantics

`/health` should distinguish:

```text
service alive
runtime available
asset verified
capability loaded
capability enabled
degraded capability
```

A healthy web process with missing model artifact is not equivalent to a ready capability.

Do not expose secret paths/tokens.

Example conceptual summary:

```text
service_status = PASS
manual_workflow = AVAILABLE

capabilities:
  dr_grade:
    provider = uspec...
    runtime = LOADED
    release = RESEARCH_ONLY

  core_lesion_localization:
    provider = none
    release = DEFERRED
```

---

# 26. Failure semantics

## Missing artifact

```text
BLOCKED_ARTIFACT
manual path continues
```

## Invalid expected hash

```text
INVALID_EXPECTED_HASH
do not substitute observed hash
```

## Hash mismatch

```text
HASH_MISMATCH
stop provider
```

## Loader/security blocked

```text
SECURITY_BLOCKED
do not deserialize
```

## Runtime/dependency failure

```text
RUNTIME_FAILED
preserve verified-byte receipt
```

## CUDA/OOM

```text
RESOURCE_FAILED
preserve artifact integrity status
```

## Unsupported modality

```text
UNSUPPORTED
not grade 0
not empty reviewed findings
```

## Timeout/transport

```text
AI unavailable
manual workflow continues
```

## Stale response

```text
STALE_RESULT
must not overwrite human decision
```

---

# 27. Testing matrix

## 27.1 Contract tests

Add/extend tests for:

- legacy bridge.v1 round trip;
- new versioned result contract;
- capability descriptor;
- unknown extra field behavior;
- source/analysis/model binding;
- explanation payload typing;
- missing explanation;
- invocation idempotency;
- stale response;
- duplicate response;
- malformed remote payload;
- wrong image hash;
- wrong analysis hash/context;
- legacy remote compatibility.

## 27.2 Source-origin tests

```text
PUBLIC allowed
SYNTHETIC allowed
WORKSPACE blocked
UNKNOWN blocked
pseudonymous WORKSPACE still blocked
```

until owner policy changes.

## 27.3 USPEC tests

Without claiming clinical performance:

- expected hash;
- deterministic selection;
- artifact role;
- class order;
- preprocessing;
- output shape;
- score validity;
- grade mapping;
- repeatability;
- attention shape/version;
- attention unavailable fallback;
- source/analysis binding;
- runtime load error;
- unsupported state.

## 27.4 PRISM tests

- current legacy CFP regression;
- exact selected research adapter fixture if adopted;
- ROI cropper behavior;
- box coordinates;
- `review_boxes` distinction if candidate exposes them;
- empty output semantics;
- UWF comparator warning;
- no UWF native claim.

## 27.5 Persistence tests

- append AI run;
- previous run preserved;
- physician grade preserved after later model run;
- annotations preserved;
- revision conflict;
- restart;
- PostgreSQL round trip;
- workspace isolation.

## 27.6 UI tests

- capability-based status;
- disabled UWF capability;
- enabled UWF grade;
- model warning near result;
- raw score wording not “clinical probability”;
- Explainability available/unavailable;
- Models & Audit dynamic provider list;
- comparator hidden from normal Review;
- manual AI-off full flow.

## 27.7 Browser tests

Use Playwright for deterministic Phase 3 browser evidence.

At minimum:

```text
1920×1080
1440×900
1366×768
1280×720
1024×768
representative mobile
```

Phase 3 must preserve P3-0 image dominance and primary-action hierarchy.

---

# 28. Validation commands

Use focused tests while iterating.

Stable candidate:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check dr_support tests

cd frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
cd ..

npm.cmd test
.\.venv\Scripts\python.exe scripts\docs\check_docs.py
git diff --check
```

Model-server runtime checks must run inside the exact selected Model API environment, not by assuming the workstation `.venv` proves model compatibility.

Record skipped/not-run checks honestly.

---

# 29. PostgreSQL requirements

Phase 3 must not rely only on SQLite/synthetic memory state for final persistence claims.

If an approved PostgreSQL test DSN is available:

- run model result/inference-history round trip;
- restart;
- stale revision/CAS;
- workspace isolation.

If unavailable:

```text
POSTGRES_PHASE3_RUNTIME = NOT_RUN
```

and do not claim it passed.

Phase 1/2 historical evidence remains background, not a new Phase 3 execution.

---

# 30. Security/privacy checks

Before integration:

- no checkpoint in Git;
- no `.env`;
- no bearer token;
- no DSN;
- no hospital PHI;
- no absolute private model path in public evidence;
- no arbitrary untrusted code execution from bundle manifests;
- no external model download during normal offline inference;
- no raw remote error/stack in clinician UI.

MONAI/Clef exploration must obey the same rule.

---

# 31. Documentation updates

Update only affected canonical material.

Likely:

```text
README.md
THIRD_PARTY_NOTICES.md
docs/operations/MODEL_SERVER.md
docs/operations/CONFIGURATION.md
developer model/API manual sections
clinician model-evidence sections
M1_MASTER_PLAN.md
this Phase 3 execution evidence
```

Do not rewrite Phase 1/2/P3-0 history.

If MONAI or Clef is only evaluated and not adopted, document that status without adding it as a runtime dependency.

---

# 32. Evidence artifacts to create

Create repository-safe text evidence, not model artifacts.

Suggested:

```text
docs/milestone/m1/M1_PHASE3_EXECUTION_R3.md
docs/milestone/m1/M1_PHASE3_EVIDENCE.md
docs/milestone/m1/phase3/
  capability_registry_receipt.json
  artifact_receipt.md
  security_runtime_receipt.md
  adapter_contract_receipt.md
  monai_decision.md
  comparator_decision.md
  performance_profile.md
  final_phase3_receipt.md
```

MAIN may reduce file count if one structured evidence document is clearer.

Do not create redundant planning documents.

---

# 33. Owner decision checkpoints

Most work must proceed without asking the owner.

Stop only for these actual decisions.

## OD-1 — Artifact/trust conflict

Observed USPEC bytes/source do not match expected evidence.

## OD-2 — Security path

A selected runtime/loader remains affected or cannot be safely qualified.

## OD-3 — Hospital data authorization

Any request to send `WORKSPACE`/hospital-origin image bytes to Model API.

## OD-4 — PRISM UWF assistive enablement

Engineering comparator can proceed, but clinician-facing UWF fallback enablement requires owner/clinical decision.

## OD-5 — Operating profile

After exploratory GPU evidence, owner freezes final runtime acceptance profile.

## OD-6 — Clinical release

Promoting a research model from comparator/research-only to clinician-visible primary/assistive release.

## OD-7 — Clef fine-tuning

Zero-shot comparator may proceed within authorized research scope. Fine-tuning is a separate decision.

Routine decisions such as file organization, registry implementation, test layout, adapter class design, or MONAI engineering adoption/defer decision may be made by MAIN when frozen contracts remain intact.

---

# 34. Independent review policy

Use substantive chunk reviews:

```text
Chunk A → one independent review
Chunk B → one independent review
Chunk C → one independent review
Chunk D → one final integration review
```

Findings:

```text
BLOCKER
REQUIRED FIX
NON-BLOCKING / DEFER
```

Fix BLOCKER/REQUIRED FIX inside the approved scope.

Re-review changed diff only.

Do not reopen accepted Phase 2/P3-0 behavior without regression evidence.

If reviewer-account independence is not established, report reduced independence honestly.

---

# 35. Local self-audit requirement

Before each independent review, MAIN performs local self-audit.

Final self-audit must answer:

## Model identity
- exact provider?
- exact artifact?
- exact digest?
- deterministic selection?

## Security
- exact runtime?
- exact loader?
- advisory review?
- trust evidence?

## Input
- source SHA?
- origin?
- analysis SHA?
- transform?
- mask/representation version?

## Output
- typed task?
- raw AI preserved?
- human decision separate?
- explanation correctly labeled?

## Staleness
- request revision bound?
- late response protected?
- retry idempotent?

## Runtime
- GPU?
- load?
- latency?
- VRAM?
- offline?
- recovery?

## UI
- P3-0 preserved?
- one primary action?
- manual path?
- no technical clutter?
- comparator hidden?

## Claims
- no hospital validation claim?
- no calibrated probability claim?
- no UWF claim for CFP provider?
- no rights claim without evidence?

---

# 36. Phase 3 closeout categories

Report capability outcomes independently.

Example:

```text
3G USPEC UWF grading
artifact: VERIFIED_BYTES
security: PASS
runtime: PASS
bridge: PASS
L4 profile: PASS
domain: UWF_RESEARCH_EVALUATED
clinical validation: NOT_ESTABLISHED
rights: UNVERIFIED
release: RESEARCH_ONLY / ASSISTIVE_ENABLED per owner

3L native UWF localization
DEFERRED_NO_QUALIFIED_CANDIDATE

PRISM
CFP runtime: PASS/...
UWF: NOT_VALIDATED_FOR_UWF
release: COMPARATOR_ONLY / DISABLED

MONAI
EVALUATED_ADOPTED_BUNDLE
or EVALUATED_DEFERRED

Clef
COMPARATOR_NOT_RUN / COMPARATOR_EVALUATED / DEFERRED_RESOURCE_LIMIT

Longitudinal
DISABLED
```

Do not compress this into a single “AI PASS”.

---

# 37. Phase 3 overall completion gate

Phase 3 may be proposed `READY_FOR_OWNER_REVIEW` when:

- Chunk A foundation is integrated;
- selected capability registry is deterministic;
- bridge compatibility and stale-response safety pass;
- Phase 2/P3-0 regression passes;
- preferred USPEC track has an honest terminal state;
- lesion track has an honest terminal state;
- Model API live-success is PASS or explicitly BLOCKED/NOT_RUN with reason;
- runtime/security evidence exists for every enabled provider;
- public/synthetic source-origin contract is safe;
- hospital-origin data remains blocked unless separately authorized;
- MONAI decision is recorded;
- Clef comparator state is recorded;
- longitudinal state is recorded;
- docs/evidence are current;
- main is clean and synchronized;
- Brain is FRESH.

Do not mark Phase 3 `DONE` inside the implementation run unless the owner explicitly accepts the Phase 3 evidence/UAT afterward.

---

# 38. Owner UAT after Phase 3 integration

Use public/synthetic or separately authorized data only.

Owner UAT should verify:

## UAT-1 — Manual path

Model API unavailable:

```text
review → grade → findings → finish
```

still works.

## UAT-2 — UWF grade suggestion

If USPEC is enabled:

- compact suggestion appears;
- exact model limitation is understandable;
- human grade remains easy;
- no extra mandatory model interaction.

## UAT-3 — Explainability

If available:

- attention is visually understandable as model evidence;
- it is not presented as lesion localization.

## UAT-4 — Lesions

If only PRISM comparator/fallback exists:

- CFP/UWF limitation is obvious;
- no empty-box negative interpretation;
- human correction flow unchanged.

## UAT-5 — Model outage

Timeout/unavailable/error remains local and recoverable.

## UAT-6 — Models & Audit

Exact identity/version/runtime/warnings are visible without cluttering the clinical path.

## UAT-7 — Connection

Approved Model API connection test succeeds when target exists.

## UAT-8 — UX freeze

Annotation/grade/worklist behavior still matches accepted P3-0.

---

# 39. Final execution marker

The implementation goal stops at:

```text
PHASE 3 READY_FOR_OWNER_REVIEW
```

Expected state at that point:

```text
Phase 1 = DONE
Phase 2 = DONE
P3-0 = DONE
Phase 3 = READY_FOR_OWNER_REVIEW
Phase 4 = NOT_STARTED
Phase 5 = NOT_STARTED
```

Owner acceptance is a separate closeout action.

---

# 40. Required final receipt

Return a concise evidence-based receipt:

```text
Starting SHA:
Chunk A SHA:
Chunk B SHA:
Chunk C SHA:
Chunk D / final main SHA:

Git:
- main == origin/main:
- clean:
- worktrees/branches removed:

Brain:

Bridge:
- v1 compatibility:
- Phase 3 versioned contract:
- capability discovery:
- source-origin behavior:
- stale/duplicate response guard:
- inference history:

USPEC:
- artifact path identity (redacted if needed):
- expected SHA:
- observed SHA:
- trust:
- security:
- adapter version:
- representation:
- fixture inference:
- explanation:
- runtime:
- domain:
- clinical validation:
- rights:
- release:

PRISM:
- selected adapter identity:
- ROI cropper behavior:
- CFP status:
- UWF status:
- review_boxes:
- empty-output semantics:
- release:

Native UWF lesion:
- status:

MONAI:
- version/reference evaluated:
- adoption level:
- decision:

Clef:
- model evaluated:
- data scope:
- result:
- clinical exposure:
- status:

Longitudinal:

Model API:
- health:
- capability discovery:
- live Gate C:
- auth:
- offline:
- one-worker/runtime policy:
- cold load:
- warm p50/p95:
- VRAM:
- recovery:

Persistence:
- PostgreSQL:
- restart:
- CAS:
- human decision protection:
- AI history:

UX:
- P3-0 regression:
- manual AI-off:
- Review:
- Models & Audit:
- accessibility:
- responsive:

Security/privacy:
- checkpoint in Git:
- secrets:
- hospital data:
- advisory receipt:

Validation:
- backend:
- Ruff:
- frontend:
- typecheck:
- build:
- root smoke:
- docs QA:
- git diff --check:
- Playwright:

Independent reviews:
- Chunk A:
- Chunk B:
- Chunk C:
- Chunk D:

Known limitations:
Owner decisions still pending:

Phase 3:
READY_FOR_OWNER_REVIEW

Phase 4:
NOT_STARTED

Final marker:
PHASE 3 READY_FOR_OWNER_REVIEW
```

---

# 41. Public technical references reviewed for r3.0

These references inform engineering evaluation only. They do not constitute clinical evidence.

## PyTorch security

- `https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p`
- Published affected range for this issue: `<= 2.9.1`
- Published patched range: `>= 2.10.0`
- Final runtime version must still be selected by compatibility/security testing, not by advisory number alone.

## MONAI

- `https://github.com/Project-MONAI/MONAI`
- `https://monai.readthedocs.io/en/1.6.1/bundle_intro.html`
- MONAI 1.6.1 release line was current during this reconciliation.
- Bundle is evaluated as a reproducibility/packaging mechanism, not as a UWF DR model.

## Clef

- `https://blog.cloudflare.com/clef-decision-models/`
- `https://huggingface.co/Cloudflare/clef`
- `https://huggingface.co/Cloudflare/clef/blob/main/joint_schema_model.py`
- Evaluated only as a non-blocking structured multimodal decision-model comparator.

---

# 42. Change log

## r3.0 — 2026-10-04

Reconciles historical Phase 3 r2.2 with the accepted Phase 1, Phase 2 and P3-0 repository state.

Major additions:

- exact current-repo gap audit;
- capability-oriented provider architecture;
- protected Bridge v1 + versioned Phase 3 extension;
- append-only inference lineage and stale-response protection;
- dynamic Model Gateway discovery;
- deterministic installed-capability registry;
- dedicated Model API runtime/security qualification;
- current PyTorch pre-deserialization gate;
- explicit reconciliation of legacy repo PRISM vs research PRISM adapter;
- native UWF lesion track may truthfully defer;
- MONAI engineering evaluation;
- Clef/Clef-Flash non-blocking comparator;
- P3-0 frozen UX integration rules;
- target-host performance-profile freeze;
- live Model API Gate C;
- chunked self-audit/review policy;
- category-specific closeout rather than one vague AI-ready flag.

No model was loaded, trained, enabled, or clinically validated by writing this document.

# End — M1 Phase 3 Execution r3.0
