# DR Screening M1 — Phase 2 UWF Labeling Workflow

**Document revision:** Execution r3.0 (owner-directed Phase 2 execution specification)
**Prepared:** 2026-09-29
**Document status:** `OWNER_DIRECTED_EXECUTION_SPEC`
**Implementation status:** `READY_FOR_REVIEW` — bounded Phase 2 implementation is integrated; owner closeout is pending.
**Phase 1 dependency:** `SATISFIED` — Phase 1 is `DONE` as of 2026-09-29.
**Repository baseline at preparation:** `20726efcb8aa6ce857eb9b8537810fea5175b42e` (`main` / `origin/main`)
**Primary repository:** `siriponsri/dr-support-screening-poc`
**Normative parent:** `docs/milestone/m1/M1_MASTER_PLAN.md`, especially §§2–10, 17, 20, 23–24
**Research evidence retained:** `DR_M1_DELIVERY_20260928_r1/`, notebook/code-reading copies, prepared model bundles and masking research. Research assets are evidence, not clinical or production approval.

> This document expands the Master Plan; it does not replace it. `AGENTS.md`, `DESIGN.md`, accepted ADRs, the Phase 1 persistence contract, and approved owner decisions remain authoritative. If this file conflicts with a frozen safety/privacy/clinical/data-integrity contract, stop only the affected work, preserve completed unaffected work, and report the exact conflict.

---

## 1. Purpose

Phase 2 turns the Phase 1 data foundation into an efficient **physician-led UWF labeling workflow**.

The desired physician path is intentionally short:

```text
Open UWF case
→ confirm patient / eye / visit evidence when needed
→ inspect Original
→ inspect Masked Analysis / AI evidence when available
→ choose or correct DR grade
→ review Core findings
→ optionally review Advanced findings
→ confirm/save
→ move to next case
```

The system, not the physician, should automatically capture reviewer identity, time, revision, source identity, model/preprocessing provenance, and audit history wherever the existing product context already supplies them.

Phase 2 must optimize for two outcomes at the same time:

1. **low physician burden**, because labeling time is scarce; and
2. **high training-label consistency**, because ambiguous or inconsistently interpreted labels create downstream relabeling and model-training cost.

M1 remains a **Labeling System**, not an autonomous screening/referral product. Phase 2 does not authorize real hospital inference/export, production deployment, model retraining, or clinical screening claims.

---

## 2. Alignment with the Master Plan

The Master Phase 2 goal is to make repeated UWF labeling efficient while maximizing physician-confirmed information. This specification implements the Master Phase 2 requirements without changing their intent.

| Master Phase 2 requirement | Phase 2 execution owner |
|---|---|
| 1. Preserve viewer / visual direction | P2-2, P2-4 |
| 2. UWF intake without treating UWF as CFP | P2-1, P2-7 |
| 3. Shared masked-analysis representation and safe failure | P2-3, P2-4 |
| 4. Patient/eye/visit evidence | P2-1 |
| 5. Efficient DR grade confirmation/editing | P2-2 |
| 6. Core findings workflow | P2-5 |
| 7. Advanced findings separate/optional | P2-5 |
| 8. Annotation-group completeness | P2-6 |
| 9. AI vs human provenance | P2-5, P2-6 |
| 10. Reject/correct/add/confirm | P2-5 |
| 11. Original-image coordinates authoritative | P2-3, P2-4, P2-5 |
| 12. Manual labeling when AI unavailable | P2-7 |
| 13. Explainability Panel + CFP fallback notice | P2-4, P2-7 |

Phase 2 exit is based on the integrated labeling workflow and recorded evidence. Native UWF model readiness is **not** a Phase 2 prerequisite; model qualification belongs to Phase 3.

---

## 3. Execution philosophy — reduce owner burden without weakening safety

### 3.1 MAIN / IMPLEMENT / REVIEW autonomy

Within this approved Phase 2 scope, MAIN, IMPLEMENT and REVIEW should:

- inspect the repository and select the smallest compatible implementation;
- make normal implementation decisions without asking the owner for component structure, helper functions, file organization, test naming, minor copy, or other routine engineering details;
- implement, test, review, fix and re-test within the bounded work item;
- preserve existing frozen contracts unless this specification explicitly authorizes an additive change;
- continue unaffected work when a local sub-item is blocked.

Do **not** ask the owner to approve every implementation detail.

### 3.2 When an owner decision is actually required

Stop only the affected work and ask the owner when a choice would materially change one of these:

1. clinical label meaning or clinical negative semantics;
2. real hospital-data access, inference, export, or permission policy;
3. destructive patient/review-data behavior;
4. original-image immutability or authoritative coordinate semantics;
5. model-domain claim, selected production model, or model weight/artifact identity;
6. referral, DME, treatment, or autonomous screening logic;
7. a frozen confirmation/provenance contract that cannot be preserved compatibly;
8. scope beyond Phase 2.

