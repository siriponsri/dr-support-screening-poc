# DR Screening — Milestone 1 Master Plan

**Document path in repository:** `docs/milestone/M1_MASTER_PLAN.md`  
**Version:** 1.0 working master  
**Date:** 2026-09-25  
**Status:** Owner-directed working plan; update at the end of each phase  
**Primary repository:** `siriponsri/dr-support-screening-poc`  

---

## 1. Purpose of this document

This file is the single traceable master plan for Milestone 1 (M1). It exists so the owner, the clinical team, and coding agents can answer four questions at any time:

1. What is M1 supposed to deliver?
2. Which phase is currently active?
3. What evidence proves that a phase is complete?
4. Which limitations, blockers, and owner decisions remain open?

This document should remain concise enough to review before each implementation phase, but detailed enough to prevent scope drift. Do not create large numbers of overlapping planning files. Phase-specific documents may be created only when they are necessary for implementation or review.

After the owner approves and commits this file, it becomes the M1 planning source of truth wherever it conflicts with earlier M1 planning drafts. Existing repository safety rules, `AGENTS.md`, frozen behavior, `DESIGN.md`, and approved clinical contracts remain authoritative unless explicitly amended by the owner.

---

## 2. M1 product objective

M1 is an **AI-assisted UWF retinal labeling and review workstation** that helps ophthalmologists review the hospital's existing diabetic-retinopathy image collection and produce high-quality, traceable labels for later model development.

The primary product value of M1 is not merely to display model predictions. It is to convert an existing, incompletely labeled hospital image collection into a structured, physician-reviewed dataset while making the physician's limited labeling time as productive as possible.

The intended M1 workflow is:

```text
Workspace
→ ingest retinal images
→ resolve patient / eye / visit evidence
→ prepare an analysis representation without changing the source image
→ obtain available AI suggestions
→ physician reviews the original image and AI evidence
→ physician confirms, corrects, rejects, or adds labels
→ save all provenance and review decisions in PostgreSQL
→ reopen and continue work later
→ inspect workspace data
→ export physician-confirmed datasets/manifests for later training
```

M1 is also the data foundation for later hospital-domain models. The system therefore must preserve the difference between:

- source image evidence;
- AI prediction;
- physician-confirmed result;
- physician-added result;
- rejected AI suggestion;
- unreviewed AI suggestion;
- review completeness;
- model/preprocessing provenance.

An AI suggestion must never silently become ground truth merely because it was displayed on screen.

---

## 3. Clinical and product scope

### 3.1 Primary image modality

The primary M1 modality is **ultra-widefield retinal imaging (UWF)** because this matches the hospital image collection used for the project.

The product may continue to support conventional color fundus photography (CFP) where the existing application already supports it, but CFP support must not be confused with validated UWF AI performance.

### 3.2 DR grading labels collected in M1

M1 should collect the full physician-confirmed five-level DR grade whenever the physician is willing and able to provide it:

| Internal value | Clinician-facing label |
|---|---|
| `0` | No apparent DR |
| `1` | Mild NPDR |
| `2` | Moderate NPDR |
| `3` | Severe NPDR |
| `4` | Proliferative DR |
| separate state | Ungradable |
| separate state | Unknown / not yet determined |

The system may later derive coarser labels, such as `DR` versus `NO_DR`, from a physician-confirmed grade. The derived label must not replace or destroy the original grade.

Referral status, DME status, and DR grade are separate concepts. Do not infer DME from hard exudates alone. Do not create a referral rule without an explicitly approved clinical definition.

### 3.3 Core findings

M1 should make the most common and immediately useful lesion annotations fast to review. The initial **Core findings** section should include at least:

- Microaneurysm
- Retinal hemorrhage
- Hard exudate
- Cotton-wool spot / soft exudate

These are the minimum high-priority lesion families for the initial labeling workflow. They are not the final complete diabetic-retinopathy taxonomy.

### 3.4 Advanced findings

Because ophthalmologist labeling time is scarce, M1 should capture additional clinically useful findings whenever the physician can provide them. These should be separated from the core workflow so the primary review experience remains fast.

The initial **Advanced findings** candidate set includes:

- Dot hemorrhage
- Blot hemorrhage
- Flame-shaped hemorrhage
- Venous beading
- Intraretinal microvascular abnormality (IRMA)
- Neovascularization of the disc (NVD)
- Neovascularization elsewhere (NVE)
- Preretinal hemorrhage
- Vitreous hemorrhage
- Fibrous proliferation

This list is a candidate labeling schema, not a claim that every class already has a usable AI model or training dataset.

The clinical team must be able to refine class definitions, geometry, ambiguity rules, and terminology without corrupting historical data. Therefore every annotation record must carry a taxonomy/schema version.

