# DR Screening M1 — Phase 2.1 UX Hardening & Server Connection

**Document revision:** Execution r1.0<br>
**Prepared:** 2026-10-01<br>
**Document status:** `OWNER_DIRECTED_EXECUTION_SPEC`<br>
**Parent milestone:** M1 — Labeling System<br>
**Parent phase:** Phase 2 — UWF Labeling Workflow<br>
**Current Phase 2 state:** `READY_FOR_REVIEW` — technical implementation/reviews passed; Owner UAT found workflow/UX changes required before `DONE`<br>
**Repository baseline for this plan:** `bb380e3f9acd470400e26a5ed96915c2c478801c` (`main` / `origin/main`)<br>
**Primary repository:** `siriponsri/dr-support-screening-poc`<br>
**Normative parents:** `AGENTS.md`, `DESIGN.md`, `docs/milestone/m1/M1_MASTER_PLAN.md`, `docs/milestone/m1/M1_PHASE2_UWF_LABELING.md`<br>
**Phase 3 status:** `NOT_STARTED`

> Phase 2.1 is a bounded owner-UAT hardening pass. It does not reopen completed Phase 2 engineering work broadly. It improves clinician usability, makes masked-analysis review understandable, reduces unnecessary controls, and proves the workstation can connect safely to the Model API server. Model qualification, production readiness, real-hospital-data authorization, and clinical validity remain outside this phase unless explicitly approved.

---

## 1. Why Phase 2.1 exists

Phase 2 reached `READY_FOR_REVIEW` with passing technical validation and independent Chunk A/Chunk B reviews. Owner UAT on the real workstation then identified usability issues that matter to the M1 product goal:

- Worklist status text is too dense and can collide with adjacent columns.
- Clinician grading exposes exception actions too prominently and increases cognitive load.
- The grade UI does not yet provide a compact 0–4 clinical reference.
- Annotation editing exposes more geometry/tools than the normal M1 labeling task needs.
- Completeness controls are difficult to understand and add visible state-management burden.
- Masked Analysis can report `NEEDS_REVIEW` without giving the user a clear visual mask-QA surface.
- Explainability / Processing / AI controls are split across multiple layers and feel duplicated.
- Some “next action” guidance can contradict the actual workflow position.
- AI-unavailable states occupy too much UI space even though manual review is the intended fallback.
- The current flow can be reduced for both novice staff and expert ophthalmologists.

These are not reasons to discard Phase 2. They are reasons for a focused Phase 2.1 hardening pass before owner closeout.

---

## 2. Product objective

Phase 2.1 should make the M1 workstation:

1. **understandable by first-time and non-expert operators** for the tasks they are permitted to perform;
2. **fast for expert ophthalmologists** reviewing many images under time pressure;
3. **image-first and clinically calm**, with one obvious primary action at a time;
4. **progressively disclosed**, so uncommon exceptions and technical details do not dominate the normal path;
5. **truthful about AI and processing**, with no hidden fallback or fabricated evidence;
6. **compatible with existing Phase 1/2 persistence, provenance, coordinate, and audit contracts**;
7. **ready to connect to the Model API server safely**, without prematurely declaring models clinically qualified.

### 2.1 Target interaction principle

Do not create a separate “Simple mode / Expert mode” toggle.

Use **progressive disclosure**:

```text
Everyone sees:
current task
retinal image
one primary action
one next step

Reveal only when needed:
exceptions
AI evidence
advanced findings
processing provenance
technical details
```

For expert speed, prefer keyboard shortcuts, remembered reviewer identity, remembered last finding class, auto-advance where safe, and fewer page transitions.

---

## 3. Scope boundaries

### In scope

- Worklist density and status presentation.
- Review / clinician-grade usability.
- Grade reference/help.
- Annotation editor simplification.
- Box-first Core finding workflow.
- Completeness interaction simplification without weakening stored semantics.
- Masked-analysis / mask-QA visualization.
- Case-local AI / Explainability / Processing information architecture.
- Removal of duplicated controls and misleading next-action copy.
- AI-unavailable/manual-path simplification.
- Responsive layout and accessibility for changed surfaces.
- Focused automated regression tests.
- Owner UAT after the patch.
- Model API server connectivity and workstation connection smoke.
- Failure-state testing for server unavailable / not ready / unauthorized.
- Documentation/evidence updates.

### Explicitly out of scope