If an unresolved issue can be safely represented as **unavailable**, **not reviewed**, **needs second review**, **deferred**, or **manual-only**, use that safe state and continue. Do not block the whole phase merely because an optional clinical/model capability is unresolved.

### 3.3 Review intensity

Phase 2 deliberately uses fewer review gates than Phase 1.

Use:

- focused tests while implementing;
- one substantive independent REVIEW for **Chunk A**;
- one substantive independent REVIEW for **Chunk B**;
- one final integration review / main validation before Phase 2 closeout.

O1 or O2 is acceptable when the reviewer is independent from MAIN/IMPLEMENT, read-only, and reviews the exact candidate/diff.

A reviewer should classify findings as:

- **BLOCKER** — data loss/corruption, incorrect coordinates, provenance failure, unsafe silent fallback, privacy/security violation, persistence failure, or acceptance-critical test failure;
- **REQUIRED FIX** — a Phase 2 functional or contract defect that prevents the bounded work from meeting this specification;
- **NON-BLOCKING / DEFER** — cosmetic issue, speculative enhancement, pre-existing warning/debt, optional documentation polish, or a later-phase capability.

Do not reopen previously closed findings without concrete regression evidence.
When a reviewed diff changes only to fix a bounded finding, re-review the affected change and contract; do not restart a whole-repository audit.

---

## 4. Phase 2 product outcome

At Phase 2 completion, a physician using public/synthetic or otherwise authorized test fixtures can:

- open a UWF case;
- verify patient/eye/visit evidence without inventing chronology;
- inspect the immutable Original;
- inspect the selected Masked Analysis image when AI processing is used;
- inspect AI Overlay and available Explainability evidence;
- assign one clinically named DR grade or deliberately mark the case unresolved/ungradable;
- review, correct, reject, or add Core findings;
- optionally use a separate Advanced findings surface without slowing the Core workflow;
- explicitly record whether a finding group was actually reviewed;
- save and reopen the same case after restart in the correct workspace;
- continue manual labeling when masking or Model API processing is unavailable;
- preserve raw AI history separately from final physician decisions;
- preserve original-image coordinates for stored spatial findings.

No Phase 2 success claim requires a ready native UWF model.

---

## 5. DR grading contract — fast for physicians, consistent for training

### 5.1 Clinician-facing five-grade rubric

The physician UI must display **descriptive clinical names**, not unexplained numeric buttons.

| Internal grade | Primary clinician-facing label | M1 interpretation baseline |
|---|---|---|
| `0` | **No apparent DR** | No apparent diabetic-retinopathy abnormality on the reviewed image |
| `1` | **Mild NPDR** | Microaneurysms only |
| `2` | **Moderate NPDR** | More than microaneurysms only, but less than Severe NPDR |
| `3` | **Severe NPDR** | Severe NPDR pattern; no proliferative sign. Use the approved simplified severity baseline (e.g. severe hemorrhage distribution, venous beading, or IRMA criteria) |
| `4` | **Proliferative DR (PDR)** | Proliferative evidence such as retinal neovascularization and/or vitreous/preretinal hemorrhage |

The numeric value is for storage/model compatibility. The UI should prioritize the clinical label.

The Master Plan and ICO clinical-reference baseline support the five named severity levels. Phase 2 must not create referral or DME semantics from the DR grade.

### 5.2 Keep non-grade states separate from the five classes

`Ungradable` and unresolved review states are **not sixth/seventh DR grades**.

Use semantics equivalent to:

```text
grade_status =
  NOT_REVIEWED
  FINAL
  UNGRADABLE
  NEEDS_SECOND_REVIEW

grade_value =
  0..4 only when grade_status = FINAL
```

Exact field names are an implementation decision if the existing contract requires compatibility.

#### `UNGRADABLE`

Use when the physician judges that the available image does not support a reliable DR severity assignment.

Examples of reasons may include image quality, insufficient usable retinal field, media/artifact obstruction, or another reviewability problem. Reason capture may be optional/quick-select; it must not add mandatory free-text burden.

`UNGRADABLE` is not exported as grade 0–4.

#### `NEEDS_SECOND_REVIEW`

Use when the image is reviewable but the physician does not want to finalize one of the five grades.

This replaces ambiguous clinician-facing use of `Unknown`. Existing persisted `Unknown / not yet determined` data must remain backward compatible, but the active UI should distinguish:

- untouched / not yet reviewed; from
- deliberately escalated for another review.

`NEEDS_SECOND_REVIEW` is not training-ready.

### 5.3 Grade interaction burden

Normal grade review should require approximately:

```text
inspect image
→ choose one descriptive grade
→ Confirm DR Grade
→ next case
```

Reviewer/time/audit/revision capture should be automatic when available from the current session/workflow.

Save/reopen is a system requirement, **not an extra physician step**. Reopening must restore the existing decision and history.

### 5.4 Multiple physicians and disagreement

Phase 2 must prevent one physician's review from silently overwriting another physician's independent review.

Default operation remains **single-reviewer efficient labeling**; do not require two ophthalmologists to review every image.

When multiple independent reviews exist:

```text
same final grade
→ preserve both review records
→ no disagreement flag required

different final grade
→ preserve both review records
→ mark NEEDS_ADJUDICATION / NEEDS_SECOND_REVIEW equivalent
→ exclude unresolved grade from training-ready status
→ present the case for a later adjudication pass
```

Do not:

- automatically average or majority-vote ordinal grades;
- silently keep only the most recent grade;
- force the model-training team to contact physicians case-by-case outside the product workflow.

The product should make disagreement cases discoverable as a batch/worklist state. Phase 4 may provide richer workspace-level filtering/export; Phase 2 needs at least persisted status and a usable path to reopen/adjudicate.

### 5.5 Calibration before large-scale labeling

The workflow should support a small clinician calibration/reference set before or early in large-scale labeling.

The exact number of images is operational, not a Phase 2 blocker. The purpose is to:

- expose Mild↔Moderate and Moderate↔Severe interpretation differences;
- verify that participating physicians interpret the UI rubric consistently;
- capture feedback on terminology;
- reduce later relabeling/adjudication load.

Agreement metrics such as weighted kappa may be reported when two independent sets are available, but Phase 2 must not fabricate a statistical acceptance threshold that the project has not approved.

Treated/stable PDR or other difficult edge cases should use `NEEDS_SECOND_REVIEW` until the clinical team freezes a dedicated rule. This does not block ordinary five-grade labeling.

---

## 6. Finding taxonomy and completeness — safe defaults that do not block Core work

### 6.1 Core findings

The Core workflow must remain fast and prioritize the Master Plan families:

- Microaneurysm (MA)
- Retinal hemorrhage (HE)
- Hard exudate (EX)
- Cotton-wool spot / soft exudate (SE)

Phase 2 may preserve the existing generic annotation geometry tooling and provenance model unless a specific class requires a clinically meaningful geometry change.

The Core physician action model is:

```text
AI suggestion or blank image
→ accept
→ correct
→ reject
→ add physician finding
→ confirm annotation set
```

Raw AI score/class/geometry must remain preserved when a physician corrects or rejects a suggestion. A physician-added/corrected annotation must not inherit a fabricated model score.

### 6.2 Advanced findings

Advanced findings remain a **separate optional surface** so they do not increase Core labeling burden.

The Master candidate list is retained:

- Dot hemorrhage
- Blot hemorrhage
- Flame-shaped hemorrhage
- Venous beading
- IRMA
- NVD
- NVE
- Preretinal hemorrhage
- Vitreous hemorrhage
- Fibrous proliferation

However, unresolved class definitions/geometry do **not** block P2-1/2/3/4/7 or the Core workflow.

Safe policy:

- implement the separate Advanced surface and versioned taxonomy boundary;
- enable only semantics that can be represented truthfully with the current/approved annotation contract;
- for a class whose geometry/meaning is unresolved, show it as unavailable/deferred rather than inventing a definition;
- never turn an unopened Advanced section into negative labels;
- record the active taxonomy version for every saved Advanced annotation.

If a specific unresolved Advanced class prevents final Phase 2 `DONE`, report that capability as deferred/limited at owner review rather than repeatedly reopening unrelated implementation.

### 6.3 Annotation-group completeness

Support states equivalent to:

```text
NOT_REVIEWED
PARTIALLY_REVIEWED
REVIEWED_NONE_FOUND
REVIEWED_FINDINGS_RECORDED
```

Operational meanings for Phase 2:

- `NOT_REVIEWED` — no deliberate review of that group has been recorded;
- `PARTIALLY_REVIEWED` — deliberate review occurred but the group/class scope was not completed;
- `REVIEWED_FINDINGS_RECORDED` — reviewer deliberately completed the group and one or more active findings are recorded;
- `REVIEWED_NONE_FOUND` — reviewer deliberately completed the group and explicitly recorded that no finding in the defined group was found.

Important boundary:

`REVIEWED_NONE_FOUND` may be stored as review-completeness evidence, but **Phase 2 alone does not authorize it as a training/export negative**. Phase 4 owns export eligibility/policy. This lets Phase 2 implement useful review-state capture without forcing the owner to freeze the full training-negative rubric now.

Never infer completeness from:

- number of AI boxes;
- empty detector output;
- empty annotation array;
- opening a panel;
- case-level annotation confirmation alone.

---

## 7. Intake, identity and provenance

### 7.1 Source boundaries

A source image must retain truthful origin/provenance separate from:

- retinal modality;
- patient pseudonym;
- deidentification state;
- use authorization/permission.

Do not classify hospital-origin data as `PUBLIC` or `SYNTHETIC` merely to fit the current Bridge v1 enum.

Phase 2 may add local/persisted provenance fields or an additive versioned contract needed to represent truthful origin while keeping the current remote Bridge behavior compatible.

Real hospital inference/export remains outside Phase 2 authorization until the appropriate data-steward/owner path is approved.

### 7.2 Patient / eye / visit

Capture or confirm, when evidence exists:

- pseudonymous patient key;
- laterality;
- visit/capture identity;
- acquisition date/time where supported;
- source evidence for resolver decisions.

Do not turn visit ordinal into acquisition chronology.

Uncertain context must remain uncertain rather than being invented. Manual correction/confirmation must be possible when current workflow supports it.

### 7.3 Original source integrity

Original bytes/hash are immutable evidence.

Normal Phase 2 operations must not:

- overwrite;
- recompress in place;
- rename destructively;
- permanently mask;
- rewrite source bytes to simplify model input.

All analysis representations are derivatives.

---

## 8. Shared masked-analysis representation and processing contract

### 8.1 One shared analysis-stage identity

Phase 2 owns a versioned contract equivalent to:

```text
Original
→ selected valid-retina / masked-analysis representation
→ provider-specific transform
→ model input
→ model output / explanation evidence
```

The selected Masked Analysis representation must have enough provenance to identify:

- source hash and source dimensions;
- derivative hash/identity;
- analysis/mask version;
- parameters relevant to reproducibility;
- input/output dimensions;
- color-space expectations where relevant;
- coordinate mapping / transform identity;
- fallback/error state.

### 8.2 Double-mask research issue

NB04 research applied `border_component_v1` before adapters that may apply v4 masking again. Source inspection alone does not prove that the paths are equivalent or harmful.

Phase 2 should:

1. compare candidate paths on synthetic/public fixtures with intermediate hashes/dimensions/geometry;
2. document measured differences;
3. choose/freeze the application-level shared representation contract;
4. avoid silently changing model-specific preprocessing behavior that belongs to Phase 3 qualification.

If the comparison cannot prove that changing adapter behavior is safe, keep current model-adapter behavior unchanged and hand the measured evidence to Phase 3. **Do not block the manual Phase 2 workflow.**

No mask coverage or fallback state may be treated as clinical gradability.

### 8.3 Mask failure

If a safe Masked Analysis image cannot be produced:

- show Original normally;
- show processing status as unavailable/failure;
- do not fabricate a normal-looking masked result;
- do not synthesize grade 0 or empty findings;
- keep manual grade/annotation workflow usable.

`UNMASKED_FALLBACK` must remain explicit and must not imply that image quality is adequate.

---

## 9. Viewer, AI Overlay, Explainability and coordinates

### 9.1 Required review modes

The active case should support, where evidence exists:

- **Original**
- **Masked Analysis**
- **AI Overlay**
- **Explainability**

Processing details remain distinct from Explainability.

### 9.2 Explainability semantics

Explainability may display supported evidence such as:

- grading class scores;
- grading patch/attention evidence;
- lesion proposals / review boxes;
- proposal confidence/fold agreement where actually available;
- model-domain limitation;
- unavailable/error state.

A grading attention map must be labeled as **model attention/evidence, not validated lesion localization**.

Explainability evidence must never:

- become a physician annotation automatically;
- create a gold lesion label;
- change the final physician grade;
- imply calibrated clinical probability unless calibration exists.

If no provider exposes explanation evidence, show `Unavailable` rather than fabricating it.

### 9.3 Original-image coordinates

Persist spatial findings in `original_image_pixels` or the current equivalent authoritative coordinate system.

Round-trip logic must account for relevant:

- resize;
- letterbox;
- crop/tile;
- viewer zoom/pan;
- shared analysis-stage transform;
- provider-specific transform.

A derivative/transform mismatch must block spatial AI display for that result and fall back to Original/manual review. Never silently rewrite stored geometry to make an overlay look aligned.

### 9.4 Coordinate oracle — lighter review process

The fixture oracle is developed **with** the implementation/tests, not as a separate pre-test approval ceremony.

It must document:

- synthetic/non-sensitive fixture identity;
- source dimensions;
- coordinate origin/axes;
- box representation;
- clipping/rounding convention;
- expected geometry/overlay;
- tolerance rationale.

REVIEW evaluates the oracle and implementation together during the relevant chunk review.

If a test expectation changes because the prior oracle was wrong, update the oracle with rationale and review that bounded change. Do not retroactively redefine an expectation merely to turn a real failure into PASS.

---

## 10. Manual/failure path and model-domain honesty

Manual physician labeling is a first-class path.

When AI is:

- unavailable;
- disconnected;
- unsupported;
- errored;
- not ready;
- disabled;

the physician must still be able to:

- inspect Original;
- confirm context;
- grade;
- annotate;
- save/reopen.

Do not synthesize AI results to keep the UI looking complete.

For any CFP-trained fallback shown on UWF, preserve the Master meaning equivalent to:

> **CFP-trained AI · Not validated for UWF**

The full primary notice and Processing details metadata must agree with the selected bundle manifest. Phase 2 tests warning visibility/state handling; Phase 3 owns guarded model-contract enablement and qualification.

---

## 11. Bounded Phase 2 work items