### 3.5 Review completeness must be explicit

An empty annotation list is ambiguous unless review completeness is stored.

At minimum, each annotation group should support states equivalent to:

- `NOT_REVIEWED`
- `PARTIALLY_REVIEWED`
- `REVIEWED_NONE_FOUND`
- `REVIEWED_FINDINGS_RECORDED`

This distinction is essential for future training. For example:

- the physician never opened Advanced findings → this is **not** a negative label;
- the physician reviewed Advanced findings and explicitly confirmed none were present → this may become a valid negative label under the approved export policy;
- the physician reviewed only selected classes → only those reviewed classes should be treated as resolved.

### 3.6 Longitudinal data in M1

M1 should establish reliable identity and visit structure so future same-eye longitudinal analysis is possible.

The product should capture or resolve, with physician confirmation where needed:

- pseudonymous patient key;
- laterality;
- visit/capture sequence evidence;
- reliable acquisition date/time where available;
- camera/device metadata where available;
- image quality/reviewability;
- same-patient/same-eye pairing evidence.

The UI may provide side-by-side comparison and physician change labeling when useful.

A learned longitudinal AI model is desirable but is not allowed to block the primary M1 labeling workflow. If the model is unavailable, longitudinal AI must remain optional/off while the system still captures the data required to develop it later.

---

## 4. Architecture that must be preserved

M1 should evolve the current repository rather than replace it.

Preserve the established architecture unless an owner-approved change is recorded:

```text
React / Vite clinician UI
        ↓
FastAPI application
        ↓
PostgreSQL authoritative database
        ↓
Local image store / approved storage

FastAPI / worker
        ↓
Hospital-local Model API
        ↓
Locally installed model weights
```

### 4.1 Application and model separation

The workstation/application should not directly load large model weights. Model inference remains behind the Model API boundary.

This separation allows:

- the application to remain usable when AI is unavailable;
- models to be replaced independently;
- model-specific GPU requirements to remain outside the main application process;
- model provenance and readiness to be reported honestly;
- optional capabilities such as longitudinal inference to be disabled without affecting grading or annotation.

### 4.2 Offline hospital operation

After approved installation/setup, normal hospital inference must not require a cloud inference API.

Model installation may require a separate approved online preparation step, but the final inference bundle must support local operation with:

- pinned dependencies;
- permitted weights;
- weight/checkpoint hashes;
- known preprocessing version;
- model metadata;
- readiness/health checks.

### 4.3 Original image integrity

Original admitted images are immutable source evidence.

Do not overwrite, recompress, rename, or destructively mask the source image as part of normal analysis.

If M1 creates a valid-retina mask or analysis representation, store enough provenance to reconstruct which representation was used for each prediction.

---

## 5. UWF preprocessing and artifact handling

Hospital UWF images may contain machine borders, eyelashes/lids, glare, reflection, or other non-retinal structures. Existing CFP-oriented models may incorrectly treat these as image evidence.

M1 should therefore maintain two distinct concepts:

1. **Original image** — the immutable source shown to the physician.
2. **Analysis representation** — a derived image that may mask regions considered invalid for AI analysis.

### 5.1 Analysis-mask requirements

A preprocessing pipeline may:

- estimate the visible retinal field;
- exclude clear machine rim/background;
- exclude only regions supported by deterministic/validated preprocessing logic;
- fill excluded regions with a neutral analysis value when required by the model;
- preserve the original image dimensions/canvas when practical;
- preserve coordinate mapping to the original image.

A mask must not be presented as clinically validated retinal segmentation unless it has actually been validated for that purpose.

### 5.2 Failure behavior

When a safe analysis representation cannot be produced:

- the physician must still be able to review and label the image;
- AI inference may be unavailable for that image;
- the UI must explain the unavailable state without exposing raw internal exceptions;
- the source image must remain accessible.

### 5.3 Processing Details surface

M1 should include a secondary, non-primary-flow surface named **Processing details**.

It should be able to show, where available:

```text
Original image
→ valid-retina / analysis mask
→ analysis representation
→ model input transformation
→ model output provenance
```

It is not necessary to store every debug screenshot or transient visualization. However, the system should retain enough provenance to prove which mask, transform, model, and source image produced a stored AI result.

---

## 6. AI model strategy

M1 uses two model strategies in parallel:

1. **Preferred path:** develop or integrate models that are actually appropriate for UWF.
2. **Temporary fallback path:** when native UWF models are not ready in time, allow existing CFP-based RETFound and PRISM-DR assistance with explicit clinician-facing limitations.

The fallback exists to keep physician labeling productive. It must not be reported as a UWF-validated model.

