# DR Screening — Milestone 1 Master Plan

**Document path in repository:** `docs/milestone/m1/M1_MASTER_PLAN.md`  
**Document revision:** Closeout r2.7 (Phase 2 owner-approved closeout)
**Prepared:** 2026-09-29
**Document status:** `OWNER_APPROVED_CLOSEOUT`
**Implementation status:** Phase 1 `DONE` (owner-approved on 2026-09-29; independent O1 technical review accepted) and Phase 2 `DONE` (owner-approved on 2026-10-03 after UAT; independent O1 review/self-audit and final integrated evidence accepted); see the phase tracker, which is independent of later-phase authorization.
**Source baseline commit:** `20726efcb8aa6ce857eb9b8537810fea5175b42e`
**Research evidence:** package `DR_M1_DELIVERY_20260928_r1/` (`ASSET_LOCK.json`, `EVIDENCE.md`, `PACKAGE_PREPARATION_REPORT.md`); these are package artifacts, not repository-relative links.  
**Owner decisions pending:** Phase 0 scope freeze, clinical taxonomy/completeness rubric, model-use/rights and operational acceptance thresholds; unresolved optional items follow the Phase 2 safe-defer boundary in §24.
**Primary repository:** `siriponsri/dr-support-screening-poc`  

**Current reading guide (closeout r2.7):** §§2–9 and accepted ADRs state the target contracts; §§10 and 14 are phase/tracker requirements, not proof of completion. The §6.1 examples and original §15 status rows record the 2026-09-25 planning baseline; the current-evidence table distinguishes research assets from repository integration and runtime. Phase 1 §20/§21 provider-specific transcripts are historical only. The current execution roles are in Phase 1 §13. Package research is evidence, not authority to amend a frozen clinical/API contract. Owner approved Phase 1 `DONE` on 2026-09-29 and Phase 2 `DONE` on 2026-10-03 based on the recorded implementation/evidence, accepted UAT, independent O1 review/self-audit, and final integrated implementation SHA `bde3e673169fa6de2f1ecee6373c22c7d46a04de`. Phase 3 remains `NOT_STARTED`; this does not authorize production, hospital-data use, or clinical/model semantic changes.

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

M1 is an **AI-assisted UWF retinal labeling and review workstation** that helps ophthalmologists review the hospital's existing diabetic-retinopathy image collection and produce high-quality, traceable labels for later model development. **M1 is a Labeling System, not the final Clinical Screening System.** The same clinician UI, provenance contracts and model boundary should be designed so they can be extended in M2, where hospital-domain models and separately approved screening/referral behavior may be introduced without rebuilding the workstation from scratch.

The primary product value of M1 is not merely to display model predictions. It is to convert an existing, incompletely labeled hospital image collection into a structured, physician-reviewed dataset while making the physician's limited labeling time as productive as possible. M1 must not present an AI grade, lesion proposal, attention map or longitudinal comparison as an autonomous screening decision.

The intended M1 workflow is:

```text
Workspace
→ ingest retinal images
→ resolve patient / eye / visit evidence
→ prepare a versioned masked/analysis representation without changing the source image
→ obtain available AI suggestions and explanation evidence
→ physician reviews the original image, masked analysis image, AI overlay and explainability evidence
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
- model/preprocessing provenance;
- model explanation evidence and its interpretation limits.

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
| separate state | Needs Second Review (active unresolved review state) |

The system may later derive coarser labels, such as `DR` versus `NO_DR`, from a physician-confirmed grade. The derived label must not replace or destroy the original grade.

`Ungradable` is used when the image does not support a reliable severity assignment. `Needs Second Review` is used when the image is reviewable but the physician does not finalize one of the five grades. Historical `Unknown / not yet determined` records remain readable for backward compatibility, but the active clinician UI must distinguish untouched/not-yet-reviewed cases from deliberate second-review escalation.

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

Phase 2 may persist these states as deliberate review evidence without freezing the full training-negative policy. Phase 4 owns export eligibility; an empty group or `REVIEWED_NONE_FOUND` state must not be promoted to a training negative by Phase 2 alone.

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

The UI may provide side-by-side comparison and physician change labeling when useful. **Three distinct levels require separate evidence:** same-eye images may be displayed side by side with date/order `UNKNOWN` and no before/after or improvement/worsening claim; chronological comparison requires supported acquisition ordering; learned change/risk requires a separately qualified model and clinical protocol. The owner/clinical reviewer must approve the allowed label and action at each level (`PENDING_OWNER`); a visit ordinal does not establish chronology.

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

## 5. UWF preprocessing, masked analysis representation and artifact handling

Hospital UWF images may contain machine borders, eyelashes/lids, glare, reflection, or other non-retinal structures. Existing CFP-oriented models may incorrectly treat these as image evidence.

M1 should therefore maintain two distinct concepts:

1. **Original image** — the immutable source shown to the physician.
2. **Masked analysis representation** — a derived, versioned image that may mask regions considered invalid for AI analysis and that can be inspected by the physician when AI is used.

The masked analysis representation is a **shared representation contract** for model adapters, not a lesion-only preprocessing trick. Grading and lesion providers may apply different model-specific transforms after this shared stage, but neither may silently create an additional incompatible mask or double-mask the image without a versioned, reviewed contract and regression evidence.

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

### 5.3 Explainability Panel

M1 should provide a clinician-facing **Explainability Panel** that is distinct from Processing details. Its purpose is to show what AI evidence contributed to a suggestion, not to expose implementation logs. Where the selected provider supports it, the panel may show:

- grading class scores and a patch/attention overlay from the preferred UWF grader;
- lesion proposals, class, score/fold-agreement or uncertainty evidence and `review_boxes`;
- model/domain limitations and unavailable/error states.

A grading attention map must be labeled as **model attention/evidence, not validated lesion localization**. Explanation evidence remains AI provenance and must never become a physician annotation or gold lesion label automatically. The panel must degrade safely when a provider does not expose explanation evidence.

### 5.4 Processing Details surface

M1 should include a secondary, non-primary-flow surface named **Processing details**. Phase 2 owns a case-level inspection sufficient to see source, selected processing stages, mask/fallback, transform and model/domain warning during review; Phase 4 owns a read-only workspace-level filtered/detail/JSON and export inspection using those recorded versions. Approved clinical group semantics introduced after Phase 1 are owned by the introducing phase, including any additive payload/schema migration; Phase 1 owns the reusable migration infrastructure and compatibility baseline.

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

1. **Preferred UWF path:** qualify and integrate the current UWF research candidates, with **NB01/USPEC grading as the preferred M1 grading candidate** and UWF-compatible localization pursued separately.
2. **Temporary fallback/comparator path:** when the preferred capability is not ready, retain existing CFP-based RETFound and PRISM-DR assistance only under explicit clinician-facing limitations and the existing approval gates.

RETFound is therefore retained as a historical comparator/temporary fallback, not as a co-primary UWF grader. Selecting NB01/USPEC as the preferred direction does **not** itself prove checkpoint integrity, runtime compatibility, clinical performance, rights or production readiness. The fallback exists to keep physician labeling productive and must not be reported as UWF validation.

### 6.1 Preferred UWF model work

Model experimentation/training may proceed in parallel with repository development.

The current preferred grading research path is **NB01: USPEC encoder + RGB 7×7 patch/MIL grading head**, using the versioned masked analysis representation. The selected inference artifact is the trained `grading_state.pt` bundle after qualification. `USPEC_weights.pth` is the pretrained/base encoder asset used for training or future retraining, not the normal inference artifact; an optimizer-bearing `latest.pt`, when present in the training workspace, is a same-run resume checkpoint rather than the deployed model identity. DINOv3 RGB remains a controlled research comparator unless a later owner decision changes the preferred candidate.

The lesion path remains separately qualified. The current PRISM bundle is CFP-domain (`NOT_VALIDATED_FOR_UWF`) and may only be used under its assistive limitation until a UWF-capable localization model is established. NB03 remains a longitudinal review/comparison scaffold; it does not establish a learned progression model.

The model-development direction from M1 to M2 is:

```text
qualified model version
→ AI-assisted physician labeling in M1
→ physician-confirmed, versioned dataset snapshot
→ separately authorized new training/fine-tuning run
→ new model version with parent checkpoint + dataset/split + metrics + artifact hash
→ evaluation/promotion decision
```

M1 must create the data and provenance needed for that loop, but it must not perform automatic/online learning from newly saved hospital labels or overwrite an enabled model in place. Hospital-domain fine-tuning is a separately authorized training activity and is expected to become a principal M2 model-development path.

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

The system must not silently change RETFound/PRISM metadata from CFP to UWF merely to enable the route. At the pinned commit, `dr_support/services/model_api.py` currently returns `UNSUPPORTED` for UWF input on the CFP providers; the owner-directed temporary assistive fallback is a **required target**, not evidence that the current route already enables it. Phase 3 P3-4 must propose/review any guarded contract change.

### 6.3 Mandatory physician-facing fallback notice

When a CFP-based model is shown on a UWF case, the primary review page must show a concise notice near the AI result.

Recommended English UI copy:

> **CFP-trained AI — this bundle is not validated for UWF.** This bundle was trained for conventional color fundus photographs. Review the full UWF image and confirm, correct, or reject each suggestion.

A shorter badge may be used in dense UI:

> **CFP-trained AI · Not validated for UWF**

The primary notice and the Processing details domain/validation metadata must agree with the selected bundle manifest. For the prepared PRISM bundle, show `model_domain=CFP` and `validation_status=NOT_VALIDATED_FOR_UWF`; this wording is bundle-specific, not a claim about every historical PRISM release. Phase 2 P2-7, Phase 3 P3-4/6 and Phase 5 P5-4 verify visibility in both surfaces. Final clinician-facing copy remains subject to clinical-owner review, without weakening the manifest meaning.

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

**Status:** `DONE` (owner-approved 2026-09-29; independent O1 technical review accepted; final documentation closeout is bounded to this administrative update)
**Start date:** 2026-09-25
**Completion date:** 2026-09-29
**Reviewed by:** Owner approval on 2026-09-29; independent O1 technical review run `e1859e9890d24166b682f2b429fa4ed2` accepted the exact candidate.
**Evidence / commit(s):** Owner-reviewed implementation/evidence baseline `b912f43ca9f5fe31bfb5ff0cac0672e746beca3c`; O1-reviewed candidate `a1da89c5b90c2e32d432ee863f79d8db70fde0c4`; P1-F foundation at `b63126ae989109e380ef9bdeb6d425c49eb96cec`; final documentation closeout commit is recorded in Project Brain after push; current validation evidence is in `docs/milestone/m1/M1_PHASE1_POSTGRES.md`.
**Migration evidence:** Isolated synthetic PostgreSQL 16.15, schema v1->v4; one workspace and one case imported; revision 4/content preserved; identical rerun idempotent; changed source rejected with exit 2; SQLite sources remained read-only.
**Fresh migration receipt:** snapshot `phase1-synthetic-receipt-20260929`; source-set SHA-256 `6674d63f93d00396826e61796b8659a5cc692d2bda5395c8923f4a9b9dd966d2`; catalog SHA-256 `a903f9fb9b5bdce0a4b98f0249c52e99fc3ddc26be32079c588e107762fd4158`; one orphan reported inventory-only.
**Dry-run result: safe_to_proceed=true.** The successful dry-run caused no destructive source/target mutation; SQLite source bytes remained unchanged and no target data was deleted, truncated, or recreated.
**Restore evidence:** 10,950-byte custom dump restored into a clean isolated target with one workspace, one case, one receipt, and verified revision/content; restored application selected PostgreSQL storage.
**Accepted limitations:** Root legacy UI smoke lacks the ten public HRF samples required by its documented environment prerequisite; documentation QA reports the pre-existing missing `docs/README.md`; the post-merge backend run did not use a designated PostgreSQL DSN while the designated-DSN receipt remains recorded; two optional NumPy-dependent DICOM/S5 tests remain skipped; existing React warnings and the frontend large-chunk warning remain. These do not block this owner-approved Phase 1 closeout.
**Owner decisions:** Owner approved P1-A, P1-B, P1-I, the recorded PostgreSQL qualification/restore evidence, and the public/synthetic-only Phase 1 boundary on 2026-09-29. No hospital-data inference/export, production deployment, clinical/model semantic change, or Phase 2 implementation is authorized by this closeout.

---

# Phase 2 — UWF Labeling Workflow

## Goal

Make the clinician workflow efficient for repeated UWF labeling while maximizing the amount and quality of physician-confirmed information captured per review session.

**Entry and dependency (2026-09-29):** Phase 1 is `DONE` under the owner-approved public/synthetic evidence boundary. Phase 2 implementation began under the owner-directed start instruction and completed bounded Chunk A and Chunk B work. Native UWF model readiness, hospital inference/export authorization, production deployment, retraining, referral/DME logic, and autonomous clinical claims are not Phase 2 entry dependencies or permissions.

## Required work

1. Preserve the established viewer and general visual direction.
2. Improve UWF intake/review behavior without treating UWF as CFP.
3. Implement or harden the shared valid-retina/masked-analysis representation, safe failure states, and clinician inspection of the masked image used for AI.
4. Improve patient/eye/visit evidence extraction and confirmation.
5. Provide efficient DR grade confirmation/editing using descriptive five-grade labels, separate `Ungradable` and `Needs Second Review` states, and disagreement-safe persistence.
6. Provide **Core findings** annotation workflow.
7. Provide **Advanced findings** as a separate optional section/tab/surface.
8. Record annotation-group completeness.
9. Preserve AI versus human provenance at per-finding level.
10. Support reject/correct/add/confirm actions.
11. Ensure original-image coordinates remain authoritative for stored findings.
12. Ensure manual labeling remains available when AI is unavailable.
13. Add a distinct **Explainability Panel** for available model evidence and a concise clinician-facing CFP-fallback notice when fallback models are used on UWF.

## Acceptance criteria

A physician can:

- open a UWF image;
- confirm patient/eye/visit context;
- see the original image without destructive modification;
- inspect the selected masked/analysis representation when AI processing is used;
- see available AI evidence and Explainability Panel with correct model-domain warning;
- set or correct DR grade;
- use descriptive five-grade labels without relying on numeric codes;
- route reviewable unresolved cases to `Needs Second Review` rather than an ambiguous active-UI `Unknown` state;
- preserve independent reviewer decisions and adjudication state when final grades disagree;
- accept/correct/reject suggested core findings;
- add new core findings;
- optionally review/add Advanced findings;
- explicitly indicate whether a finding group was reviewed;
- save and reopen the case;
- continue labeling even if the Model API is unavailable.

## Phase 2 execution and review policy

Implementation is organized into two substantive review gates:

- **Chunk A — Core UWF Review Foundation:** P2-1 through P2-4 and P2-7, including intake/context, low-burden grade review, shared processing representation, viewer/evidence states, and manual/failure behavior.
- **Chunk B — Findings & Completeness:** P2-5 and P2-6, including Core/Advanced findings, provenance, completeness, persistence, and any required disagreement/adjudication worklist state.

Each chunk receives one independent substantive review of the exact candidate. O1 or O2 may review when read-only and independent from MAIN/IMPLEMENT. Final integration/main validation follows both chunk reviews. Findings are classified as `BLOCKER`, `REQUIRED FIX`, or `NON-BLOCKING / DEFER`; closed findings are not reopened without regression evidence. Routine implementation choices remain with MAIN/IMPLEMENT. Optional clinical/model capabilities use explicit unavailable/deferred/manual-only states rather than blocking unrelated Core work.

## Phase 2 status tracker

**Status:** `DONE`
**Specification:** Execution r3.0 adopted 2026-09-29; Chunk A and Chunk B implementation integrated; owner UAT and formal closeout accepted 2026-10-03
**Start date:** 2026-10-01
**Completion date:** 2026-10-03  
**Reviewed by:** Independent O1 Chunk A review PASS; independent O1 Chunk B review PASS; final integration review by MAIN
**Evidence / commit(s):** Chunk A `6bfa7825da7175694373e6b3661abc7d53d7d5f7`; Chunk B `6c33255741b1b43a42b1474a05a3db6cfcbce021`; integrated main `5b300f70d8ab6a5433d2066d24a8706fe044a696`; final integrated implementation `bde3e673169fa6de2f1ecee6373c22c7d46a04de`. The full pre-closeout validation, self-audit, independent review, and UAT evidence remains recorded below and in the Phase 2 closeout documents.
**Clinical feedback:** Owner accepted the Phase 2 UAT on 2026-10-03 and authorized formal closeout. Unresolved Advanced taxonomy/geometry remains explicitly deferred.
**Open blockers:** None for the accepted Phase 2 scope. Accepted limitations and deferred UX observations remain recorded below; they do not reopen Phase 2.
**Owner decisions:** Owner approved Phase 2 `DONE` on 2026-10-03. This does not authorize production/clinical deployment, real hospital-data use, native UWF model qualification, live Model API success, Phase 3 start, or Phase 4 export-policy approval.

**2026-10-03 final closeout candidate evidence (pre-owner decision):** Candidate `732cad50cf47cf89afa337f5cab5081f57f6aa33` is integrated in main at `ea329f400c6ed55f4ab5c8dc6c832da78f1969ed` and was ready for owner closeout from baseline `dded17ee035464255b77a3206ccb00b6068db60a`. Resolver refresh, one-action Core Finish/retry locking, structured API errors, compact reviewer identity, image-first responsive layout, documentation alignment, and the no-negative audit are recorded in the Phase 2 receipt. Full main validation passed: backend `213 passed, 28 skipped, 50 warnings`; Ruff PASS; frontend `19 files / 121 tests PASS`; typecheck PASS; build PASS with the existing large-chunk warning; and `git diff --check` PASS. Source docs QA passed for 88 sources from the bounded feature worktree; the authoritative outer-main invocation reports only the preserved nested `main/` worktree's duplicate generated PDFs as a workspace-layout limitation. Root legacy smoke overlay/API checks passed, but its runner could not start because the final audit feature-worktree `.venv` was unavailable (`KNOWN ENVIRONMENT LIMITATION`). PostgreSQL persistence/restart validation recorded `8 passed, 26 skipped` because no designated PostgreSQL DSN/server was available. Chrome audit evidence covered 1366, 1024 and 800 pixels with no horizontal overflow, Lighthouse accessibility/best-practices `100/100`, AI-off completion, and restart preservation; 1920-pixel visual inspection was not run. Independent configured O1 changed-diff review PASS; reviewer account independence remained unverified. Phase 2 was then `READY_FOR_REVIEW`; Phase 3 remained `NOT_STARTED`; owner UAT was `READY`.

**2026-10-03 formal Phase 2 closeout:** Owner accepted the Phase 2 UAT and authorized formal closeout. Phase 2 is now `DONE` at final integrated implementation SHA `bde3e673169fa6de2f1ecee6373c22c7d46a04de`; the accepted independent O1 changed-diff review and MAIN self-audit remain the evidence for the exact candidate. Accepted limitations are: the feature-worktree `.venv` was unavailable in the final audit environment; no PostgreSQL DSN/server was available for that final audit run; the 1920px audit was not run; reviewer account independence remains unverified; the legacy root-smoke limitation remains historical evidence and is not a fabricated PASS; and live Model API success remains deferred to Phase 3. The owner also accepted these NON-BLOCKING / DEFERRED TO PRE-PHASE-3 UX observations without reopening Phase 2: compress the Annotation Editor toolbar toward one row with compact popover/progressive disclosure for secondary tools, and replace the implementation-oriented `Record partial review` wording in a future UX pass by deriving completeness from clinical actions. Phase 3 remains `NOT_STARTED`.

---

# Phase 3 — AI Models & Model API Integration

## Goal

Provide the best available AI assistance without blocking the labeling workflow or overstating model validity.

## Workstreams

### Phase 3G — Grading

Preferred outcome:

- qualify and integrate the **NB01/USPEC UWF grading bundle** as the preferred M1 grading candidate, with explicit grade output, reproducible local inference identity and optional patch-attention explanation evidence.

Temporary fallback when the preferred candidate is not ready:

- RETFound may be retained as a CFP-based comparator/assistive fallback with the mandatory UWF limitation notice; it is not the preferred UWF grading path.

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
- artifact/checkpoint identity where applicable;
- explanation-evidence type/version and interpretation warning where applicable.

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
10. Add distinct **Processing details** and **Explainability evidence** surfaces: provenance/debug chain in Processing details; model attention/scores/localized AI evidence in Explainability, never silently converted to gold labels.
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
→ generate or skip the selected masked/analysis representation
→ inspect masked image used for AI
→ run available AI assistance
→ display correct native/fallback model status and explanation evidence when supported
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
| 1 | Data Foundation & PostgreSQL | `DONE` | Owner-approved implementation/evidence baseline `b912f43ca9f5fe31bfb5ff0cac0672e746beca3c`; detailed receipt in `docs/milestone/m1/M1_PHASE1_POSTGRES.md` | Public/synthetic-only scope; accepted UI/documentation validation limitations remain; Phase 2 not started |
| 2 | UWF Labeling Workflow | `DONE` | Chunk A `6bfa782`; Chunk B `6c33255`; final integrated implementation `bde3e67`; full validation, accepted UAT, and limitations recorded in §10 | Owner-approved 2026-10-03; Advanced taxonomy/geometry and native UWF model capabilities remain safely deferred |
| 3 | AI Models & Model API Integration | `NOT_STARTED` |  | Native UWF work may use explicit CFP fallback temporarily |
| 4 | Dataset & Review Tools | `NOT_STARTED` |  |  |
| 5 | End-to-End Validation & M1 Review | `NOT_STARTED` |  |  |

---

## 15. Model capability tracker

The original rows below are **2026-09-25 target/integration planning statuses**, retained for traceability. `NOT_STARTED` there does not mean research assets do not exist and does not assert that a fallback is deployed. Use the current-evidence table immediately after those rows to plan next work.

| Capability | Preferred target | Current deployment mode | Status | Limitation / evidence |
|---|---|---|---|---|
| DR grading | NB01/USPEC UWF grading candidate | TBD | `NOT_STARTED` | Preferred direction selected; RETFound retained only as comparator/temporary CFP fallback with explicit UWF warning |
| Core lesion localization | Native UWF model | TBD | `NOT_STARTED` | CFP PRISM-DR fallback allowed only with explicit UWF warning |
| Advanced finding localization | Per-class UWF capability where feasible | Manual + future AI | `NOT_STARTED` | Never claim unsupported classes are automatically detected |
| Longitudinal change | Optional learned same-eye model | Disabled until ready | `NOT_STARTED` | Comparison/data capture may proceed without model |

**Current evidence at pinned commit and Step 2 package (r2; not deployment approval):**

| Capability | Research evidence | Asset/byte state | Repository integration | Target runtime / clinical / rights |
|---|---|---|---|---|
| NB01/USPEC UWF grading | Aggregate internal research test only | Drive/package metadata identify `grading_state.pt` as the trained inference bundle and `USPEC_weights.pth` as a retraining/base asset; implementation environment still must independently verify selected bytes/hash | Exported bundle not shown integrated into Bridge v1; current adapter computes MIL attention but the API does not yet expose it as a versioned explanation field | Load/L4/offline/clinical untested; production rights `UNVERIFIED`; preferred direction is not readiness approval |
| PRISM CFP lesion | `custom_provisional_v3`, not official PRISM evaluation | 21/21 checkpoints and 3/3 adapter/config byte-verified; current adapter loads 20 specialists, not ROI cropper | Exported bundle not shown integrated into Bridge v1 | Load/L4/offline untested; `NOT_VALIDATED_FOR_UWF` |
| Existing repository CFP providers | ADR-0002 Bridge v1 paths/profiles in source | No Step 2 runtime receipt for deployed provider | Current code exists; current UWF route behavior must be checked, not inferred from fallback policy | Deployment/clinical status not established; preserve explicit limitation and manual workflow |
| Longitudinal learned model | No qualified candidate in package | None claimed | No selected learned integration | `DISABLED` pending identity/date, model and clinical gate |

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
| 2026-09-28 | M1 is the physician Labeling System; M2 is the later Clinical Screening System. | Preserve the current UI/data/model boundary for extension into M2 without treating M1 AI output as autonomous screening/referral. | Owner-confirmed |
| 2026-09-28 | NB01/USPEC is the preferred M1 UWF grading direction; RETFound remains comparator/temporary fallback only until NB01 passes its gates. | Align grading with the UWF research path and allow future hospital-domain fine-tuning without discarding the M1 workstation. | Owner-confirmed |
| 2026-09-28 | Masked analysis image and Explainability Panel are first-class review surfaces, separate from Processing details. | Let physicians inspect what image the model saw and what evidence it used while preserving the distinction between attention, lesion localization and provenance. | Owner-confirmed |
| 2026-09-28 | Physician-confirmed M1 snapshots may seed later NB01 fine-tuning only through separately authorized, versioned training runs. | Prevent online/self-training contamination and in-place model mutation; preserve parent checkpoint, dataset/split, metrics and artifact identity for M2. | Owner-confirmed |
| 2026-09-29 | Phase 1 is `DONE`; Phase 2 enters from the completed persistence foundation but remains `NOT_STARTED` until implementation is explicitly started. | Establish the Phase 2 dependency and prevent document adoption from being mistaken for implementation authorization. | Owner-directed |
| 2026-09-29 | Phase 2 uses a low-burden descriptive five-grade workflow; `Ungradable` is separate, and active unresolved review uses `Needs Second Review` while historical `Unknown` remains backward-compatible. | Improve physician speed and label consistency without treating non-grade states as grades or silently changing historical records. | Owner-directed |
| 2026-09-29 | Independent reviewer disagreement preserves both decisions, marks an adjudication/second-review state, and excludes the unresolved grade from training-ready status; two reviews are not required for every image. | Protect review provenance while keeping ordinary labeling low burden. | Owner-directed |
| 2026-09-29 | Phase 2 uses Chunk A and Chunk B substantive review gates followed by final integration validation; O1 or O2 may provide independent read-only review, and optional unresolved clinical/model capabilities are safely deferred. | Reduce review burden, preserve independence, and keep unrelated Core workflow moving without weakening safety contracts. | Owner-directed |
| 2026-10-01 | Phase 2 completed bounded Chunk A and Chunk B implementation and independent review. Chunk A covered intake, named grading, disagreement-safe persistence, shared analysis representation, viewer/evidence states, and manual failure paths; Chunk B added persisted Core/Advanced completeness with reviewer/time/taxonomy provenance and explicit no-negative behavior. | Record actual implementation evidence without claiming native UWF model qualification, full Advanced taxonomy, production readiness, or Phase 2 owner closeout. | Owner-directed execution; O1 reviews accepted |
| 2026-10-03 | Owner accepted the integrated Phase 2 UAT and authorized formal Phase 2 closeout as `DONE` at final integrated implementation SHA `bde3e673169fa6de2f1ecee6373c22c7d46a04de`. | Close Phase 2 while preserving accepted limitations and deferred Pre-Phase-3 UX items; Phase 3 remains `NOT_STARTED` and later clinical/model/export permissions remain separate. | Owner-approved |

---

## 17. Open clinical decisions

These items should be asked when they become necessary for a phase. Do not block unrelated engineering work prematurely.

### Grading

- Confirm the grading rubric used by the participating ophthalmologists.
- Confirm handling of treated/stable PDR images.
- Confirm edge-case handling around `Ungradable` and `Needs Second Review`; retain historical `Unknown` only for backward-compatible records, not as the active unresolved UI choice.
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
- the physician can inspect the masked/analysis image used for AI;
- an Explainability Panel can show supported model evidence with clear interpretation limits and explicit unavailable state;
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

## 22. Candidate rebaseline and current versus target (2026-09-28)

This closeout preserves §§1–21, including the historical Phase 0 and Phase 1 trackers and decision log. The two baseline documents were read at the pinned commit; package research is separately dated evidence, not a repository revision or clinical authorization. Owner approved Phase 1 `DONE` on 2026-09-29 based on the recorded repository evidence and independent O1 technical review. Historical test counts and the Phase 1 worker transcript remain historical evidence, not new tests run during this documentation closeout. The historical Phase 1 suggested `/goal` is preserved as an audit record, not a current provider/account instruction.

| Area | Current implementation or evidence at pinned commit | Required target / accountable work |
|---|---|---|
| Persistence | Owner-approved baseline `b912f43ca9f5fe31bfb5ff0cac0672e746beca3c` provides PostgreSQL-authoritative managed review/case and workspace/catalog paths, legacy SQLite read-only migration, and documented live synthetic qualification; exact evidence is in `M1_PHASE1_POSTGRES.md`. | Phase 1 is closed as `DONE`; any later clinical/schema/export extension requires a new owner-reviewed phase instruction. |
| Intake/review | Existing admission, resolver, workflow and UI milestones; image, grade and annotation confirmations are separate (`docs/adr/0004-three-human-confirmation-milestones.md`). | Phase 2 adds efficient UWF manual workflow and clinically approved per-group completeness without converting case-level annotation confirmation into individual AI ROI confirmation. |
| Source origin / permission (B01) | `dr_support/services/admission.py` currently creates workspace `BridgeImage` with `source_type="PUBLIC"`; `workflow.py` has a `PUBLIC` fallback. Bridge v1 `contracts/_schema.py`/`services/model_api.py` accept only `PUBLIC`/`SYNTHETIC`; `providers/remote.py` forwards the image value. These are pinned-source observations, not a hospital runtime test. | Owner/data steward approves a truthful authorized-hospital provenance/permission contract and migration/Bridge compatibility. P2-1 owns intake identity, P1-A durable baseline, P3-4 wire/result mapping, P4-3 export lineage and P5-1/3/5 integrated authorization checks. Do not classify hospital images as public/synthetic solely to satisfy the current schema. |
| Dataset | Existing `s4.dataset-manifest.v2` and `s8.2-task-specific-v1` grade/lesion readiness in `docs/reference/DATASET_MANIFEST.md`. | Phase 4 preserves compatibility and adds read-only inspection, snapshot reproducibility and approved completeness semantics. |
| Model API | ADR-0002 Bridge v1: `/health`, `/v1/models`, `/v1/predict/dr`, `/v1/predict/lesions`; review/remote and CUDA model_api/local profiles. | Phase 3 qualifies bundles and negotiates any explicit, reviewed contract changes. The deployment prototype's `/predict:8000` does not override current routes/port (`PORT=7860` in repository profile). |
| Research | 21/21 PRISM checkpoints and 3/3 adapter/config entries byte-verified. NB01 `grading_state.pt` remains external to the delivery package; the Drive object has been located at the expected size, but implementation has not independently verified its bytes/hash or loaded it. | Phase 3 separately establishes observed hash, runtime, integration, hardware, domain, rights and clinical gates. Drive/package metadata alone supplies none of these later gates. |

Phase 0 tracker remains `NOT_STARTED` in the historical master. Source gate, package preparation, source inspection and this candidate reconciliation supply evidence toward its inventory; they do **not** prove the owner scope freeze or close Phase 0. Owner to reconcile tracker after reviewing this candidate. No later phase is automatically authorized by drafting its specification.

## 23. Shared cross-phase contracts and gates

This section is the cross-phase reference for [Phase 1](M1_PHASE1_POSTGRES.md), [Phase 2](M1_PHASE2_UWF_LABELING.md), [Phase 3](M1_PHASE3_MODELS_MODEL_API.md), [Phase 4](M1_PHASE4_DATASET_REVIEW_EXPORT.md), and [Phase 5](M1_PHASE5_E2E_VALIDATION.md). §§2–9, accepted ADRs, `AGENTS.md`, `DESIGN.md` and approved clinical contracts remain in force. A proposal below cannot silently amend them.

1. **Identity and source:** human-selected approved top-level workspace input, immutable original bytes and SHA-256, confirmed pseudonymous patient/eye/visit evidence, acquisition date distinct from visit ordinal; do not infer source authority from orphaned SQLite or hospital folder names. Source origin, permission/authorization and retinal modality are separate dimensions. Current Bridge v1 represents `source_type` only as `PUBLIC`/`SYNTHETIC`; deidentification or pseudonymization does not make hospital data public. The hospital contract and allowed path are `PENDING_OWNER`/data-steward review before hospital inference or export; synthetic/public engineering can proceed. Provenance must remain truthful across admission, remote request/result, persistence and export. `docs/adr/0003-immutable-source-and-separate-analysis-derivative.md`, `docs/adr/0006-human-selected-image-intake-boundary.md`; P1-A/P1-B, P2-1/P2-2, P3-4, P4-1/P4-3, P5-1/P5-3.
2. **Coordinates and representations:** original-image pixels are authoritative for geometry; display and analysis derivatives carry transform identity, source and derivative hashes, mask/preprocessing version and reversible mapping. Overlay must be checked against original pixels. Phase 2 owns the representation contract; Phase 3 tests adapter compatibility and maps outputs; Phase 5 verifies round trips. Neither mask coverage nor an all-true fallback is clinical gradability. `docs/adr/0003-immutable-source-and-separate-analysis-derivative.md`; P2-3/P2-4, P3-2/P3-4, P5-2.
3. **Human authority:** distinct Confirm Image, Confirm DR Grade and Confirm Annotation milestones; case-level annotation confirmation and set hash do not individually confirm AI ROIs. An untouched, rejected or unreviewed AI suggestion is never a gold label. The grade and lesion readiness policies are independent; empty confirmed active set is reviewed but not proof of no lesion. Future group/class states `NOT_REVIEWED`, `PARTIALLY_REVIEWED`, `REVIEWED_NONE_FOUND`, `REVIEWED_FINDINGS_RECORDED` require an approved rubric and additive migration; they must not be inferred from box count. `docs/adr/0004-three-human-confirmation-milestones.md`, `docs/adr/0005-task-specific-dataset-readiness.md`, `docs/reference/DATASET_MANIFEST.md`; P1-A, P2-5/P2-6, P4-2/P4-3, P5-3.
4. **Clinical/model domain:** UWF is the target image domain; grade 0–4 with separate `Ungradable` and active `Needs Second Review` states, while historical `Unknown` remains backward-compatible; DR-vs-NO_DR derivation preserves grade; DME/referral are independent and need clinical approval. Core MA/HE/EX/SE and Advanced candidate taxonomy are §3 scope, not a frozen clinical ontology. NB01/USPEC is the preferred UWF grading candidate but production rights remain `UNVERIFIED`; RETFound is comparator/temporary fallback rather than the preferred UWF path. PRISM remains CFP, `NOT_VALIDATED_FOR_UWF`, and `custom_provisional_v3` is not official PRISM evaluation. MIL attention is explanation evidence, not validated lesion localization. CFP assistive fallback on UWF requires explicit domain notice and review; it is not UWF validation. P2-4/P2-5, P3-1/P3-3/P3-4/P3-5, P5-2/P5-4.
5. **Failure and privacy:** model unavailable/error/unsupported is explicit and does not synthesize grade 0 or empty findings. Manual review and audited save continue without inference. Access, least privilege, export minimization, no patient-level package evidence; source files and credentials do not enter repository planning overlay. P1-I, P2-7, P3-4, P4-4, P5-5.
6. **Provenance and export:** persist model/bundle/checkpoint and processing identities, raw suggestion versus human action, reviewer/time, revision/audit and taxonomy/schema/policy versions. Read-only Workspace data and reproducible exports must agree with PostgreSQL; keep patient grouping key but do not create automatic split. P1-A/P1-I, P2-6, P3-4, P4-1/P4-3, P5-3.

**Dependency order:** P1-F → P1-A/P1-B → P1-I and persistence gate; Phase 2 manual intake/review can be specified and fixture-tested without a real GPU but its integrated persistence acceptance needs Phase 1. Phase 3 research qualification proceeds independently, while bundle integration depends on the Phase 2 representation/coordinate contract. Phase 4 export depends on confirmed Phase 1 persistence and Phase 2 human semantics, not Phase 3 model availability. Phase 5 exercises one integrated build after the relevant gates; no demo-specific substitute. Phase 2 and Phase 3 agree on the preprocessing contract before production behavior changes. Later gate outcomes remain provisional.

**Phase entry/exit:** Phase 0 owner reconciles scope/decisions; Phase 1 exit requires PostgreSQL migration/restore and ledger approval; Phase 2 exit requires manual save/reopen, reviewed finding semantics and overlay evidence; Phase 3 exit is reported per capability and may leave models disabled; Phase 4 exit requires DB/UI/export and contamination evidence; Phase 5 review requires integrated commit, product/persistence/export/operational results and separate model/clinical conclusions. An engineering E2E pass does not authorize clinical use or production deployment.

## 24. Decisions and limitations pending owner review

| Decision / evidence | Affected work and blocked claim | Work possible now / closure |
|---|---|---|
| Phase 0 tracker `NOT_STARTED`; inventory/package evidence does not freeze scope | Phase 0 closure and new plan approval | Review candidate and record owner scope decision; bounded research/manual design can be evaluated. |
| Advanced taxonomy, group-level reviewed-negative rubric, visit date provenance, referral/DME definitions (§§3, 17; ADR-0004/0006) | P2-2/P2-5, P4-2, clinical labels/export rule | Preserve existing three milestones and `s8.2-task-specific-v1`; implement only truthful supported semantics, defer unresolved classes/negative-export authority, and continue unrelated Core work. |
| NB04 `border_component_v1` then adapter v4, untested coordinate/input equivalence (package report) | P2-3/P2-4 and P3-2 acceptance | Compare both paths with consented/synthetic fixtures; owner approves any behavior-changing selection. |
| NB01 grading checkpoint is external to the delivery package; Drive object located but independent observed hash/load receipt still absent. USPEC rights `UNVERIFIED`; PRISM CFP `NOT_VALIDATED_FOR_UWF` despite 21/21 byte checks | Grading load/promotion and production rights; UWF PRISM clinical claims | Manual labeling and planning proceed. Independently verify/hash/load the selected NB01 bundle, obtain rights proof and separate runtime/clinical evidence. |
| Version mismatch and no L4/offline receipt; NB03 review-only, NB04 latest executed receipt absent | P3-1/P3-3/P3-5 and deployment decisions | Inventory and test isolated target environments, then decide pins/service topology; no fabricated thresholds. |
| Prototype route `/predict:8000` conflicts with current ADR-0002 Bridge v1 | P3-4 interface adoption | Current API remains; any migration requires owner-reviewed compatibility and tests. |
| Hospital-origin contract absent from `PUBLIC`/`SYNTHETIC` Bridge v1 (B01) | Hospital Model API and export authorization; synthetic/public fixture work proceeds | Data steward/owner approves origin/permission representation and Bridge/persistence/export contract; P2-1/P3-4/P4-3/P5-3/5 prove lineage. No false relabeling. |
| Selected checkpoint loader/runtime security applicability (B02) not qualified | Initial deserialization/model-enabled readiness; manual work proceeds | P3-1/3 security owner checks selected build, artifact source and loader path against primary advisory before load, then compatibility after remediation if needed; P5-4 checks receipt. |

The supplied `07-physical-deployment.png` image's **whole-diagram approval status is UNKNOWN**. Its physical QA/PRD host, VLAN, NVIDIA L4, `/data/models` and promotion details are component-level proposals/requirements to reconcile with the owner; the extracted deployment **code** is marked prototype and its `/predict:8000` interface does not replace ADR-0002 Bridge v1. Phase 1's owner-approved local-development/AWS RDS UAT PostgreSQL decision remains intact; it can coexist with a hospital-local model host. Record separate approval provenance for DB, application host, model host/network and promotion before release (Phase 3 P3-5, Phase 5 P5-5; `PENDING_OWNER`). Meeting transcription is unverified discussion, not an approved clinical rubric. No patient data, model runtime, clinical validation, deployment or application tests were used to author this candidate.

## 25. Candidate change log and next handoff

2026-09-28 r1: preserved the baseline sections, work-item history and status tracker; corrected document path and added candidate status, pinned provenance, current/target matrix, shared contracts, dependencies, owner decisions and links to the detailed Phase 2–5 candidates. See the corresponding candidate report in the working package (`candidate-r2.1/M1_PLAN_RECONCILIATION_REPORT.md`) for r2.1 changes/hashes; r1 and r2 remain untouched. 2026-09-28 r2: resolved static reviewer comments in §§3.6, 5, 6.1, 6.3, 15 and deployment authority in §24; clinical/deployment decisions remain pending. The attached ChatGPT static document review is separate from an O2/runtime review and owner approval. Candidate r2.1 (2026-09-28) adds B01 source-origin and B02 loader-security gates to §§22–24 without changing prior research/clinical statuses. Candidate r2.2 records the owner's clarified product direction: M1 is the Labeling System that is extended in M2 into a Clinical Screening System; NB01/USPEC is the preferred UWF grading candidate, RETFound becomes comparator/temporary fallback, the masked analysis image and a distinct Explainability Panel are first-class review surfaces, and later hospital-domain fine-tuning must use versioned physician-confirmed snapshots in separately authorized runs rather than online/in-place learning. No model runtime, clinical validation or hospital-data training was performed to make this documentation change. On review, reconcile Phase 0 and Phase 1 ledger against a fresh implementation baseline before authorizing bounded work; do not treat this candidate as automatic execution approval. 2026-09-29 closeout r2.4: owner approved Phase 1 `DONE` on the public/synthetic evidence boundary after accepting the recorded P1-A/P1-B/P1-I, validation, and limitation receipts; independent O1 review remains the technical review record. Phase 2 is not started and requires a new owner instruction. 2026-09-29 r2.5: adopted the owner-directed Phase 2 Execution r3.0 specification at the synchronized 20726ef baseline. Phase 2 remains `NOT_STARTED`; implementation uses Chunk A and Chunk B reviews followed by final integration, with low-burden named grading, safe disagreement/adjudication, and explicit safe-defer boundaries.

# End of M1 Master Plan