| ID | Work | Required outcome | Non-blocking/deferred boundary |
|---|---|---|---|
| **P2-1** | Intake & context | Truthful source provenance; patient/eye/visit evidence; save/reopen compatibility | Real hospital inference/export authorization remains later approval |
| **P2-2** | Efficient DR grade review | Named five-grade UI, separate Ungradable and Needs Second Review, automatic audit, disagreement-safe persistence | Treated/stable PDR edge rule may route to second review |
| **P2-3** | Processing-stage ownership | Versioned Original→Masked Analysis→provider transform contract; measured double-mask comparison | Do not change provider model behavior merely to finish Phase 2 |
| **P2-4** | Mask / Overlay / Explainability / mapping | Four review modes, case-level Processing details, coordinate round-trip tests, safe unavailable states | Phase 3 may later add richer provider explanation evidence |
| **P2-5** | Core + optional Advanced annotations | Core accept/correct/reject/add; Advanced separate; provenance preserved | Unresolved Advanced classes may remain disabled/deferred |
| **P2-6** | Completeness & persistence | Explicit group review states, reviewer/time/taxonomy version, restart/isolation | Phase 4 decides negative/export eligibility |
| **P2-7** | Manual/failure/domain path | Manual workflow survives Model API/mask failure; CFP-on-UWF warning visible when applicable | Model readiness itself belongs to Phase 3 |

---

## 12. Two implementation chunks

### Chunk A — Core UWF Review Foundation

Includes:

- P2-1 Intake & context
- P2-2 DR grade review
- P2-3 processing representation
- P2-4 Original / Masked Analysis / AI Overlay / Explainability / mapping
- P2-7 manual/failure/domain states

Expected handoff:

- physician can open fixture UWF;
- context is truthful;
- grade workflow is low-burden and persistent;
- Masked Analysis / overlay state is inspectable;
- manual mode works with AI off;
- no false model/domain claim;
- original image unchanged;
- relevant focused/backend/frontend tests pass.

Then obtain **one independent Chunk A review**.

### Chunk B — Findings & Completeness

Includes:

- P2-5 Core / Advanced annotation workflow
- P2-6 completeness and persistence
- adjudication/disagreement worklist state needed by P2-2, if not already completed in Chunk A

Expected handoff:

- Core findings are efficient;
- AI vs human lineage is preserved;
- Advanced remains separate and non-blocking;
- completeness requires deliberate reviewer action;
- save/reopen and revision behavior remain correct;
- unresolved negatives are not exported/treated as gold;
- relevant tests pass.

Then obtain **one independent Chunk B review**.

After both chunks are integrated, run final main validation and produce the Phase 2 evidence receipt.

---

## 13. Validation strategy

### 13.1 Focused tests during implementation

Extend existing tests where practical:

- `tests/test_admission.py`
- `tests/test_resolver.py`
- `tests/test_derivatives.py`
- `tests/test_workflow.py`
- `tests/test_uwf_intake.py`
- PostgreSQL persistence/revision/isolation tests affected by additive payload work
- frontend review/geometry/workflow tests
- `tests/overlay.test.cjs` where still authoritative

Add focused coverage for:

- five-grade named UI and final persistence;
- Ungradable vs Needs Second Review;
- reopen after restart;
- two-reviewer disagreement preservation and no silent overwrite;
- source provenance round trip;
- double-mask candidate comparison;
- coordinate round-trip;
- Model API unavailable;
- mask failure;
- Explainability unavailable;
- Core finding accept/correct/reject/add;
- completeness transitions;
- no gold-label promotion from untouched AI evidence.

### 13.2 Full validation

Run the applicable repository-required suite before final Phase 2 integration closeout:

```text
python -m pytest -q
python -m ruff check dr_support tests
frontend: npm test
frontend: npm run typecheck
frontend: npm run build
root smoke / applicable browser or API smoke
git diff --check
```

Use the repository's actual supported environment/commands at execution time. Report skipped checks honestly.

Do not repeatedly rerun the entire full suite after every minor fix; use focused tests during iteration, then rerun affected tests and final full validation at the integration gate.

### 13.3 Visual/manual receipt

Use public/synthetic/deidentified authorized fixtures only.

Capture a concise reviewer receipt that confirms:

- Original visible;
- Masked Analysis visible when available;
- overlay alignment;
- Explainability semantics/unavailable state;
- descriptive grade labels;
- Ungradable / Needs Second Review behavior;
- Core finding action flow;
- manual operation with AI off;
- save/reopen behavior;
- no PHI/secrets in the receipt.

No synthetic fixture result is a clinical-validity claim.

---

## 14. Acceptance criteria

Phase 2 is `READY_FOR_REVIEW` when the integrated candidate demonstrates the following for the implemented scope:

### Core physician workflow

- [ ] UWF fixture opens in the correct workspace.
- [ ] Patient/eye/visit evidence is reviewable and not fabricated.
- [ ] Original source remains immutable.
- [ ] Five clinical DR labels are understandable without relying on numeric codes.
- [ ] Normal grade confirmation is a short action path.
- [ ] Ungradable is separate from DR severity.
- [ ] Needs Second Review is separate from a final DR grade.
- [ ] Save/reopen restores prior physician decision/history.
- [ ] Multiple independent reviews cannot silently overwrite one another.
- [ ] Unresolved disagreement is excluded from training-ready grade status.