### 6.1 Preferred UWF model work

Model experimentation/training may proceed in parallel with repository development.

Current research direction may include:

- UWF DR grading using a UWF-specific fine-tuned approach such as DINOv3 features + patch/MIL + DR grading head;
- UWF lesion localization trained or adapted using eligible spatial labels;
- optional longitudinal comparison when eligible same-patient/same-eye pair labels exist.

Any selected UWF model must preserve:

- exact model identity/version;
- exact preprocessing;
- modality declaration;
- class order/taxonomy version;
- checkpoint hash;
- training/evaluation provenance;
- known limitations;
- offline inference bundle requirements.

### 6.2 Temporary CFP fallback

If the UWF-native model is not ready for an M1 physician review session, the application may temporarily offer:

- existing RETFound grading output; and/or
- existing PRISM-DR lesion suggestions;

only if the software keeps their modality limitation explicit.

The fallback status must be recorded as something equivalent to:

```text
model_domain = CFP
input_modality = UWF
validation_status = NOT_VALIDATED_FOR_UWF
usage_mode = TEMPORARY_ASSISTIVE_FALLBACK
```

The system must not silently change RETFound/PRISM metadata from CFP to UWF merely to enable the route.

### 6.3 Mandatory physician-facing fallback notice

When a CFP-based model is shown on a UWF case, the primary review page must show a concise notice near the AI result.

Recommended English UI copy:

> **CFP-based AI — limited UWF validation.** This model was trained for conventional color fundus photographs, not ultra-widefield images. UWF field-of-view, peripheral findings, image artifacts, and lesion appearance may reduce accuracy. Review the full image and confirm, correct, or reject all AI suggestions.

A shorter badge may be used in dense UI:

> **CFP-based AI · UWF limitation**

A Processing details/help surface may additionally state:

> AI output is provided only as temporary review assistance. It is not evidence that this model has been validated for ultra-widefield screening performance.

### 6.4 Additional fallback restrictions

When CFP fallback is active:

- the physician remains authoritative;
- untouched AI suggestions are not automatically gold labels;
- an empty lesion result does not mean that no lesion exists;
- peripheral UWF retina must not be assumed to have equivalent sensitivity to CFP-trained behavior;
- confidence/softmax values must not be presented as calibrated clinical probabilities unless calibration has been established;
- the data export must record the exact fallback model and limitation state;
- the UI must allow manual labeling even if the model fails or is disabled.

### 6.5 M1 completion semantics with fallback models

M1 may be operationally released for labeling/review with the temporary CFP fallback if the owner accepts the limitation and all applicable workflow/data-integrity gates pass.

However, the status must remain explicit:

- **M1 application/workflow:** may be `DONE`;
- **native UWF grading model:** `DONE`, `BLOCKED`, or `DEFERRED` based on evidence;
- **native UWF lesion model:** `DONE`, `BLOCKED`, or `DEFERRED` based on evidence;
- **fallback CFP provider:** `ACTIVE_WITH_LIMITATION` when used.

Do not mark a native UWF model capability complete merely because the fallback path is functioning.

This distinction gives the project schedule flexibility without hiding scientific limitations from the clinical team.

---

## 7. PostgreSQL and data model goals

PostgreSQL becomes the authoritative persistent database for M1.

The migration must cover both major persistence concerns in the current product:

- clinical/review case state;
- workspace/catalog state.

Do not migrate only one SQLite path and report PostgreSQL migration complete.

### 7.1 Required logical entities

The exact normalized schema is an engineering decision after repository audit, but the data model must be able to represent at least:

```text
Workspace
Patient (pseudonymous)
Eye
Visit / Capture
Image
Image admission / quality / modality
Analysis representation / transform provenance
Model
Model version / artifact identity
Inference job
Raw prediction
DR grade review
Annotation
Annotation review decision
Annotation-group completeness
Review/audit event
Dataset/export snapshot
```

### 7.2 Minimum provenance requirements

A clinically reviewed result should be traceable to:

- workspace;
- source image SHA-256 or equivalent immutable identity;
- source dimensions;
- patient/eye/visit context;
- modality;
- reviewer;
- review timestamp;
- model ID/version when AI was used;
- preprocessing/mask/transform version when AI was used;
- original AI value;
- final physician-confirmed value;
- edit/reject/addition lineage;
- taxonomy version;
- record revision.

### 7.3 Concurrency and auditability

M1 should avoid silent last-write-wins corruption for clinician review.

Where feasible within the existing architecture, use revision/version checks for updates and retain an audit trail for clinically meaningful changes.

---

## 8. Workspace Data surface

M1 should provide a read-only clinician/developer-facing page called **Workspace data**.