- Real hospital-data use or authorization.
- Production deployment.
- Autonomous diagnosis/referral logic.
- DME/treatment recommendations.
- New clinical grade semantics.
- New model training/retraining.
- Declaring NB01/USPEC or PRISM clinically validated.
- Enabling a UWF model solely to make the UI appear complete.
- Full Advanced-finding taxonomy redesign.
- Removing legacy annotation geometry from persisted contracts.
- Phase 4 export-negative policy.
- Full M2 role/permission implementation.

---

# 4. P0 — Required before Phase 2 owner closeout

P0 items are owner-UAT blockers or acceptance-critical usability defects. They must be completed before Phase 2 can be considered `DONE`.

## P2.1-P0-1 — Worklist review column hardening

### Problem

The current Review cell can show long text such as:

```text
Review complete
DR grade confirmed · Annotations confirmed
```

This can crowd adjacent columns and reduces scanability.

### Required outcome

Use a compact visual contract, for example:

```text
Complete
Grade ✓ · Findings ✓
```

or an equivalent compact representation.

Requirements:

- fixed/minimum sensible Review column width;
- no overlap with Action;
- long explanatory text moves to tooltip/details rather than primary row;
- status remains explicit and accessible;
- pending, grade-confirmed, second-review, ungradable, excluded, and complete states remain distinguishable;
- table remains usable at supported laptop widths.

---

## P2.1-P0-2 — Correct misleading “Next action” guidance

### Problem

Owner UAT observed `Next action: Confirm image` while already inside Clinician Review / Annotation Editor, including after a DR grade had been confirmed.

### Required outcome

Separate **workflow next step** from **context warnings**.

Example:

```text
Workflow:
Grade complete → Review findings → Finish case

Context:
Patient link incomplete
```

Rules:

- never tell the user to go backward as the “next action” unless backward action is truly required;
- unresolved patient/eye/context information may remain visible, but label it as context/status rather than the next workflow step;
- after grade confirmation, the next workflow instruction should point toward findings/finish;
- after case completion, guidance should point to the next case/worklist.

---

## P2.1-P0-3 — Simplify DR grade decision

### Current issue

Normal grade confirmation competes visually with:

- Mark Ungradable
- Request Second Review

Those are important states, but they are exception paths.

### Required normal path

```text
Final DR grade          Grade guide ⓘ
[ 2 · Moderate NPDR ▼ ]

                       [ Confirm grade ]

Can't finalize this case ▾
```

Under `Can't finalize this case` expose:

- Image is not gradable
- Needs another review

Exact UI control may be popover/menu/disclosure if accessible.

### Grade guide

Provide a compact, accessible popover/drawer using the owner-approved
`docs/reference/ICO_DR_GRADING_0_4_REFERENCE.md` wording:

| Grade | Name | Short description |
|---|---|---|
| 0 | No apparent DR | No apparent diabetic-retinopathy abnormality on the reviewed image |
| 1 | Mild NPDR | Microaneurysms only |
| 2 | Moderate NPDR | More than microaneurysms only, but less than Severe NPDR |
| 3 | Severe NPDR | No proliferative signs, plus at least one ICO 4-2-1 criterion: >=20 intraretinal hemorrhages in each of 4 quadrants, definite venous beading in 2 quadrants, or IRMA in 1 quadrant |
| 4 | Proliferative DR (PDR) | Proliferative disease with neovascularization and/or vitreous or preretinal hemorrhage |

Requirements:

- descriptive name is primary; numeric value is secondary;
- any one Grade 3 lesion-distribution threshold is sufficient; do not require all three;
- `Ungradable` and `Needs Second Review` remain workflow states outside 0-4;
- DME remains a separate classification from DR grade;
- no new referral or treatment semantics;
- no unapproved clinical threshold is invented;
- keyboard navigation is preserved;
- normal grade confirmation remains the fastest route.

Optional expert shortcuts may include `0–4` to select and `Enter` to confirm when safe and conflict-free.

---

## P2.1-P0-4 — Box-first annotation workflow

### Owner direction

For normal M1 lesion labeling, make **rectangle/box** the primary drawing geometry.

### Required UI

Primary toolbar should be approximately:

```text
Select | Draw box | Finding class | Undo | Delete
```

Requirements:

- `Select` and `Box` are first-class visible tools;
- Polygon / Point / Circle are hidden from normal workflow under `More tools`, feature flag, or equivalent;
- do **not** delete legacy geometry support from backend/persistence;
- existing saved non-rectangle annotations must remain readable;
- AI box correction remains possible;
- stored coordinates remain in original-image pixels.

### Finding class safety

Do not allow an unnoticed default class to create accidental labels.

Preferred behavior:

```text
Finding class: Choose finding…
```

or clearly retain/indicate the last active class.

Core classes remain:

- Microaneurysm
- Hemorrhage
- Hard exudate
- Soft exudate / cotton-wool spot baseline per existing contract

No Advanced class is invented.

---

## P2.1-P0-5 — Simplify completeness interaction

### Problem

Visible Core/Advanced completeness state controls create cognitive load and make the editor feel like a state-management form.

### Required direction

Move completeness capture to the natural **Finish case** boundary.

Example:

```text
Finish case

Core findings review
○ Findings reviewed and recorded
○ Reviewed — none found
○ Not finished yet

Advanced findings
Skip for now
```

Rules:

- `REVIEWED_NONE_FOUND` still requires deliberate reviewer action;
- empty AI output or zero annotations must never auto-create a negative;
- `NOT_REVIEWED`, `PARTIALLY_REVIEWED`, `REVIEWED_NONE_FOUND`, and `REVIEWED_FINDINGS_RECORDED` remain representable in persistence;
- Advanced remains optional/collapsed and may remain partial/deferred;
- Phase 4 still owns export-negative eligibility.

---

## P2.1-P0-6 — Make Masked Analysis / mask QA inspectable

### Problem

The UI can show:

```text
Masked Analysis needs review
```

while not providing a clear visual way to inspect the candidate masked representation.

### Required review modes

For UWF cases, provide a clear case viewer with:

```text
Original | Analysis area | Mask overlay | AI evidence
```

Names may be refined, but semantics must remain explicit.

#### Original

Immutable source image.

#### Analysis area

The selected application-level derived representation that will feed the downstream processing chain if/when accepted.

#### Mask overlay

Show the Original image with the proposed valid-retina mask visually overlaid so the user can distinguish:

- retained retinal area;
- excluded border/artifact area;
- uncertain/fallback state.

A `NEEDS_REVIEW` candidate may be visually inspected but **must not silently become approved model input**.

### Required behavior

- preserve original bytes/hash;
- never imply mask coverage = clinical gradability;
- expose candidate mask when safe for inspection even before `READY`;
- make failure/fallback explicit;
- if a mask/transform/hash mismatch exists, fail closed;
- store/display representation version and relevant provenance;
- do not silently change provider-specific preprocessing.

### Terminology

Prefer **Analysis area** rather than always calling this the final “Model input”, because a provider may still perform resize/crop/normalization later.

Truthful chain:

```text
Original
→ Analysis area
→ provider transform
→ actual model input
→ model output
```

---

## P2.1-P0-7 — Consolidate AI-unavailable UI

### Problem

When UWF AI is unavailable, the page can show multiple empty/negative cards:

- Analysis
- DR assessment: Not analyzed
- Lesion suggestions: Not analyzed

### Required outcome

When no qualified AI capability exists, collapse this into one compact state:

```text
AI assistance
Unavailable for UWF in this configuration.
Manual review remains available.
```

Do not render empty assessment/suggestion panels unless there is actual evidence or a specific action the user can take.

Manual clinical review must remain immediately available.

---

## P2.1-P0-8 — Remove duplicated viewer controls

Examples of current duplication include:

- `Show AI suggestions` switch plus `AI Overlay` control;
- repeated Original controls in some UWF states;
- separate information surfaces that communicate the same availability state.

Required outcome:

- one control per concept;
- stable viewer mode selection;
- retinal image remains the dominant object;
- no control row should feel like a dashboard;
- preserve zoom, fit, coordinate inspector, fullscreen, pan, and original-coordinate overlay contracts.

---

## P2.1-P0-9 — Case-local Explainability / Processing inspector

Explainability is case-specific evidence. It should not become a global product destination beside Worklist/Datasets.

Preferred information architecture:

```text
Case viewer:
Original | Analysis area | AI overlay | Explainability

Case-local inspector:
Decision
AI evidence
Processing details ▾
Technical details ▾
```

Requirements:

- Explainability remains distinct from Processing;
- model attention is not presented as validated lesion localization;
- unavailable explanation is explicit;
- image should not disappear merely to show a paragraph if evidence is unavailable;
- raw hashes, representation IDs, internal enum names, and technical model metadata should be progressively disclosed rather than dominate the clinician surface.

---

# 5. P1 — High-value workflow refinement

P1 items materially improve efficiency and professionalism but may be deferred only if they would significantly destabilize the bounded closeout.

## P2.1-P1-1 — Reduce page transitions

Evaluate whether Review + Clinician Review can be safely presented as one coherent **Review & Grade** surface without changing persistence semantics.

Target journey:

```text
Worklist
→ Review & Grade
→ Findings
→ Next case
```

Do not merge pages merely for code aesthetics. Merge only if it reduces clinician time and keeps the interaction clear.