### Representation / AI evidence

- [ ] Masked Analysis is inspectable when used.
- [ ] Processing-stage provenance is versioned.
- [ ] Original-coordinate round trip is tested.
- [ ] AI Overlay does not alter human labels.
- [ ] Explainability is clearly separated from Processing details.
- [ ] Attention is not represented as lesion localization.
- [ ] AI unavailable/error/mask failure preserves manual workflow.
- [ ] CFP-on-UWF fallback state is truthful when such evidence is displayed.

### Findings

- [ ] Core accept/correct/reject/add works.
- [ ] Raw AI lineage is preserved after human action.
- [ ] Physician-added/corrected findings do not inherit fabricated model confidence.
- [ ] Advanced is separate and optional.
- [ ] Unsupported/unresolved Advanced semantics are not invented.

### Completeness / persistence

- [ ] Group completeness requires deliberate review action.
- [ ] Empty AI output or empty annotation list is not automatically negative.
- [ ] Completeness/reviewer/time/taxonomy version survives restart.
- [ ] Phase 1 workspace isolation/revision protections remain intact.

### Integration

- [ ] Required focused tests pass.
- [ ] Applicable full backend/frontend validation passes or limitations are explicitly recorded.
- [ ] Chunk reviews have no unresolved BLOCKER/REQUIRED FIX.
- [ ] Final `main` is clean and synchronized with `origin/main`.
- [ ] Phase evidence is recorded in the Phase 2 document and Master tracker.
- [ ] No real-hospital-data or production authorization is implied.

`DONE` is an owner closeout decision after the final evidence receipt. Optional/deferred Advanced/model capabilities must be reported honestly and must not be disguised as complete.

---

## 15. Failure behavior

| Failure | Required behavior |
|---|---|
| PostgreSQL conflict / stale revision | Preserve existing committed revision, expose conflict/reload path, no silent overwrite |
| PostgreSQL unavailable | Fail clearly; no silent SQLite authority |
| Mask extraction fails | Original/manual workflow remains usable; processing failure visible |
| `UNMASKED_FALLBACK` | Explicit state; no claim of gradability |
| Model API unavailable/error | Manual workflow continues; no fake grade/findings |
| Explainability unavailable | Show unavailable; no fabricated heatmap/evidence |
| Transform/hash mismatch | Do not display spatial AI overlay for that result |
| Independent grade disagreement | Preserve both reviews; unresolved/adjudication state; not training-ready |
| Unknown patient/eye/visit evidence | Keep unknown/unresolved; do not invent |
| Unsupported Advanced definition | Disable/defer that class; continue Core workflow |
| Clinical/export-negative rule unresolved | Store review state but defer negative training/export semantics to Phase 4 |

---

## 16. Dependencies and decisions intentionally deferred

These are **not blockers for ordinary Phase 2 fixture implementation**:

1. real hospital source/permission contract for inference/export;
2. production deployment;
3. NB01/USPEC checkpoint/runtime/rights/clinical qualification;
4. PRISM clinical UWF validity;
5. Phase 3 model-contract changes;
6. final referral/DME policy;
7. treated/stable PDR edge-case rule beyond safe second-review handling;
8. full Advanced taxonomy/geometry for classes that cannot be represented safely yet;
9. Phase 4 negative/export eligibility policy;
10. learned longitudinal model or progression logic.

If one of these becomes necessary to complete a specific bounded capability, report that capability as `DEFERRED`/`BLOCKED` while continuing unaffected work.

---

## 17. Repository and Git lifecycle

Follow root `AGENTS.md`.

Before implementation writes, record:

```text
repository root
worktree path
current branch
current HEAD
git status --short --branch
```

Implementation work must use bounded branch/worktree(s), not direct writes to authoritative `main`, except owner-authorized documentation/integration-only work.

For each implementation chunk:

```text
clean synchronized main
→ bounded branch/worktree
→ implementation
→ focused tests
→ required chunk validation
→ scoped add
→ commit
→ push branch
→ independent review
→ bounded fixes if required
→ merge/integrate
→ validate authoritative main as applicable
→ push main
→ verify remote
→ cleanup completed branch/worktree
```

Do not use destructive reset/clean/restore to erase unexpected work.

Do not force-push or delete an unrelated branch/worktree.

---

## 18. Execution ledger