The goal is to make stored structured information visible without requiring direct database access.

Minimum capabilities:

- list current workspace records;
- filter by patient key, eye, visit, grade, review status, annotation readiness, and model where practical;
- show human-readable columns;
- inspect structured JSON/details for a selected record;
- export an authorized CSV snapshot;
- export an authorized JSON snapshot;
- show training/export readiness separately for grading and lesion tasks.

This page is not a general SQL administration console.

It must respect workspace boundaries and must not expose secrets or records outside the selected/authorized workspace.

---

## 9. Training-data export principles

The main downstream value of M1 is a clean physician-reviewed dataset.

### 9.1 Grade export

A grade may be training-ready only when applicable requirements are satisfied, including:

- image identity/provenance available;
- valid inclusion/admission state;
- physician final grade recorded;
- reviewer identity recorded;
- review timestamp recorded;
- grade confirmation state valid;
- patient-group key available when required for patient-disjoint splitting.

### 9.2 Lesion/finding export

An annotation may be training-ready only when its review state and the annotation group's completeness support that conclusion.

Default rules should prevent these from becoming gold labels:

- untouched AI suggestions;
- annotations in a group the physician did not review;
- unconfirmed imported annotations;
- model attention maps converted into pseudo-lesions without an approved localization model;
- ambiguous findings that were never resolved under the active taxonomy policy.

### 9.3 Negative labels

A negative label must be explicit.

`REVIEWED_NONE_FOUND` may become a usable negative under an approved taxonomy/export policy.

`NOT_REVIEWED` must never be exported as a negative merely because no annotation row exists.

### 9.4 Dataset snapshots

Exports should be reproducible snapshots, not mutable views with no identity.

Each dataset export should record, as applicable:

- export ID;
- schema version;
- taxonomy version;
- created timestamp;
- workspace ID;
- source image hashes;
- record revisions;
- task-specific eligibility decisions;
- coordinate system;
- annotation provenance;
- model provenance for retained AI-originated history;
- patient grouping key for split safety.

---

## 10. Six M1 phases

M1 is executed as six phases. The phases define review gates, not necessarily strict serial execution for every technical task. Model experimentation may run in parallel where it does not change unfrozen product contracts.

---

# Phase 0 — Baseline & Scope Freeze

## Goal

Establish the exact starting point and freeze the practical M1 scope before implementation writes begin.

## Required work

1. Verify actual local repository root, worktree, branch, HEAD, and status under `AGENTS.md`.
2. Read current `AGENTS.md`, `README.md`, `DESIGN.md`, relevant milestone specs, user manual sources, model contracts, and operational docs.
3. Identify any uncommitted or interrupted work. Do not overwrite it.
4. Inventory current:
   - FastAPI routes/services;
   - React clinician workflow;
   - Workspace Manager;
   - image admission and UWF logic;
   - patient/eye resolver;
   - SQLite stores;
   - dataset export paths;
   - Model API routes/providers;
   - RETFound and PRISM-DR behavior;
   - current tests.
5. Reconcile current code with this master plan.
6. Record exact conflicts requiring owner decisions before Phase 1.
7. Confirm the M1 six-phase plan and current fallback-model policy.

## Phase 0 must not

- rewrite the application;
- migrate the database;
- alter clinical semantics silently;
- overwrite unresolved work;
- claim model readiness from notebook existence;
- fabricate missing local repository evidence.

## Exit evidence

Phase 0 is complete when:

- repository/worktree state is known;
- current architecture/persistence/model paths are documented;
- blockers and contradictions are explicit;
- owner-required decisions needed for implementation are identified;
- the next bounded Phase 1 task is clear.

## Phase 0 status tracker

**Status:** `NOT_STARTED`  
**Start date:**  
**Completion date:**  
**Reviewed by:**  
**Evidence / commit(s):**  
**Open blockers:**  
**Owner decisions:**  

---

# Phase 1 — Data Foundation & PostgreSQL

## Goal

Create the durable data foundation for physician review, model evidence, workspace separation, and later M2 training.

## Required work

1. Design the smallest compatible PostgreSQL persistence layer after auditing existing repositories/services.
2. Migrate or replace both review persistence and workspace/catalog persistence.
3. Preserve existing user-visible clinician behavior where possible.
4. Add schema support for patient-eye-visit/image relationships.
5. Add model/prediction/review provenance needed by later phases.
6. Add annotation review/completeness semantics.
7. Add revision/audit support for clinically meaningful changes.
8. Add migration/dry-run tooling or a documented migration procedure for existing local development state where applicable.
9. Add backup/restore instructions and test a representative restore path.
10. Validate workspace isolation and restart persistence.

## Acceptance criteria