---

## P2.1-P1-2 — Expert speed layer

Where safe:

- numeric 0–4 grade shortcuts;
- Enter to confirm;
- remember reviewer identity;
- remember last selected finding class;
- auto-focus expected next field;
- auto-advance after successful finish;
- preserve keyboard-first operation.

Never make shortcuts the only way to complete a task.

---

## P2.1-P1-3 — Role-aware progressive disclosure foundation

Phase 2.1 does not implement M2 RBAC, but the UI should avoid assuming every user is an expert ophthalmologist.

Design surfaces so future roles can limit capabilities cleanly:

- assistant/nurse: context, capture, image quality, worklist;
- trained reviewer: bounded labeling tasks;
- ophthalmologist: final DR grade, adjudication, expert review;
- technical/operator: Processing / Models & Audit.

Do not weaken physician authority or let explanatory help imply that a non-authorized user should make final clinical decisions.

---

## P2.1-P1-4 — Clean clinician-facing terminology

Primary clinician UI should avoid raw internal strings where a human label exists.

Examples:

```text
WORKSPACE_INPUT
→ Workspace image

raw SHA/image ID
→ Technical details

representation_version
→ Processing details
```

Internal values remain available for audit/debug.

---

## P2.1-P1-5 — Responsive density and visual cleanup

Apply `DESIGN.md` rather than introducing a new visual system.

Focus on:

- fewer competing cards;
- clearer hierarchy;
- smaller amount of persistent explanatory copy;
- aligned columns;
- no text overflow;
- one primary action per step;
- image-first layout;
- clear focus states;
- readable touch targets;
- professional, low-noise clinical appearance.

---

# 6. Server connection — Model API connectivity without premature model qualification

After P0 is stable and P1 changes are integrated as appropriate, prove the review workstation can connect to the intended Model API service.

This is **connectivity/readiness**, not approval of model clinical validity.

## 6.1 Architecture

```text
Windows review workstation
APP_PROFILE=review
MODEL_RUNTIME=remote
PostgreSQL authoritative store
        |
        | REMOTE_MODEL_URL
        v
Controlled Linux NVIDIA GPU host
APP_PROFILE=model_api
MODEL_RUNTIME=local
verified assets
```

The workstation must not load production model weights locally in normal review mode.

---

## 6.2 Server-side preflight

On the designated Model API host:

```bash
cd /opt/dr-support-screening-poc
./scripts/model-server/setup.sh
./scripts/model-server/start.sh
./scripts/model-server/healthcheck.sh
```

Before using the service for evidence display, require the service health contract expected by the repository and verify the asset state required by the current server documentation.

Do not commit weights, tokens, or server credentials.

---

## 6.3 Workstation connection

In the private workstation `.env`:

```text
REMOTE_MODEL_URL=<approved Model API base URL>
REMOTE_MODEL_TOKEN=<private token if required>
```

Then restart the workstation with the supported launcher.

Never print the token/DSN in receipts.

---

## 6.4 Capability truthfulness

Connection success does **not** mean a model is approved for UWF.

The client must use declared capability/model metadata and preserve domain warnings.

For UWF:

- if no qualified UWF capability is enabled, remain manual-only;
- do not route to CFP models silently;
- do not fabricate model evidence;
- do not turn server connectivity into a clinical-validity claim.

A CFP fallback may only be displayed when the existing guarded contract permits it and the required limitation is visible, equivalent to:

> CFP-trained AI · Not validated for UWF

Phase 3 still owns model bundle/runtime/security/qualification decisions.

---

## 6.5 Connectivity smoke

Verify at minimum:

### Healthy server

- workstation can reach the configured server;
- model status loads;
- capability metadata is visible to the app;
- manual review remains usable;
- returned evidence preserves provenance.

### Server unavailable

- UI shows a concise unavailable state;
- manual grade/annotation continues;
- no fake result is synthesized.

### Unauthorized / wrong token

- connection fails clearly;
- token is not echoed;
- manual path remains usable.

### Timeout / not ready

- bounded failure;
- no UI hang;
- no silent fallback to unqualified model;
- retry behavior remains safe.

### UWF with no qualified model

Expected:

```text
AI assistance unavailable for UWF
Manual review available
```

This is a PASS state, not a failure, until Phase 3 qualifies a UWF provider.

---

# 7. Target end-to-end user journey

## Normal expert path

```text
Worklist
→ open case
→ confirm image/context only when needed
→ inspect Original / Analysis area
→ choose final DR grade
→ Confirm grade
→ review/correct/add Core boxes only as needed
→ Finish case
→ next case
```