| Work item | State at document adoption | Evidence needed to close |
|---|---|---|
| P2-1 Intake/context | `DONE` | Chunk A candidate `6bfa782`; intake/context and truthful-origin tests |
| P2-2 Grade review | `DONE` | Chunk A candidate `6bfa782`; named-grade, Ungradable, Needs Second Review, disagreement/adjudication tests |
| P2-3 Representation | `DONE` | Chunk A candidate `6bfa782`; versioned derivative, mask and double-mask evidence |
| P2-4 Viewer/Explainability/mapping | `DONE` | Chunk A candidate `6bfa782`; safe display/unavailable and coordinate fail-closed tests |
| P2-5 Findings | `DONE` | Chunk B candidate `6c33255`; Core lineage-preserving workflow and safe Advanced boundary |
| P2-6 Completeness | `DONE` | Chunk B candidate `6c33255`; deliberate group states, persistence, reviewer/time/taxonomy and revision tests |
| P2-7 Manual/failure | `DONE` | Chunk A candidate `6bfa782`; AI/mask unavailable manual continuation tests |
| Chunk A REVIEW | `DONE` | Independent O1 exact-candidate review PASS; candidate `6bfa782` |
| Chunk B REVIEW | `DONE` | Independent O1 exact-candidate review PASS after bounded fix; candidate `6c33255` |
| Final integration validation | `READY_FOR_REVIEW` | Main `5b300f7`; full backend/frontend validation and diff check pass; owner closeout remains |
| Owner Phase 2 closeout | `TODO` | owner reviews final evidence and decides `DONE` |

Allowed execution states:

```text
TODO
IN_PROGRESS
BLOCKED
DEFERRED
READY_FOR_REVIEW
DONE
```

Do not convert an optional/deferred capability into a phase-wide blocker unless it is explicitly required by the Master acceptance criteria and cannot be safely represented as unavailable/deferred.

---

## 19. Evidence receipt template

MAIN must maintain a concise receipt rather than repeatedly rewriting planning prose.

### Repository

```text
Phase 2 start baseline:
Chunk A integrated commit:
Chunk B integrated commit:
Final main commit:
origin/main synchronized:
worktree/branch cleanup:
```

### P2-2 grade workflow

```text
Five descriptive labels:
Ungradable state:
Needs Second Review:
single-review path:
multi-review disagreement:
restart/reopen:
training-ready exclusion for unresolved:
```

### Representation / geometry

```text
shared analysis representation version:
source hash preservation:
mask/transform identity:
double-mask comparison:
coordinate oracle:
overlay round-trip:
```

### Findings / completeness

```text
Core taxonomy/version:
Core action tests:
Advanced enabled/deferred classes:
group completeness version:
reviewed-negative export authorization: NOT AUTHORIZED BY PHASE 2 unless separately approved
```

### Failure/manual path

```text
Model API down:
mask failure:
Explainability unavailable:
CFP/UWF warning:
manual save:
```

### Validation

```text
focused backend:
full backend:
Ruff:
frontend test:
typecheck:
build:
root/browser/API smoke:
skips/warnings:
independent Chunk A review:
independent Chunk B review:
final integration review:
```

### 2026-10-03 final closeout candidate receipt

```text
Starting SHA: dded17ee035464255b77a3206ccb00b6068db60a
Candidate SHA: 732cad50cf47cf89afa337f5cab5081f57f6aa33
Final main SHA: ea329f400c6ed55f4ab5c8dc6c832da78f1969ed

Resolver refresh: PASS; unresolved legacy filename evidence refreshes per field,
manual/confirmed identity remains protected, sequence remains evidence rather
than chronology, and refresh events include compact prior/new parser evidence
without raw OCR text. Repeated reads do not duplicate events.
Annotation completion: PASS; one Finish action records Core findings-recorded or
explicit reviewed-none, confirms the current set, preserves untouched AI and
unopened Advanced provenance, and retries lost/conflicted requests from a
refreshed record. Finish locks edits, navigation and autosave during the
multi-request persistence sequence.
Annotation layout/browser: PASS at 1366, 1024 and 800 pixels with no horizontal
overflow; Lighthouse accessibility 100 and best practices 100; AI-off manual
flow completed through grade, Finish and Worklist completion; restart preserved
grade, completeness, reviewer, timestamp and annotation hash. 1920-pixel visual
inspection was not run.
Error handling: PASS for structured 422, string detail, 409 and non-JSON/500
fallbacks; completeness mutations send JSON; no [object Object] regression.
Dataset/no-negative audit: REVIEWED_NONE_FOUND and empty human sets do not create
negative lesion annotations; empty AI output is not reviewed-none; untouched AI
rows remain AI evidence; lesion_training_ready remains the pre-existing
task-specific readiness baseline and Phase 4 owns reviewed-negative policy.
Documentation: source clinician/developer workflow docs and docs/README.md are
aligned; docs QA passed for 88 sources from the bounded feature worktree. The
authoritative outer-main invocation reports only the preserved nested `main/`
worktree's duplicate generated PDFs as a workspace-layout limitation.
Validation: full backend 213 passed / 28 skipped / 50 warnings; focused resolver
and workflow tests 36 passed; Ruff PASS; frontend 19 files / 121 tests PASS;
typecheck PASS; build PASS with existing large-chunk warning; overlay/API root
smoke checks PASS, then legacy runner stopped because this feature worktree has
no .venv/Scripts/python.exe (KNOWN ENVIRONMENT LIMITATION, not a product pass);
git diff --check PASS; PostgreSQL persistence/restart file 8 passed / 26 skipped
because no designated DSN/server was available.
Independent review: configured O1 changed-diff review PASS for candidate 732cad5;
the prior O1 review's four REQUIRED FIX findings were corrected. The fallback
host exposes no account selector, so account-level independence is unverified.
Phase 2: READY_FOR_REVIEW
Phase 3: NOT_STARTED
Owner UAT: READY
```