- application can persist and reopen reviewed cases through PostgreSQL;
- active workspace data remains scoped correctly;
- clinically relevant existing state is not silently discarded;
- restart does not lose committed review state;
- concurrent/revision behavior is tested for the defined M1 usage pattern;
- migration/restore evidence exists;
- SQLite is no longer the authoritative M1 clinical/workspace store after Phase 1 completion.

## Phase 1 status tracker

**Status:** `IN_PROGRESS`
**Start date:** 2026-09-25
**Completion date:**  
**Reviewed by:**  
**Evidence / commit(s):** P1-F foundation integrated at `b63126ae989109e380ef9bdeb6d425c49eb96cec`; detailed execution evidence is in `docs/milestone/m1/M1_PHASE1_POSTGRES.md`.
**Migration evidence:**  
**Restore evidence:**  
**Open blockers:** P1-A, P1-B, migration verification, backup/restore smoke, and final main validation remain.
**Owner decisions:**  

---

# Phase 2 — UWF Labeling Workflow

## Goal

Make the clinician workflow efficient for repeated UWF labeling while maximizing the amount and quality of physician-confirmed information captured per review session.

## Required work

1. Preserve the established viewer and general visual direction.
2. Improve UWF intake/review behavior without treating UWF as CFP.
3. Implement or harden valid-retina/analysis masking and safe failure states.
4. Improve patient/eye/visit evidence extraction and confirmation.
5. Provide efficient DR grade confirmation/editing.
6. Provide **Core findings** annotation workflow.
7. Provide **Advanced findings** as a separate optional section/tab/surface.
8. Record annotation-group completeness.
9. Preserve AI versus human provenance at per-finding level.
10. Support reject/correct/add/confirm actions.
11. Ensure original-image coordinates remain authoritative for stored findings.
12. Ensure manual labeling remains available when AI is unavailable.
13. Add concise clinician-facing CFP-fallback notice when fallback models are used on UWF.

## Acceptance criteria

A physician can:

- open a UWF image;
- confirm patient/eye/visit context;
- see the original image without destructive modification;
- see available AI evidence with correct model-domain warning;
- set or correct DR grade;
- accept/correct/reject suggested core findings;
- add new core findings;
- optionally review/add Advanced findings;
- explicitly indicate whether a finding group was reviewed;
- save and reopen the case;
- continue labeling even if the Model API is unavailable.

## Phase 2 status tracker

**Status:** `NOT_STARTED`  
**Start date:**  
**Completion date:**  
**Reviewed by:**  
**Evidence / commit(s):**  
**Clinical feedback:**  
**Open blockers:**  
**Owner decisions:**  

---

# Phase 3 — AI Models & Model API Integration

## Goal

Provide the best available AI assistance without blocking the labeling workflow or overstating model validity.

## Workstreams

### Phase 3G — Grading

Preferred outcome:

- a UWF-capable grading model with explicit grade output and reproducible local inference bundle.

Temporary fallback when preferred model is not ready:

- RETFound may be shown as CFP-based assistive evidence with the mandatory UWF limitation notice.

### Phase 3L — Lesion/finding localization

Preferred outcome:

- a UWF-capable localization model for the approved scope, beginning with core findings and expanding where data permit.

Temporary fallback when preferred model is not ready:

- PRISM-DR may be shown as CFP-based assistive lesion evidence with the mandatory UWF limitation notice.

### Phase 3T — Longitudinal

Preferred outcome:

- optional same-patient/same-eye change suggestion when an eligible learned model and data exist.

If unavailable:

- keep the feature disabled or provide non-AI comparison tooling without labeling it as a trained model result.

## Required Model API behavior

Every provider must expose enough metadata to determine:

- model ID;
- version/revision;
- task;
- supported/trained modality;
- current input modality;
- taxonomy/class order;
- preprocessing version;
- readiness;
- limitations/warnings;
- artifact/checkpoint identity where applicable.

The application should route based on declared capability rather than by pretending that a CFP model is UWF-native.

## Acceptance criteria

For any AI capability displayed to physicians:

- the exact model is identifiable;
- the input/output contract is validated;
- model-domain limitations are visible;
- inference failure does not block manual review;
- stored predictions preserve model/preprocessing provenance;
- outputs map correctly to original image coordinates where spatial;
- physician changes do not overwrite raw AI history;
- locally installed model inference can be smoke-tested in the intended offline/runtime environment when that provider is declared ready.

Native UWF model work may remain `BLOCKED` or `DEFERRED` while the application uses the explicitly labeled CFP fallback.

## Phase 3 status tracker

