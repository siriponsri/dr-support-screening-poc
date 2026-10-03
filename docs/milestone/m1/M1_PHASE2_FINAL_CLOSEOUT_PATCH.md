# DR Screening M1 — Phase 2 Final Closeout Patch

**Document revision:** Final Closeout Patch r1.0  
**Prepared:** 2026-10-03  
**Status:** `OWNER_DIRECTED_FINAL_PHASE2_PATCH`  
**Repository:** `siriponsri/dr-support-screening-poc`  
**Audited baseline:** `dded17ee035464255b77a3206ccb00b6068db60a`  
**Current Phase 2 state:** `DONE` (owner-approved 2026-10-03)  
**Current Phase 3 state:** `NOT_STARTED`  
**Owner closeout:** `APPROVED`  

**Normative parents, in priority order:**

1. `AGENTS.md`
2. `DESIGN.md`
3. `docs/milestone/m1/M1_MASTER_PLAN.md`
4. `docs/milestone/m1/M1_PHASE2_UWF_LABELING.md`
5. `docs/milestone/m1/M1_PHASE2_1_UX_HARDENING_SERVER_CONNECTION.md`
6. prior Phase 2.1 owner-UAT patch documents
7. accepted ADRs and current clinician/developer documentation

> This document is the final bounded implementation and self-audit patch for Phase 2. It does not start Phase 3, does not authorize real hospital-data use, does not qualify a model, and does not authorize production deployment. Its purpose is to remove the remaining Phase 2 workflow, persistence, usability, and closeout gaps so the owner can perform one final focused UAT and decide whether to mark Phase 2 `DONE`.

---

# 1. Audit scope

This patch was prepared after a fresh repository review at:

```text
dded17ee035464255b77a3206ccb00b6068db60a
Merge branch 'fix/m1-phase2-1-owner-uat-operation-simplification'
```

The audit covered the current Phase 2 workflow end-to-end and the files/contracts that directly affect owner UAT and closeout, including:

```text
AGENTS.md
DESIGN.md
README.md

docs/milestone/m1/M1_MASTER_PLAN.md
docs/milestone/m1/M1_PHASE2_UWF_LABELING.md
docs/milestone/m1/M1_PHASE2_1_UX_HARDENING_SERVER_CONNECTION.md
docs/milestone/m1/M1_PHASE2_1_OWNER_UAT_UX_PATCH.md
docs/milestone/m1/M1_PHASE2_1_OWNER_UAT_OPERATION_SIMPLIFICATION_PATCH.md
docs/milestone/m1/M1_PHASE4_DATASET_REVIEW_EXPORT.md

docs/adr/0004-three-human-confirmation-milestones.md
docs/adr/0005-task-specific-dataset-readiness.md
docs/reference/DATASET_MANIFEST.md
docs/release/RELEASE_CHECKLIST.md

docs/clinician/USER_WORKFLOW.md
docs/clinician/FEATURE_REFERENCE.md
docs/manuals/clinician/02-workflow.qmd
docs/manuals/clinician/05-annotations.qmd
docs/manuals/clinician/07-confirm-annotation.qmd
docs/manuals/developer/07-review-state.qmd

dr_support/workflow.py
dr_support/store.py
dr_support/services/resolver.py
dr_support/services/dataset.py
dr_support/persistence/cases.py

frontend/src/lib/api.ts
frontend/src/lib/caseProgress.ts
frontend/src/components/common/NextActionHint.tsx
frontend/src/components/common/ReviewerField.tsx
frontend/src/components/worklist/ConfirmImageDialog.tsx
frontend/src/components/worklist/ReviewStatusCell.tsx
frontend/src/components/worklist/WorklistTable.tsx
frontend/src/pages/WorklistPage.tsx
frontend/src/pages/ReviewPage.tsx
frontend/src/pages/ClinicianReviewPage.tsx
frontend/src/pages/AnnotationEditorPage.tsx

frontend/tests/annotationEditor.test.tsx
frontend/tests/singleLineFlow.test.tsx
frontend/tests/phase2_1Ux.test.tsx
frontend/tests/uwfIntake.test.tsx
tests/test_resolver.py
tests/test_uwf_intake.py
tests/test_workflow.py
tests/test_dataset.py
tests/ui.test.cjs
```

No outside clinical/model semantics are introduced by this patch.

---

# 2. Product intent for final Phase 2

Phase 2 is a **high-volume physician-led labeling workflow**, not a technical state-management console.

The intended user may be:

- an ophthalmologist reviewing many images;
- a trained clinical reviewer;
- a nurse/assistant resolving basic intake context;
- a future M2 clinical user who should not need to understand the implementation.

The normal case path should require very little interpretation:

```text
Worklist
→ confirm only unresolved image context
→ inspect Original / processing evidence if useful
→ confirm DR grade
→ review/correct/add Core findings if needed
→ one deliberate Finish action
→ next case
```

The user should **not** have to:

- understand internal enum names;
- manage review-state transitions manually;
- choose processing thresholds;
- fill metadata already derivable by the system;
- click two or three controls to express one clinical completion decision;
- learn why a request failed from `[object Object]`;
- scroll through large blank areas caused by page composition.

The system should do clerical work and preserve provenance automatically.

---

# 3. Non-negotiable Phase 2 invariants