---

## 20. Handoff to later phases

### To Phase 3

Provide:

- selected shared analysis representation version;
- transform/coordinate contract;
- measured double-mask comparison;
- model-domain warning requirements;
- Explainability display contract;
- manual/unavailable state behavior.

Phase 3 owns:

- bundle hash/load/runtime/security qualification;
- native UWF / CFP fallback capability negotiation;
- provider-specific preprocessing/output qualification;
- production model readiness claims.

### To Phase 4

Provide:

- final physician grade semantics;
- unresolved/adjudication states;
- Core/Advanced taxonomy version(s);
- annotation lineage;
- completeness states;
- persisted processing/explanation provenance.

Phase 4 owns:

- workspace-level query/detail/export;
- training readiness;
- reviewed-negative eligibility;
- contamination prevention;
- reproducible dataset snapshots.

### To Phase 5

Provide:

- integrated Phase 2 commit;
- workflow/visual receipts;
- source-integrity evidence;
- coordinate round-trip evidence;
- manual/failure evidence;
- accepted limitations/deferred capabilities.

---

## 21. Phase 2 document-adoption actions

Before implementation starts, MAIN should perform a documentation-only adoption pass:

1. verify actual clean synchronized `main` and current HEAD;
2. place this file at `docs/milestone/m1/M1_PHASE2_UWF_LABELING.md`;
3. reconcile only affected Master Plan sections so they agree with this owner-directed Phase 2 specification;
4. keep Phase 2 implementation status `NOT_STARTED` until code implementation actually begins;
5. record in the Master decision log:
   - low-burden descriptive five-grade workflow;
   - `Ungradable` separate from grade;
   - `Needs Second Review` replacing ambiguous active-UI `Unknown` semantics while preserving backward compatibility;
   - disagreement/adjudication preservation without mandatory double review;
   - two substantive chunk reviews plus final integration validation;
   - O1/O2 flexible independent review;
   - unresolved optional clinical/model items should be deferred locally rather than block unrelated Phase 2 work;
6. update Project Brain with the adopted Phase 2 scope, baseline, review policy and deferred boundaries;
7. run documentation consistency/diff checks;
8. commit and push the documentation/Brain preparation as permitted by the repository/Brain workflow;
9. verify `main == origin/main` and clean state;
10. **stop and report to the owner before implementation writes.**

This adoption pass is preparation only. It must not silently start P2-1 through P2-7.

---

## 22. Change log

**2026-09-28 r1–r2.2:** prior candidate expanded the Master Phase 2 requirements, source-origin gap, shared masked-analysis representation, Explainability surface, mapping QA, failure behavior and execution ledger.

**2026-09-29 Execution r3.0:** owner-directed execution rewrite after Phase 1 closeout. Rebased Phase 2 on completed PostgreSQL foundation; reduced review-loop intensity; made MAIN/IMPLEMENT autonomous for ordinary implementation details; introduced a low-burden physician grading contract with descriptive five-class labels, separate `Ungradable`, explicit `Needs Second Review`, disagreement/adjudication preservation, and optional calibration; kept Advanced/completeness/model/hospital-data uncertainties from blocking unrelated Core work; moved negative-export authority to Phase 4; replaced pre-test coordinate approval ceremony with implementation-plus-review evidence; retained Master safety, provenance, coordinate, UWF/CFP-domain, manual-fallback and human-authority boundaries.

**2026-10-01 implementation receipt:** Phase 2 began from integrated main `5a4e9721ddfa8d5613db8932aa0e07d13fda6f97`, which contains the adopted r3.0 specification and Chunk A integration. Chunk A candidate `6bfa7825da7175694373e6b3661abc7d53d7d5f7` received independent O1 review PASS and is integrated in main history. Chunk B candidate `6c33255741b1b43a42b1474a05a3db6cfcbce021` received independent O1 review PASS after a bounded completeness synchronization fix. Final integrated main is `5b300f70d8ab6a5433d2066d24a8706fe044a696`. Full main validation: backend `198 passed, 27 skipped, 42 warnings`; Ruff PASS; frontend `17 files / 105 tests PASS`; typecheck PASS; build PASS with existing chunk-size warning; `git diff --check` PASS. Advanced class-specific annotation semantics remain deferred; the UI records Advanced partial review only. Reviewed-none remains completeness evidence, not Phase 2 training/export-negative authority. This receipt sets Phase 2 to `READY_FOR_REVIEW`, not `DONE`; owner closeout remains required.

# End of M1 Phase 2 Execution Specification