**Overall status:** `NOT_STARTED`  
**3G native UWF grading:** `NOT_STARTED`  
**3G CFP fallback:** `AVAILABLE / NOT_AVAILABLE / NOT_REVIEWED`  
**3L native UWF localization:** `NOT_STARTED`  
**3L CFP fallback:** `AVAILABLE / NOT_AVAILABLE / NOT_REVIEWED`  
**3T longitudinal model:** `NOT_STARTED`  
**Start date:**  
**Completion/review date:**  
**Evidence / commit(s):**  
**Model artifact references:**  
**Known model limitations:**  
**Open blockers:**  
**Owner decisions:**  

---

# Phase 4 — Dataset & Review Tools

## Goal

Turn reviewed PostgreSQL data into transparent, queryable, exportable, training-ready assets while preserving provenance and preventing AI-only contamination.

## Required work

1. Add **Workspace data** read-only data surface.
2. Provide useful filters and human-readable records.
3. Provide selected-record details/JSON view.
4. Provide CSV and JSON snapshot export.
5. Provide grading training-readiness status.
6. Provide lesion/finding training-readiness status.
7. Enforce explicit review-completeness rules.
8. Prevent untouched AI suggestions from entering default gold exports.
9. Preserve patient grouping key for patient-disjoint later model splitting.
10. Add **Processing details** surface for source/mask/transform/model provenance.
11. Provide longitudinal pair/history visibility where available.
12. Ensure exported records carry schema/taxonomy versions and snapshot identity.

## Acceptance criteria

- stored DB values, Workspace data display, and exported values agree;
- unreviewed AI suggestions are excluded from gold training exports by default;
- explicit reviewed-negative annotations can be represented without confusing them with not-reviewed cases;
- exports can be reproduced/audited from their metadata;
- clinician-confirmed grade and finding lineage remain visible;
- query/export operations do not mutate clinical review records.

## Phase 4 status tracker

**Status:** `NOT_STARTED`  
**Start date:**  
**Completion date:**  
**Reviewed by:**  
**Evidence / commit(s):**  
**Export sample / schema:**  
**Open blockers:**  
**Owner decisions:**  

---

# Phase 5 — End-to-End Validation & M1 Review

## Goal

Validate the integrated M1 build as the actual product to be reviewed with physicians. There is no separate demo-only implementation.

## Required end-to-end scenario

At minimum, test:

```text
create/open Workspace
→ scan/import UWF images
→ confirm image context
→ inspect original image
→ generate or skip analysis representation
→ run available AI assistance
→ display correct native/fallback model status
→ physician grades case
→ physician reviews/corrects/rejects/adds findings
→ save to PostgreSQL
→ restart/reopen case
→ verify audit/provenance
→ inspect Workspace data
→ export eligible grading/lesion data
→ verify exported records against review state
```

Where longitudinal data are available, also test:

```text
same patient + same eye + different eligible visits
→ comparison view
→ optional model suggestion if enabled
→ physician review
→ persistent result / provenance
```

## Required validation areas

- backend tests;
- frontend tests;
- type checking;
- frontend build;
- database migration/restore evidence;
- browser/owner smoke test against the integrated main build;
- Model API failure behavior;
- fallback-model warning visibility;
- offline inference smoke for providers declared locally ready;
- source-image integrity;
- coordinate round-trip;
- annotation provenance;
- gold-export contamination tests;
- workspace isolation;
- restart/recovery behavior.

## M1 review outcome categories

At final review, report M1 using explicit categories rather than a single vague "done" statement.

### Product status

- `DONE`
- `READY_FOR_REVIEW`
- `BLOCKED`

### Data foundation status

- PostgreSQL ready/not ready
- migration evidence
- restore evidence
- workspace isolation evidence

### Model status

For each capability:

- `NATIVE_UWF_READY`
- `CFP_FALLBACK_ACTIVE`
- `DISABLED`
- `BLOCKED`
- `DEFERRED`

### Clinical-labeling status

- grade workflow ready/not ready;
- core findings ready/not ready;
- advanced findings ready/not ready;
- negative/completeness semantics ready/not ready.

### Export status

- grade export ready/not ready;
- lesion export ready/not ready;
- longitudinal pair data ready/not ready.

## Phase 5 status tracker

**Status:** `NOT_STARTED`  
**Start date:**  
**Completion date:**  
**Reviewed by:**  
**Integrated commit:**  
**Test evidence:**  
**Demo/UAT review date:**  
**Clinical comments:**  
**Accepted limitations:**  
**Open blockers / next milestone:**  

---

## 11. Parallel execution policy

Model research/training and application work may proceed in parallel.

Recommended ownership split:

### Product / repository lane

Primary responsibility:

- repository audit;
- PostgreSQL;
- clinician workflow;
- UWF preprocessing integration;
- model capability API;
- data provenance;
- Workspace data;
- Processing details;
- export;
- integration tests.