## Exception paths

Reveal only when needed:

```text
Can't finalize:
- Image not gradable
- Needs another review

AI:
- unavailable
- unsupported
- error
- explanation unavailable

Advanced:
- optional
- deferred
```

---

# 8. Validation strategy

Do not reopen broad Phase 2 review.

Use focused validation for changed surfaces, then one integrated Phase 2.1 review.

Expected focused coverage includes:

- Worklist Review column layout/status.
- Correct Next Action behavior.
- Grade guide and exception disclosure.
- Grade persistence unchanged.
- Box-first annotation controls.
- Legacy geometry remains readable.
- Completeness transitions.
- Mask candidate visual inspection.
- Analysis-area / mask-overlay state handling.
- AI unavailable consolidation.
- Explainability/Processing separation.
- Model API unavailable/timeout/unauthorized handling.
- Server-connected metadata/provenance path.
- accessibility/keyboard behavior for changed controls.

Before owner closeout run applicable repository validation:

```text
python -m pytest -q
python -m ruff check dr_support tests
frontend: npm test
frontend: npm run typecheck
frontend: npm run build
root/app smoke as applicable
git diff --check
```

Do not repeatedly rerun full suites after every small UI adjustment.

---

# 9. Review policy

Phase 2.1 is one bounded Owner-UAT patch, not a new broad phase ceremony.

Use:

```text
MAIN
→ bounded IMPLEMENT
→ focused tests
→ one independent REVIEW of exact Phase 2.1 candidate
→ bounded required fixes
→ affected re-review only
→ integrate
→ final validation
→ Owner UAT
```

Classify findings:

- `BLOCKER`
- `REQUIRED FIX`
- `NON-BLOCKING / DEFER`

Do not reopen Phase 1 or accepted Phase 2 Chunk A/B findings without concrete regression evidence.

---

# 10. Acceptance gates

## Gate A — P0 UX hardening

Pass when:

- Worklist statuses do not overlap.
- Next-action guidance is contextually correct.
- Normal grading path is minimal.
- Ungradable / second review are progressive-disclosure exceptions.
- Grade guide is available.
- Annotation primary UI is Box-first.
- Completeness is captured deliberately without dominating the editor.
- Mask candidate can be visually inspected.
- duplicate viewer controls are removed.
- AI-unavailable UI is compact.
- Explainability/Processing information architecture is understandable.

## Gate B — P1 refinement

Pass when implemented items improve flow without weakening contracts. Any intentionally deferred P1 item must be documented and non-blocking.

## Gate C — Server connectivity

Pass when:

- workstation connects to an approved Model API test server;
- capability/model metadata round-trip works;
- secrets are not exposed;
- server failure does not block manual review;
- UWF remains manual-only unless a qualified capability exists;
- no clinical-validity claim is implied by connectivity alone.

## Gate D — Owner UAT

Owner reviews the real workstation and decides:

```text
APPROVE
APPROVE WITH NON-BLOCKING NOTES
CHANGES REQUIRED
```

Only owner approval may close Phase 2 / Phase 2.1 as `DONE`.

---

# 11. Evidence receipt

MAIN should return a concise receipt.

```text
Repository start SHA:
Phase 2.1 candidate SHA:
Final main SHA:

P0:
Worklist:
Next action:
Grade UX:
Grade guide:
Annotation tools:
Completeness:
Mask QA:
AI unavailable:
Explainability/Processing:

P1:
Implemented:
Deferred:

Server:
Model API target class:
health:
capability metadata:
UWF behavior:
failure-path smoke:
secret-safety:

Validation:
backend:
Ruff:
frontend tests:
typecheck:
build:
app smoke:
git diff --check:
independent review:

Owner UAT:
PENDING / APPROVED / CHANGES REQUIRED

Git:
main == origin/main:
clean:
worktree/branch cleanup:
Brain:
```

---

# 12. Handoff after Phase 2.1

If Owner UAT approves:

1. update Phase 2.1 evidence;
2. update Phase 2 tracker/decision log as owner-approved `DONE`;
3. update Project Brain;
4. keep deferred P1/Advanced items explicit;
5. preserve the Model API connectivity receipt;
6. then allow Phase 3 to begin model qualification.

Phase 3 remains responsible for:

- NB01/USPEC UWF grading qualification;
- PRISM/UWF localization validity;
- provider-specific preprocessing/output qualification;
- model bundle/checkpoint identity;
- runtime/security readiness;
- model-domain/clinical claims;
- production model enablement.

**Do not treat successful server connection as successful Phase 3 qualification.**

# End of M1 Phase 2.1 Execution Specification