All implementation decisions must preserve these contracts.

## 3.1 Human authority

- Final DR grade is human-confirmed.
- AI suggestions remain optional evidence.
- Untouched AI suggestions never become human labels.
- A corrected AI ROI retains original AI provenance separately.
- A human correction never inherits the original model score as if it applied to the correction.

## 3.2 Source and geometry

- Original source image remains immutable.
- Stored spatial findings remain in original-image pixels.
- Existing zoom/pan/fullscreen/coordinate behavior remains unchanged.
- Legacy polygon/point/circle persistence remains readable even though Box is the normal visible tool.

## 3.3 Completeness

The approved Phase 2 states remain:

```text
NOT_REVIEWED
PARTIALLY_REVIEWED
REVIEWED_NONE_FOUND
REVIEWED_FINDINGS_RECORDED
```

Do not infer completeness from:

- AI box count;
- empty AI output;
- empty annotation array;
- opening a panel;
- case-level annotation confirmation alone.

`REVIEWED_NONE_FOUND` is review-completeness evidence only. Phase 2 does not authorize it as a training/export negative.

## 3.4 Identity and chronology

- Filename parsing provides evidence/suggestions, not clinical truth.
- Manual/confirmed patient or eye values are never silently overwritten.
- Visit/capture ordinal is not automatically chronology.
- `L1/L2` or similar sequence evidence does not automatically mean Before/After.
- Unknown remains valid when evidence is insufficient.

## 3.5 Phase boundaries

Do not:

- start Phase 3;
- qualify USPEC, PRISM, Clef, RETFound, or another model;
- enable an unqualified UWF model;
- add referral/treatment/DME logic;
- authorize hospital-data inference/export;
- change Phase 4 reviewed-negative policy beyond a conservative safety correction described in this document;
- declare production/clinical validation.

---

# 4. Fresh audit findings

## F01 — Legacy unresolved cases can keep stale filename evidence

**Severity:** `REQUIRED FIX`

Current resolver logic supports explicit filename patterns such as:

```text
FC8804 L1.jpg
HN5071 L1.jpg
PAT0001_L1.jpg
```

and current tests prove space-separated `patient + eye + sequence` parsing.

However `workflow.ensure_resolution()` currently returns immediately whenever:

```text
case.resolver_evidence is not None
```

even when:

- the case remains `UNLINKED` / `UNKNOWN`;
- there has been no manual resolution;
- the persisted evidence was generated by an older parser;
- the current parser can now derive a safe patient/laterality candidate.

Owner UAT demonstrated this operationally: an unresolved case such as `HN5071 L1.jpg` can still ask the user to enter Patient and Eye manually even though the current parser supports that pattern.

This defeats the high-volume operation objective.

---

## F02 — Annotation completion still exposes internal state-management work

**Severity:** `REQUIRED FIX`

The current Annotation Editor shows:

```text
Finish this image
  Core findings review
    Reviewed findings recorded
    Reviewed none found
  Status ...
  Advanced findings
    Record partial review
  Reviewer name
  Confirm Annotation
```

The user must understand the difference between:

- Core completeness;
- Advanced completeness;
- annotation-set confirmation;
- case completion.

This is technically explicit but operationally too burdensome.

The Phase 2 specification requires explicit completeness while also requiring low clinician burden. These must be combined into a **single deliberate user completion action**, not presented as multiple internal workflow controls.

---

## F03 — Current case-complete helper does not require completeness

**Severity:** `REQUIRED CONSISTENCY FIX`

`frontend/src/lib/caseProgress.ts` currently defines a completed case as:

```text
grade confirmed
+
annotations confirmed
```

This is acceptable for backward compatibility with existing cases, but the current UI can still perform `CONFIRM_ANNOTATIONS` without selecting a Core completeness state.

Therefore the current visible instruction:

> Choose the review state deliberately at the finish boundary

is not actually enforced by the normal finish operation.

The final Phase 2 UI must guarantee that **new routine finishes record deliberate Core completeness and annotation confirmation from one user action**.

Do **not** retroactively make old confirmed cases incomplete solely because they predate completeness.

---

## F04 — Annotation page layout violates the image-first/high-throughput design intent

**Severity:** `REQUIRED UX FIX`

Current desktop composition is effectively:

```text
LEFT
Retinal annotation canvas

RIGHT
Finish this image
Editor tools
Legend
```

The right column is much taller than the left column. After the canvas ends, the left side becomes a large blank region while Editor tools continue lower on the right.

Problems:

- canvas-related tools are physically separated from the canvas;
- the user may scroll until the image is no longer visible while still editing tools;
- the page feels unfinished and visually unbalanced;
- persistent text such as `Double-click to finish a polygon` describes an advanced geometry even though Box is the normal workflow;
- technical coordinate copy occupies primary clinician-facing space.

This conflicts with `DESIGN.md`, which states:

- the retinal image is the primary clinical object;
- annotation controls should be grouped;
- desktop review may use ~1.35–1.4fr image and ~0.6–0.65fr supporting content;
- information density must serve a decision.

---

## F05 — Reviewer identity is repeated as a full form on every annotation case

**Severity:** `UX REQUIRED / LOW RISK`

The system already supports remembered reviewer identity, but Annotation Editor still presents:

```text
Reviewer name [full input]
[x] Use as default reviewer on this workstation
```

on every case.

For a high-volume session this is redundant visual work.

The normal path should display a compact summary when a default reviewer exists:

```text
Reviewer: Test    Change
```

and expand the input only when needed.

Reviewer default remains a workstation preference, **not authentication**.

---

## F06 — `[object Object]` can reach the clinician UI

**Severity:** `REQUIRED BUG FIX`

Owner UAT showed a red error surface containing:

```text
[object Object]
```

Two current implementation details are relevant:

1. `annotationCompletenessApi.update()` does not use the shared `jsonRequest()` helper, unlike the other JSON mutation APIs.
2. `apiJson()` assumes `body.detail` is a string, while FastAPI validation errors may return structured arrays/objects.

Raw objects must never be rendered as clinician-facing errors.

---

## F07 — Advanced findings controls are present without a meaningful normal advanced workflow

**Severity:** `REQUIRED UX FIX`

Advanced findings are explicitly optional/deferred in the Phase 2 specification.

The current Finish card still exposes:

```text
Advanced findings
→ Record partial review
```

even though this is not part of the normal Core workflow and does not represent a useful clinical completion path by itself.

An unopened Advanced section must remain:

```text
NOT_REVIEWED
```

That is truthful and sufficient.

Do not make clinicians create a `PARTIALLY_REVIEWED` record merely because the control exists.

---

## F08 — Documentation is stale relative to the current low-burden flow

**Severity:** `REQUIRED CLOSEOUT HYGIENE`

Current documentation still tells the user to:

- manually enter patient key/eye in Confirm Image as the normal path;
- use `Confirm Annotation` as a distinct visible workflow step;
- use Box/Polygon/Point/Circle as equally prominent annotation tools;
- operate a `Finish this image` panel whose intended UX is changing in this final patch.

At minimum, update source documentation that directly describes the changed workflow.

Also, the root `README.md` links to:

```text
docs/README.md
```

but that file is currently absent. This has already been reported by documentation QA.

---

## F09 — Dataset readiness must be audited against the no-negative boundary

**Severity:** `MANDATORY AUDIT GATE`, not automatic Phase 4 implementation

Current `services/dataset.py` considers lesion readiness from current annotation confirmation/hash/reviewer/time. Current manifest documentation says an empty active set may be case-level confirmed and `lesion_training_ready=true`, while also warning that this does not prove lesion absence.

The Phase 2 specification additionally states that:

```text
REVIEWED_NONE_FOUND
```

is completeness evidence and Phase 2 alone does not authorize it as a training/export negative.

This final patch must **not silently broaden export eligibility**.

Required closeout behavior:

- no negative annotation/label is created from an empty set or `REVIEWED_NONE_FOUND`;
- untouched AI suggestions remain AI evidence;
- the new Finish action records completeness truthfully;
- Phase 4 remains the owner of reviewed-negative export semantics.

During self-audit, MAIN/REVIEW must inspect whether current `lesion_training_ready` behavior directly violates the owner-approved no-negative boundary. If a safety correction is necessary, the only allowed Phase 2 change is a **conservative tightening** that cannot make additional data eligible. Any change must update tests/docs and clearly state compatibility impact. Do not invent the final Phase 4 negative policy here.

---

## F10 — Known root legacy smoke and docs limitation must be classified honestly

**Severity:** `CLOSEOUT EVIDENCE`

The repository has a known legacy root smoke that expects the historical sample environment and may time out when those samples are not present.

Do not weaken a test merely to create a green result.

For this final patch:

- run it once in the final validation environment;
- if it passes, record PASS;
- if it fails only because the documented HRF/sample prerequisite is absent, record the exact evidence as `KNOWN_BASELINE / NON-BLOCKING`;
- if it fails because this patch changed runtime/API behavior, treat it as `REQUIRED FIX`.

The missing `docs/README.md` is easy documentation debt and should be fixed in this patch unless a repository rule proves otherwise.

---

# 5. Target workflow after this patch

## 5.1 Confirm Image

Normal resolved case:

```text
Confirm image

HN5071 L1.jpg

Image type   Ultra-widefield     confirmed
Patient      HN5071              suggested from filename
Eye          Left                suggested from filename

Reviewer     Test                Change

Additional metadata ▾

[ Confirm image & continue ]
```

Only unresolved items expand into editable controls.

---

## 5.2 Review / Grade

Preserve current accepted behavior:

```text
Review
→ optional Original / Analysis / Mask / AI evidence
→ Continue to clinician review
→ choose DR grade
→ Confirm grade
```

Do not reopen accepted grading/mask UX without concrete regression evidence.

---

## 5.3 Findings

Preferred clinician-facing mental model:

```text
Review findings
→ inspect AI suggestions if present
→ correct/remove/add only when needed
→ Finish image
→ next case
```

The user should not manage completeness states manually.

---

# 6. Required patch work

# P2-FINAL-1 — Refresh safe automatic resolver evidence for unresolved legacy cases

## Goal

Current safe filename parsing should help unresolved historical cases without rewriting manual decisions.

## Required behavior

When a case is loaded/scanned and all of the following are true:

- patient and/or eye remains unresolved/unknown;
- there is no manual resolution that must be preserved;
- there is no prior Confirm Image/manual identity decision that would be overwritten;
- the current resolver can derive stronger supported evidence than the persisted automatic evidence;

then the system may refresh/enrich **automatic evidence only**.

Examples:

```text
HN5071 L1.jpg
→ patient candidate HN5071
→ laterality LEFT
→ capture sequence 1 as evidence only
```

## Must preserve

Never overwrite:

- `patient_resolution_method = MANUAL`;
- `laterality_resolution_method = MANUAL`;
- explicit manual Unknown;
- a previous `MANUAL_RESOLUTION`;
- a previously confirmed patient/eye value;
- contradictory evidence.

## Audit trail

If automatic evidence actually changes, record a compact event such as:

```text
AUTOMATIC_RESOLUTION_REFRESH
```

or another existing-compatible action with:

- timestamp;
- prior automatic state/evidence summary;
- new automatic state/evidence summary;
- method/pattern.

Do not append duplicate events on every GET when nothing changed.

## Parser/version handling

MAIN may implement an explicit parser/evidence version if that is the cleanest compatible method.

The system should be able to distinguish:

```text
old automatic evidence
vs
current automatic evidence
```

without needing destructive migration.

## Acceptance tests

At minimum:

1. `HN5071 L1.jpg` unresolved legacy record → current evidence yields `HN5071`, `LEFT`, sequence 1.
2. Existing manual `RIGHT` eye is not overwritten by filename `L1`.
3. Existing confirmed patient key is not overwritten.
4. Ambiguous/conflicting filename remains Unknown/Needs confirmation.
5. Repeated GET/restart does not append repeated refresh events.
6. Sequence remains evidence, not Before/After chronology.
7. PostgreSQL persistence survives restart.

---

# P2-FINAL-2 — Replace state-management Finish card with one deliberate completion action

## Product rule

The clinician should not choose internal completeness state and then separately confirm annotations.

One user action should represent:

> I have finished reviewing Core findings for this image.

## Normal case with one or more active clinician-recorded Core findings

Display a compact summary:

```text
Complete review

1 finding recorded
Draft saved

Reviewer: Test    Change

[ Finish image & next ]
```

The Finish action must result in:

```text
CORE = REVIEWED_FINDINGS_RECORDED
current annotation set persisted
annotation set confirmed
reviewer/time/audit recorded
case complete
next incomplete image opened
```

This is one user click, even if implementation uses more than one internal persistence operation.

## Normal case with no active Core human finding

Do **not** silently infer a negative from the empty array.

The primary action must itself express the deliberate reviewed-none decision.

Example:

```text
No Core findings recorded

Finishing records that Core findings were reviewed and none were found.

[ Finish — reviewed none found ]
```

That deliberate click results in:

```text
CORE = REVIEWED_NONE_FOUND
annotation set confirmed
reviewer/time/audit recorded
case complete
```

It does not create a negative lesion annotation and does not authorize Phase 4 gold-negative export.

## If the user is not finished

The user simply does not press Finish.

Do not require a `Review in progress` button for the normal path.

A partial state may remain an internal/persisted state where genuinely needed, but it should not be a normal completion choice.

## Existing completed cases

Do not invalidate historical completed cases solely because they predate completeness.

When reopened and edited, the next Finish action should reconcile the current Core completeness truthfully.

## Correctness after edit

Examples:

```text
prior REVIEWED_NONE_FOUND
→ clinician adds a Core finding
→ annotation confirmation invalidated
→ next Finish records REVIEWED_FINDINGS_RECORDED
```

and:

```text
prior REVIEWED_FINDINGS_RECORDED
→ clinician removes all Core human findings
→ annotation confirmation invalidated
→ next Finish requires explicit reviewed-none finish
```

## AI suggestions

Untouched AI suggestions:

- do not become HUMAN;
- do not count as human findings;
- do not force per-ROI confirmation;
- remain preserved in evidence/audit.

## Imported/CVAT findings

Inspect the existing active annotation/hash semantics before deriving the finish summary.

Do not use `draft.length` blindly if another current clinician-reviewed annotation source is active.

If an imported/legacy edge case cannot be mapped truthfully, preserve compatibility and expose a safe explicit choice rather than inventing completeness.

---

# P2-FINAL-3 — Make the completion operation retry-safe

A single user click may internally require:

```text
persist draft
→ record Core completeness
→ confirm current annotation hash
→ navigate
```

Implementation may choose:

- the existing endpoints with a proven retry-safe sequence; or
- a small additive atomic backend operation if this is the smallest safe design.

The spec defines the outcome, not the implementation.

## Required properties

- no navigation until persistence succeeds;
- revision/CAS conflicts produce a reload/retry message;
- network/API failure never displays a false `Case complete`;
- no silent partial finality;
- retry does not corrupt annotation history;
- repeated finish cannot duplicate human annotations;
- current annotation hash is what is confirmed;
- completeness reviewer/time corresponds to the actual finish action.

If sequential existing endpoints are used, tests must prove recovery from a failure between completeness persistence and annotation confirmation.

---

# P2-FINAL-4 — Remove Advanced findings from the normal completion path

Default Core completion must not ask the user to interact with Advanced findings.

Normal state:

```text
ADVANCED = NOT_REVIEWED
```

is valid and truthful.