### Model / notebook lane

Primary responsibility:

- UWF grading experiments;
- UWF lesion localization experiments;
- longitudinal experiment when eligible labels exist;
- reproducible run artifacts;
- model cards;
- holdout evidence;
- model bundles for local integration.

The two lanes meet through a versioned model/application contract.

Do not allow separate agents to invent incompatible versions of:

- taxonomy;
- model task names;
- modality names;
- prediction schema;
- annotation provenance states;
- database migration contract;
- coordinate system.

Shared contracts must be reviewed before parallel branches that depend on them are merged.

---

## 12. Repository execution rules for coding agents

Every coding agent working on M1 must follow root `AGENTS.md`.

Before implementation writes, the agent must report:

```text
repository root
worktree path
current branch
current HEAD
git status --short --branch
```

Do not implement directly on `main` unless the owner explicitly approves an allowed exception under repository policy.

Use bounded branches/worktrees.

Do not use destructive cleanup to make unexpected work disappear.

Do not merge solely because focused tests pass.

A phase is not complete until required integration validation is complete and the evidence is recorded in this master plan.

---

## 13. How this master plan must be updated

This file is intended to be updated at the **end of each phase**, not rewritten during every small task.

At phase close:

1. change the phase `Status`;
2. enter completion date;
3. add merge/integration commit(s);
4. add important test/evidence paths;
5. list accepted limitations;
6. list remaining blockers;
7. record owner decisions that change later phases;
8. do not erase historical blockers—mark them resolved with evidence where appropriate.

If an owner decision changes M1 scope materially, add an entry to the decision log below before changing implementation semantics.

---

## 14. M1 phase summary tracker

Update this table after each phase review.

| Phase | Name | Status | Integrated commit / evidence | Main blockers / notes |
|---|---|---|---|---|
| 0 | Baseline & Scope Freeze | `NOT_STARTED` |  |  |
| 1 | Data Foundation & PostgreSQL | `IN_PROGRESS` | P1-F foundation integrated at `b63126ae989109e380ef9bdeb6d425c49eb96cec` | P1-A/P1-B, migration, recovery, and final validation remain |
| 2 | UWF Labeling Workflow | `NOT_STARTED` |  |  |
| 3 | AI Models & Model API Integration | `NOT_STARTED` |  | Native UWF work may use explicit CFP fallback temporarily |
| 4 | Dataset & Review Tools | `NOT_STARTED` |  |  |
| 5 | End-to-End Validation & M1 Review | `NOT_STARTED` |  |  |

---

## 15. Model capability tracker

| Capability | Preferred target | Current deployment mode | Status | Limitation / evidence |
|---|---|---|---|---|
| DR grading | Native UWF model | TBD | `NOT_STARTED` | CFP RETFound fallback allowed only with explicit UWF warning |
| Core lesion localization | Native UWF model | TBD | `NOT_STARTED` | CFP PRISM-DR fallback allowed only with explicit UWF warning |
| Advanced finding localization | Per-class UWF capability where feasible | Manual + future AI | `NOT_STARTED` | Never claim unsupported classes are automatically detected |
| Longitudinal change | Optional learned same-eye model | Disabled until ready | `NOT_STARTED` | Comparison/data capture may proceed without model |

---

## 16. Decision log

Do not edit past decisions silently. Add new rows when the owner changes scope.

| Date | Decision | Reason / impact | Owner approval |
|---|---|---|---|
| 2026-09-25 | M1 uses six phases: baseline, PostgreSQL, UWF labeling, AI integration, dataset/review tools, end-to-end validation. | Keep planning traceable and avoid separate demo-only work. | Owner-directed |
| 2026-09-25 | Demo is not a separate milestone. | The next physician demo is a review of the integrated M1 build. | Owner-directed |
| 2026-09-25 | M1 should collect five-grade DR labels when physicians label images. | Physician labeling time is scarce; preserve the richer target and derive coarse labels later. | Owner-directed |
| 2026-09-25 | M1 should capture findings beyond the initial four, using a separate Advanced findings workflow. | Maximize the value of each physician labeling session without overloading the core workflow. | Owner-directed |
| 2026-09-25 | RETFound and PRISM-DR may be used temporarily on UWF when native UWF models are not ready. | Maintain schedule flexibility and AI-assisted review, but disclose that these are CFP-based models with limited/unvalidated UWF performance. | Owner-directed |
| 2026-09-25 | Native UWF capability status must remain separate from fallback availability. | Avoid reporting CFP fallback as proof of UWF model completion. | Owner-directed |

---

## 17. Open clinical decisions

These items should be asked when they become necessary for a phase. Do not block unrelated engineering work prematurely.

### Grading

- Confirm the grading rubric used by the participating ophthalmologists.
- Confirm handling of treated/stable PDR images.
- Confirm when an image is Ungradable versus Unknown.
- Confirm whether referral status should be collected during M1 and under which approved rule.

### Core findings

- Confirm whether microaneurysm and small dot hemorrhage must be separated in all cases or whether an ambiguity class is allowed.
- Confirm annotation geometry for each core finding.
- Confirm whether hemorrhage should initially remain one core class while subtype is captured under Advanced findings.

### Advanced findings

- Confirm exact definitions and geometry for venous beading, IRMA, NVD, and NVE.
- Confirm how uncertain NVD/NVE and other difficult vascular findings should be recorded.
- Confirm when preretinal/vitreous hemorrhage should be spatial versus image-level.
- Confirm whether fibrous proliferation is in the M1 labeling target.

### Longitudinal

- Confirm reliable visit-date evidence.
- Confirm how treatment between visits changes interpretation.
- Confirm whether the physician should label `IMPROVED`, `STABLE`, `WORSENED`, per-finding change, or both.

---

## 18. Known scientific/model limitations to preserve

1. A model trained on CFP is not automatically validated for UWF.
2. Cropping/masking a UWF image does not transform it into the CFP domain.
3. UWF peripheral retina may contain clinically important information that a CFP-trained model did not learn to use.
4. Machine borders, eyelids/eyelashes, glare, and other artifacts can create false model evidence.
5. Image-level attention is not equivalent to a validated lesion localization map.
6. An empty detector output is not proof that the retina contains no lesion.
7. Softmax/confidence scores are not automatically calibrated clinical probabilities.
8. A public dataset result does not establish local hospital performance.
9. Native UWF models require local shadow/clinical review before claims of hospital performance.
10. Dataset/model/code/weight licenses are separate questions; technical accessibility does not establish permitted organizational use.

These limitations must remain visible in planning and model metadata. They should not be hidden merely to simplify a demonstration.

---

## 19. Security, privacy, and data handling

M1 must follow repository security/privacy rules.

Do not commit:

- patient images;
- patient-identifying information;
- local databases;
- model weights;
- API keys/tokens;
- runtime secrets.

Pseudonymous patient keys should be used in product data structures where possible.

Patient data should not be uploaded to public/cloud model-training environments unless the hospital has explicitly authorized that processing path.

Public dataset training and hospital clinical data must remain distinguishable in model provenance.

---

## 20. Definition of M1 completion

M1 is considered ready for owner/physician acceptance when the integrated product demonstrates the full labeling-data lifecycle and all known limitations are reported honestly.

Minimum product completion conditions:

- PostgreSQL is the authoritative M1 persistence layer;
- workspace separation is functional;
- UWF source images remain immutable;
- patient/eye/visit context can be reviewed and stored;
- five-grade physician labeling is supported;
- Core findings can be reviewed, corrected, rejected, and added;
- Advanced findings can be recorded separately without blocking the core workflow;
- review completeness prevents unreviewed absence from becoming negative ground truth;
- raw AI evidence is distinct from physician-confirmed data;
- CFP fallback, if used, shows the required UWF limitation notice;
- manual labeling remains available when AI is unavailable;
- Workspace data can expose stored structured data without database administration access;
- authorized CSV/JSON and training manifests can be exported;
- untouched AI suggestions are excluded from default gold exports;
- Processing details can show the relevant preprocessing/model provenance;
- integrated regression/build/smoke validation passes for the accepted scope;
- all remaining model/clinical limitations are explicitly recorded.

A native UWF model is strongly preferred. If it is not ready at the M1 deadline, the product may be accepted with `CFP_FALLBACK_ACTIVE` only when the owner and reviewing clinicians accept the limitation and the software does not misrepresent the fallback as UWF-validated.

---

## 21. Reference baseline

This plan was prepared from the project's current owner instructions and the supplied project material, including:

- repository `AGENTS.md` and established branch/worktree/integration rules;
- prior M1 planning material;
- current React/FastAPI/Model API architecture;
- current RETFound and PRISM-DR integration boundary;
- DR Screening meeting notes dated 2026-09-24;
- ICO Guidelines for Diabetic Eye Care (2017 update), used as a clinical-reference baseline rather than a frozen project taxonomy;
- the supplied UWF model-selection research report;
- current Colab experimentation for grading, lesion localization, and longitudinal work.

Where clinical taxonomy, acceptance thresholds, model rights, or local-hospital performance remain uncertain, the project must record the uncertainty and obtain the appropriate owner/clinical decision rather than inventing one.

---

# End of M1 Master Plan