Remove from the primary Finish card:

```text
Advanced findings
Record partial review
```

unless there is an actual advanced-review workflow being used in that case.

If an advanced entry point remains, put it under secondary progressive disclosure such as:

```text
More review options ▾
```

and make it clear that it is optional/deferred.

Do not invent Advanced negative semantics.

Do not remove backend compatibility for existing Advanced completeness records.

---

# P2-FINAL-5 — Recompose Annotation Editor around the retinal image

## Desktop target

Use the existing two-column design intent, but keep tools with the image.

Preferred composition:

```text
┌─────────────────────────────────────┬──────────────────────┐
│ Findings review                     │ Complete review      │
│                                     │                      │
│ Select | Box | Finding | Undo ...   │ N findings recorded │
│ More tools ▾                        │                      │
│                                     │ Reviewer: Test       │
│          RETINAL IMAGE              │ Change               │
│                                     │                      │
│                                     │ [ Finish & next ]    │
│ viewer/draft status                 │                      │
│ class + provenance legend           │ More options ▾       │
└─────────────────────────────────────┴──────────────────────┘
```

## Left/image column

Place inline annotation controls **with the canvas**, preferably above the stage.

Primary visible controls:

```text
Select
Box
Finding class
Undo
Delete
```

Secondary:

```text
More tools ▾
  Polygon
  Point
  Circle
  Lock/Unlock
```

Visibility toggles may remain compact and accessible.

## Remove persistent advanced-geometry copy

Do not permanently show:

```text
Double-click to finish a polygon
```

when Polygon is not active.

Show geometry-specific help only when that geometry is selected.

## Technical coordinate copy

Keep coordinate-space invariants in:

- viewer status;
- Processing/technical detail;
- developer documentation.

Do not let technical storage wording dominate the normal clinician heading/description.

## Right column

The right column should contain only completion/supporting content needed for the decision.

Do not stack:

```text
Finish
Editor tools
Legend
```

vertically on the right.

The finish/support column should stay compact enough that it does not create a large empty block under the canvas.

## Responsive acceptance

Validate at least:

```text
1920 × 1080
1366 × 768
1024 × 768
< 1024 responsive single-column behavior
```

At supported desktop/laptop widths:

- image stays dominant;
- no giant dead whitespace below the image due solely to a longer right column;
- no horizontal page scrollbar;
- controls do not overlap image or each other;
- Finish remains discoverable.

---

# P2-FINAL-6 — Compact reviewer identity in repeated review

When the workstation already has a default reviewer:

```text
Reviewer: Test    Change
```

is preferred to a full input/checkbox block.

Clicking `Change` may reveal the existing Reviewer field.

When there is no remembered reviewer, show the normal required input.

Preserve:

- existing localStorage preference;
- reviewer attribution in persisted records;
- ability to change reviewer;
- no implication that reviewer name is authentication.

The same compact pattern may be reused in other high-volume surfaces only if it is a small compatible change. Do not broaden this patch into a global form redesign.

---

# P2-FINAL-7 — Fix clinician-facing API error handling

## JSON request consistency

`annotationCompletenessApi.update()` must use the same JSON request contract as other JSON mutations, including appropriate `Content-Type`.

## Error normalization

`apiJson()` or an equivalent shared layer must safely normalize:

```text
detail: "message"
detail: [{loc, msg, type}, ...]
detail: { ... }
no JSON body
```

into concise clinician-facing text.

Never render:

```text
[object Object]
```

Never expose:

- Python repr;
- stack trace;
- raw Pydantic object;
- token/credential content;
- internal DSN/path.

## Suggested behavior

Examples:

```text
Case changed. Reload this image and try again.
Reviewer name is required.
The review state could not be saved. Try again.
```

The exact wording may follow existing product conventions.

## Required tests

- structured FastAPI 422 detail;
- string detail;
- 409 conflict;
- 500/non-JSON fallback;
- completeness request sends JSON correctly;
- error remains local to Finish area and image/editor stays usable.

---

# P2-FINAL-8 — Keep case completion semantics backward compatible

Do not redefine historical completion globally merely to support the new UI.

`caseComplete()` may continue to recognize legacy:

```text
grade confirmed + annotation set confirmed
```

for backward compatibility.

But every **new routine Finish action** after this patch must write deliberate Core completeness before/with annotation confirmation.

This avoids destructive migration while fixing the active workflow.

Add tests that distinguish:

```text
legacy confirmed case → still recognized complete
newly finished case → complete + explicit CORE completeness
edited case → confirmation invalidated; must finish again
```

---

# P2-FINAL-9 — Documentation alignment

Update only documentation affected by the final Phase 2 behavior.

At minimum review/update:

```text
README.md
docs/clinician/USER_WORKFLOW.md
docs/clinician/FEATURE_REFERENCE.md
docs/manuals/clinician/02-workflow.qmd
docs/manuals/clinician/05-annotations.qmd
docs/manuals/clinician/07-confirm-annotation.qmd
docs/manuals/developer/07-review-state.qmd
```

Required documentation changes:

- Confirm Image is progressive-disclosure and can prefill supported filename/source evidence.
- Filename suggestions remain evidence until appropriately confirmed.
- Normal findings workflow is Box-first.
- `Finish image & next` is the third human confirmation in clinician-facing wording.
- Internally, the existing annotation-confirmation milestone/hash semantics remain.
- Finish records Core completeness deliberately.
- No Core findings is an explicit user completion decision, not an empty-array inference.
- Advanced findings remain optional/deferred.
- AI ROI-by-ROI confirmation is not required.
- reviewer default is convenience, not authentication.

## `docs/README.md`

Create the missing documentation portal if it is still absent.

Keep it short and canonical:

```text
Clinician manual
Operator manual
Developer guide
Operations
Reference
Milestone plans
Release checklist
```

Do not duplicate entire manuals.

## Screenshots / generated PDFs

Do not spend Phase 2 implementation time regenerating every PDF unless the existing documentation QA requires it for this gate.

Update source docs and only the screenshots needed for changed Phase 2 workflow evidence.

Full documentation/site/PDF regeneration remains appropriate for later release/Phase 5 unless the owner separately requests it.

---

# P2-FINAL-10 — Dataset/no-negative safety audit

This patch does not implement Phase 4.

MAIN must nevertheless inspect the current interaction between:

```text
CORE completeness
annotation confirmation
lesion_training_ready
annotations.csv
```

and produce an explicit audit conclusion.

Required assertions:

1. `REVIEWED_NONE_FOUND` does not create a negative lesion annotation.
2. An empty AI result is not treated as reviewed-none.
3. An empty human annotation set alone is not automatically converted into Core reviewed-none.
4. Untouched AI rows remain non-human evidence.
5. Any Phase 2 change does not broaden export/training eligibility.

If the existing `lesion_training_ready` flag remains true for a case-level-confirmed empty set, document clearly that this is the pre-existing task-specific readiness baseline and **not** a gold-negative label. Phase 4 owns the final negative policy.

If independent review concludes the current flag directly violates the owner-approved Phase 2 no-negative boundary, MAIN is authorized only to make the narrowest **conservative gating** fix:

```text
may reduce eligibility
must never increase eligibility
```

and must update tests/docs/policy wording accordingly.

Do not invent a reviewed-negative export rule.

---

# 7. Self-audit mandate

This final patch is intentionally different from earlier implementation rounds.

MAIN must not merely implement listed UI changes and stop.

After the first coherent candidate exists, MAIN must perform a **local self-audit of the exact candidate** against this section and fix all in-scope `BLOCKER` and `REQUIRED FIX` findings before requesting independent review.

No owner approval is needed for ordinary implementation corrections inside these boundaries.

Stop and ask the owner only if a proposed fix would change:

- clinical label meaning;
- reviewed-negative/export semantics beyond conservative gating;
- privacy/security policy;
- hospital-data authorization;
- immutable-source/original-coordinate contract;
- production model identity/domain claim;
- Phase 3/4 scope;
- another frozen contract that cannot be preserved compatibly.

---

# 8. Self-audit checklist

## A. Repository / Git gate

Before first write, record:

```text
repo root
worktree path
branch
HEAD
git status --short --branch
```

Implementation must occur in a bounded feature/fix worktree, not application writes directly on `main`.

Expected starting main:

```text
dded17ee035464255b77a3206ccb00b6068db60a
```

If main advanced legitimately, reconcile first and report the new base.

Do not discard unexpected work.

---

## B. Confirm Image audit

Test:

- current unresolved `HN5071 L1.jpg`-style record;
- resolved filename case;
- ambiguous filename;
- manual patient correction;
- manual eye correction;
- explicit manual Unknown;
- restart/reopen;
- rescan;
- repeated read.

Questions:

- Does the system derive safe evidence automatically?
- Does it avoid asking for data it already knows?
- Does it ever overwrite a manual value?
- Does it create duplicate automatic events?
- Does sequence stay separate from chronology?

---

## C. Annotation finish audit

Test at least these cases:

### C1 — one human Core finding

```text
grade confirmed
1 human finding
Finish image & next
```

Expected:

- draft persisted;
- Core = `REVIEWED_FINDINGS_RECORDED`;
- active set hash confirmed;
- one finish action from user;
- next case opens;
- restart preserves all evidence.

### C2 — zero human Core findings

Expected primary action is explicitly reviewed-none.

After click:

- Core = `REVIEWED_NONE_FOUND`;
- annotation set confirmed;
- no fabricated negative annotation;
- next case opens.

### C3 — untouched AI suggestions only

- AI rows remain AI;
- no per-ROI confirmation required;
- finish does not silently promote AI to human;
- reviewed-none wording must be an explicit clinician decision.

### C4 — edited previously complete case

- edit invalidates current annotation confirmation;
- subsequent Finish records completeness matching current active findings;
- no stale confirmed hash.

### C5 — Advanced unopened

- remains `NOT_REVIEWED`;
- does not block Core Finish;
- does not become a negative.

### C6 — failure between internal finish steps

Simulate:

- conflict;
- 422;
- network/server error;
- retry.

No false Case complete message and no corrupt/duplicated state.

---

## D. Layout / visual audit

At supported widths inspect:

- first viewport;
- after one page scroll;
- fullscreen;
- with 0 findings;
- with multiple findings;
- with AI suggestions on/off;
- with selected annotation;
- with More tools opened.

Check:

- image remains dominant;
- tools remain visually associated with canvas;
- Finish card does not dominate the page;
- no giant empty left region;
- no accidental horizontal page scroll;
- no clipped buttons;
- no overlapping controls;
- Box-first remains obvious;
- advanced tools stay secondary;
- lesion/provenance colors remain unchanged;
- human/AI provenance remains distinguishable by more than color.

---

## E. Keyboard/accessibility audit

At minimum:

- Tab order follows visible task order;
- Enter activates safe primary completion where appropriate;
- Escape exits relevant dialogs/modes;
- focus remains visible;
- disabled controls use disabled semantics;
- primary Finish has an accessible name;
- error message is associated/local and human-readable;
- no control depends on color alone;
- full-screen viewer retains keyboard behavior.

---

## F. Persistence / concurrency audit

Use PostgreSQL review mode.

Verify:

- revisions increment correctly;
- stale writer returns conflict;
- finish does not race autosave;
- restart preserves grade, findings, completeness, confirmation hash, reviewer/time;
- same-revision startup enrichment behavior remains safe;
- workspace isolation remains intact.

---

## G. Manual / AI-off audit

With Model API unavailable:

```text
Confirm image
→ Review Original
→ grade
→ findings
→ Finish
→ next case
```

must remain fully usable.

Do not add any new model prerequisite.

---

## H. Security/privacy audit

Ensure diff contains no:

- `.env`;
- token;
- password;
- DSN;
- model weight;
- raw PHI;
- local database;
- `local-state`;
- absolute private path in committed product data.

Filename parsing remains pseudonymous-evidence handling only.

---

## I. Documentation audit

Run the repository docs check if available.

Verify:

- root README links resolve;
- `docs/README.md` exists;
- clinician instructions match final UI wording;
- developer docs still accurately describe backend action/hash semantics;
- no document claims Phase 3/model qualification.

---

# 9. Validation plan

Use focused tests while iterating.

Before independent review run the complete applicable branch validation.

At minimum:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check dr_support tests

cd frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
cd ..

npm.cmd test
git diff --check
```

Also run the repository documentation check if present, for example:

```powershell
.\.venv\Scripts\python.exe scripts\docs\check_docs.py
```

If the exact command differs, inspect the repository and use the actual documented command.

---

# 10. Root legacy smoke policy

`npm.cmd test` at repository root includes the historical `web/` UI smoke.

Do not fake a pass.

Classify the result:

## PASS

Record it normally.

## Known environment prerequisite failure

If it fails only because the documented historical HRF/public sample set is not present:

```text
KNOWN_BASELINE / NON-BLOCKING
```

Record:

- exact failing assertion/timeout;
- sample count actually present;
- why the failure predates/does not exercise this React Phase 2 patch.

## Regression

If the current patch caused the failure:

```text
REQUIRED FIX
```

and fix before closeout.

---

# 11. Independent review policy

After MAIN self-audit is clean:

```text
one exact-candidate independent O1 or O2 review
```

Review must cover:

- code diff;
- tests;
- persistence semantics;
- completeness/annotation-confirmation semantics;
- resolver refresh safety;
- clinical workload/usability;
- docs consistency;
- phase-boundary safety.

Classify findings only as:

```text
BLOCKER
REQUIRED FIX
NON-BLOCKING / DEFER
```

MAIN should fix `BLOCKER` and `REQUIRED FIX` findings automatically within this approved patch.

Re-review only the changed diff/affected contract.

Do not restart a broad repository audit after every small correction.

If reviewer account infrastructure shares the same local account context, report reduced independence honestly; do not misrepresent it.

---

# 12. Efficiency / orchestration rule

Previous Phase 2.1 runs consumed excessive tokens/time.

For this final patch:

- do not repeatedly launch failing IMPLEMENT routes;
- if a worker transport fails once before useful edits, MAIN may implement directly in the bounded worktree under the previously approved recovery pattern;
- do not ask the owner about routine coding details;
- self-audit locally before external review;
- run full validation once when the candidate is stable, not after every tiny edit;
- independent re-review is changed-diff only.

Quality must not be reduced, but repeated orchestration overhead should be avoided.

---

# 13. Owner UAT after integration

After final candidate integration, owner UAT should be focused, not a repeat of all Phase 2 work.

## UAT-1 Confirm Image

Use a previously unresolved filename such as:

```text
HN5071 L1.jpg
```

Expected:

```text
Patient HN5071
Eye Left
```

as safe supported evidence/suggestion, with no manual historical overwrite.

## UAT-2 Annotation layout

Open Findings/Annotation page.

Expected:

- tools next to/above canvas;
- no large unused area caused by right-side stack;
- image remains primary;
- Finish is easy to find;
- normal workflow needs little reading.

## UAT-3 Finding recorded

Add/keep one Core finding.

Click one primary Finish action.

Expected:

- no separate Core-state click;
- case completes;
- Worklist shows complete;
- state survives restart.

## UAT-4 Reviewed none found

Use a case with no Core human findings.

The finish action must explicitly say the reviewed-none meaning.

Expected:

- Core reviewed-none stored deliberately;
- no negative annotation fabricated;
- case completes.

## UAT-5 Error

Trigger/reproduce one validation/conflict error if practical.

Expected:

```text
human-readable message
```

never:

```text
[object Object]
```

## UAT-6 Advanced untouched

Finish Core work without opening Advanced.

Expected:

```text
ADVANCED = NOT_REVIEWED
```

and no blocker.

---

# 14. Phase 2 closeout evidence update

When implementation, self-audit, independent review and owner UAT pass:

update the Phase 2 evidence sections in:

```text
docs/milestone/m1/M1_MASTER_PLAN.md
docs/milestone/m1/M1_PHASE2_UWF_LABELING.md
```

Record:

- original Chunk A/B evidence;
- Phase 2.1 hardening evidence;
- final closeout commit;
- test counts;
- owner UAT;
- independent review;
- known accepted limitations;
- Model API live-success gate deferred to Phase 3 if still not configured.

Do not erase historical evidence.

Before owner approval, keep:

```text
Phase 2 = READY_FOR_REVIEW
Phase 3 = NOT_STARTED
```

After explicit owner approval in a subsequent closeout action, Phase 2 may become:

```text
DONE
```

Phase 3 must remain `NOT_STARTED` until separately authorized.

---

# 15. Model API closeout boundary

Phase 2 does not require a qualified native UWF Model API.

If approved `REMOTE_MODEL_URL` / token are still unavailable:

```text
Live Model API success path = DEFERRED TO PHASE 3
```

provided:

- unavailable/failure behavior is validated;
- manual review remains functional;
- no model-ready claim is made.

Do not create a temporary fake production credential merely to turn a gate green.

---

# 16. Completion gate for the local execution run

The local run may stop only when all are true:

- every required patch item is implemented or explicitly blocked by a genuine owner-level contract decision;
- local self-audit has no unresolved `BLOCKER` or `REQUIRED FIX`;
- focused + full applicable validation completed;
- exact-candidate independent review completed;
- required review findings fixed;
- frontend rebuilt on authoritative main after merge;
- main pushed and synchronized with origin;
- feature worktree/branch removed;
- Brain is healthy and FRESH;
- Phase 2 remains `READY_FOR_REVIEW`;
- Phase 3 remains `NOT_STARTED`;
- Owner UAT can resume.

Final execution marker:

```text
PHASE 2 FINAL PATCH READY_FOR_OWNER_CLOSEOUT
```

Do **not** mark Phase 2 `DONE` inside this implementation run without explicit owner acceptance after UAT.

---

# 17. Required completion receipt

Return a concise but evidence-based receipt:

```text
Starting SHA:
Candidate SHA:
Final main SHA:

Resolver refresh:
- unresolved legacy filename evidence:
- manual/confirmed overwrite protection:
- chronology safeguard:

Annotation completion:
- one-action Finish behavior:
- CORE findings-recorded path:
- CORE reviewed-none path:
- Advanced untouched behavior:
- retry/conflict behavior:

Annotation layout:
- toolbar placement:
- Finish card:
- reviewer compaction:
- responsive audit:

Error handling:
- structured 422:
- 409:
- non-JSON/500:
- [object Object] regression:

Dataset/no-negative audit:
- empty set:
- REVIEWED_NONE_FOUND:
- untouched AI:
- lesion_training_ready conclusion:

Docs:
- README:
- docs/README:
- clinician docs:
- developer docs:
- docs QA:

Validation:
- backend:
- frontend:
- Ruff:
- typecheck:
- build:
- root smoke:
- git diff --check:
- PostgreSQL restart/persistence:
- AI-off/manual path:

Self-audit:
Independent review:
Review findings/fixes:

Brain:
main == origin/main:
clean worktree:
temporary branch/worktree removed:

Phase 2:
READY_FOR_REVIEW

Phase 3:
NOT_STARTED

Owner UAT:
READY

Final marker:
PHASE 2 FINAL PATCH READY_FOR_OWNER_CLOSEOUT
```

# 18. Formal owner closeout record

Owner accepted the Phase 2 UAT and authorized formal Phase 2 closeout on
2026-10-03. Phase 2 is `DONE` at final integrated implementation SHA
`bde3e673169fa6de2f1ecee6373c22c7d46a04de`. The accepted independent O1
changed-diff review and MAIN self-audit remain the evidence for the exact
candidate. The pre-approval receipt above is historical evidence and remains
unchanged in substance.

Accepted limitations:

- the feature-worktree `.venv` was unavailable in the final audit environment;
- no PostgreSQL DSN/server was available for that final audit run;
- the 1920px audit was not run;
- reviewer account independence remained unverified;
- the previously documented legacy root-smoke limitation remains historical
  evidence, not a fabricated PASS;
- live Model API success remains deferred to Phase 3.

Owner-accepted UX observations are `NON-BLOCKING / DEFERRED TO PRE-PHASE-3`
and were not implemented in this closeout:

- compress the Annotation Editor toolbar toward one row, moving secondary
  tools to a compact popover/progressive disclosure where appropriate;
- replace the implementation-oriented/confusing `Record partial review`
  wording in a future UX pass by deriving completeness from clinical actions
  rather than exposing backend state-management terminology.

Phase 3 remains `NOT_STARTED`. This closeout does not authorize
production/clinical deployment, real hospital-data use, native UWF model
qualification, live Model API success, Phase 3 start, or Phase 4 export-policy
approval.

# End of M1 Phase 2 Final Closeout Patch
