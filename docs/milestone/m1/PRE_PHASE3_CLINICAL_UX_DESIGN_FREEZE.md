# DR Screening M1 — Pre-Phase 3 Clinical UX & Design Freeze

**Document revision:** r1.0  
**Prepared:** 2026-10-03  
**Document status:** `OWNER_DIRECTED_PRE_PHASE3_EXECUTION_SPEC`  
**Implementation status:** `OPEN / NOT_RUN / NOT_READY_FOR_OWNER_UAT` — the exact candidate still has unrun runtime gates and blocked test collection; owner UAT and freeze acceptance remain open.
**Repository:** `siriponsri/dr-support-screening-poc`  
**Authoritative baseline:** `f288ae5e8a527f124aaa99eedc6f3d6f7a3e32cb`  
**Phase 1:** `DONE`  
**Phase 2:** `DONE`  
**Phase 3–5:** `NOT_STARTED`

**Execution name:** `P3-0 — Clinical UX & Design System Freeze`

> P3-0 is a bounded pre-Phase-3 product/UX convergence pass. It is deliberately placed after Phase 2 closeout and before Phase 3 model integration so the clinician workstation has a stable, low-burden presentation contract before new model evidence, controls, and explainability are introduced.

---

# 1. Authority

Read completely before implementation:

1. `AGENTS.md`
2. `DESIGN.md`
3. `docs/milestone/m1/M1_MASTER_PLAN.md`
4. `docs/milestone/m1/M1_PHASE2_UWF_LABELING.md`
5. `docs/milestone/m1/M1_PHASE2_FINAL_CLOSEOUT_PATCH.md`
6. accepted ADRs for confirmation, dataset readiness, immutable source, and original-image geometry
7. current clinician/developer manuals for every surface changed by P3-0

This document defines **WHAT must be achieved**. MAIN/IMPLEMENT choose the smallest compatible implementation after auditing the repository.

P3-0 does **not** reopen Phase 2. Phase 2 clinical/data behavior is frozen unless a concrete regression is found. If a desired UX requires changing a frozen clinical/data contract, STOP and report the exact conflict.

---

# 2. Why P3-0 exists

Phase 2 already established the hard safety and data contracts:

- image/context confirmation;
- five-grade DR review;
- Core finding annotation;
- explicit completeness;
- AI/Human provenance;
- PostgreSQL authority;
- immutable source images;
- original-image coordinates;
- mask/analysis evidence;
- manual AI-off operation;
- annotation hash/confirmation;
- safe restart/audit behavior.

Owner UAT accepted Phase 2 but deferred product-level refinements:

- the Annotation toolbar consumes too much vertical space;
- `More tools` should become a true popover/overflow surface;
- `Record partial review` exposes implementation vocabulary and is confusing;
- some completed-state guidance is duplicated;
- the overall UI can become more minimal, workstation-like, and institutionally appropriate.

P3-0 therefore focuses on:

```text
less manual work
+ fewer exposed concepts
+ fewer repeated fields
+ fewer unnecessary transitions
+ stronger image-first hierarchy
+ compact contextual controls
+ one obvious next action
+ KKU / Faculty-of-Medicine-aware visual identity
+ Thai clinician usability
```

The goal is not to clone MONAI Label, OHIF, or CVAT. The goal is to learn from mature medical-imaging workstations and produce a distinct Retinal Review Workbench optimized for UWF DR labeling.

---

# 3. Product statement to freeze

The workstation should feel like:

> **A focused retinal clinical workbench where the system handles clerical state, persistence, provenance, and navigation, while the clinician handles only decisions that require human judgment.**

Normal mental model:

```text
see image
→ decide
→ correct only if needed
→ finish
→ next image
```

Avoid:

```text
choose internal state
→ save technical state
→ confirm persistence state
→ interpret backend terminology
→ navigate manually
```

---

# 4. Frozen contracts

P3-0 must preserve:

## 4.1 Human authority

- Final DR grade remains clinician-confirmed.
- AI predictions remain optional evidence.
- Untouched AI suggestions never become human findings.
- Corrected AI findings preserve original AI provenance.
- Corrected human findings never inherit the original model score as if it applied to the correction.
- No AI output becomes an autonomous screening/referral decision.

## 4.2 Three confirmation milestones

Underlying milestones remain:

```text
Confirm Image
Confirm DR Grade
Confirm Annotation / Finish image
```

Clinician-facing wording may improve, but audit/persistence semantics remain.

## 4.3 Completeness

Compatible persisted states remain:

```text
NOT_REVIEWED
PARTIALLY_REVIEWED
REVIEWED_NONE_FOUND
REVIEWED_FINDINGS_RECORDED
```

Technical state names may be hidden from the normal UI.

Do not infer completeness from:

- empty AI output;
- empty annotation array;
- opening a panel;
- loading a case;
- displaying model output.

Reviewed-none remains a deliberate human action.

## 4.4 Advanced findings

Advanced remains optional/deferred.

Unopened Advanced:

```text
ADVANCED = NOT_REVIEWED
```

without user action.

Do not invent Advanced negatives.

## 4.5 Source / geometry / provenance

Preserve:

- immutable originals;
- original-image coordinates;
- AI/Human provenance;
- mask/analysis provenance;
- revision/CAS behavior;
- audit history;
- workspace isolation;
- PostgreSQL authority;
- manual operation when AI is unavailable.

## 4.6 Phase boundary

Do not:

- start Phase 3;
- qualify USPEC, PRISM, RETFound, Clef, MONAI, or another model;
- change Model API production semantics;
- authorize hospital data;
- add referral/DME/treatment logic;
- redefine Phase 4 reviewed-negative policy;
- claim production/clinical validation.

---

# 5. External reference study — learn, do not clone

Before visual implementation, perform a bounded interaction-pattern study of:

```text
MONAI Label
OHIF
CVAT
3D Slicer medical-image workflows
current Retinal Review Workbench
```

Study only patterns that may reduce:

- clinician cognitive load;
- clicks;
- text entry;
- page transitions;
- visual search;
- technical vocabulary.

Useful patterns to evaluate include:

- image-first annotation;
- task-specific contextual tools;
- sample-to-sample progression;
- submit/complete after correction;
- model assistance that remains secondary to the clinical task;
- viewer/server separation;
- progressive disclosure of advanced tools.

Do not:

- copy another product pixel-for-pixel;
- copy branding/artwork;
- import radiology/pathology controls that do not help UWF DR;
- replace the current app with MONAI Label/OHIF;
- imply MONAI provides a qualified UWF DR model for this project.

Create a concise internal matrix:

| Pattern | Current Workbench | Reference pattern | Keep / Adapt / Reject | Reason |
|---|---|---|---|---|

---

# 6. Institutional design direction — KKU / Faculty of Medicine

The workstation should be institutionally appropriate without confusing brand with clinical status.

Use separate token families:

```text
Institutional identity
├── university accent
└── medicine/faculty primary

Clinical semantics
├── info
├── success
├── warning
└── danger

Retinal visualization
├── MA
├── HE
├── EX
└── SE
```

`DESIGN.md` already contains the direction:

```text
Medicine Green
Red Soil
semantic status colors
retinal lesion colors
```

P3-0 should formalize these as design tokens rather than spread raw hex values across components.

## 6.1 Official brand verification

Before describing a color/logo as **official**, verify it from authoritative current KKU / Faculty of Medicine material.

- University symbol/color: official KKU source.
- Faculty-specific color/logo: official Faculty source where available.
- If exact Faculty brand values cannot be verified, retain project tokens such as `brand.medicinePrimary` and do not label them “official”.

Institutional color must never by itself mean:

```text
normal
disease
safe
danger
passed
failed
gradable
ungradable
```

Clinical status keeps semantic colors + text/icon cues.

## 6.2 Brand restraint

This is a clinical/research workstation, not a marketing page.

Use identity in the shell and restrained accents. Avoid:

- large ceremonial logos around the viewer;
- marketing banners;
- gradients/glow;
- glassmorphism;
- decorative dashboards.

---

# 7. Thai clinician usability

Prepare the interface for Thai clinical use while retaining internationally recognizable ophthalmic terminology.

Preferred language model:

```text
plain Thai task wording where helpful
+
standard English clinical term / abbreviation where conventional
```

Keep recognizable terms such as:

```text
Mild NPDR
Severe NPDR
PDR
IRMA
NVD / NVE
MA / HE / EX / SE
```

Do not force a translation of every technical ophthalmic term.

Ensure:

- Thai Unicode reviewer names render correctly;
- long Thai labels do not break layout;
- fields do not assume ASCII;
- dates/times remain unambiguous;
- audit timestamps may remain ISO;
- keyboard use works with Thai/English input.

Clinician copy should be:

```text
short
action-oriented
plain
clinically meaningful
```

Avoid primary UI terms such as:

```text
PARTIALLY_REVIEWED
annotation confirmation status
resolver evidence state
record partial review
provider transform identity
```

Technical terms belong in audit/details surfaces.

---

# 8. UX laws

## UX-01 — One dominant forward action
Each task state has one visually dominant next action.

## UX-02 — Image first
The retinal image remains the primary visual object on review/grade/findings surfaces.

## UX-03 — Progressive disclosure
Routine users see routine controls. Advanced/technical controls appear only when requested or required.

## UX-04 — System handles clerical work
Where safe, automatically handle:

- remembered reviewer;
- derived patient/eye evidence;
- save/persistence;
- audit timestamps;
- revision handling;
- current annotation hash;
- next-case navigation;
- mapping clinical actions to internal state.

## UX-05 — Manual only for uncertainty or human judgment
Manual action should exist only for:

- ambiguous context;
- clinician disagreement;
- final clinical decision;
- explicit reviewed-none;
- chosen advanced workflow.

## UX-06 — Do not expose persistence vocabulary
Clinical action → application maps to state.

## UX-07 — No dead-end AI states
AI/mask/explainability unavailable must still allow manual completion.

## UX-08 — Compact, not cramped
Minimal means fewer concepts and better hierarchy, not tiny controls.

## UX-09 — No decorative dashboard behavior
No KPI cards, heavy gradients, sci-fi AI visuals, giant rounded cards, or decorative charts.

## UX-10 — One source of guidance
Do not show a large workflow hint if the same state already has a clear primary CTA.

---

# 9. User-effort budget

These are optimization targets, not clinical validation thresholds.

For a routine case whose context is safely resolved:

```text
manual patient text entry       target: 0
manual eye selection            target: 0
reviewer re-entry               target: 0
technical-state decisions       target: 0
Advanced interactions           target: 0
threshold/preprocess tuning     target: 0
manual navigation after finish  target: 0
```

Human decisions remain:

```text
final grade
finding correction/addition when needed
explicit finish / reviewed-none decision
```

Measure before and after:

```text
clicks per routine case
manual text fields used
route/page transitions
scroll needed to reach primary action
persistent panels
technical terms visible in routine flow
observed completion time
```

Run at least one 10-case continuous workflow using allowed synthetic/public data.

Core question:

> Where does the user stop to interpret the software rather than interpret the retinal image?

Fix in-scope friction before freeze review.

---

# 10. Target information architecture

Converge around:

```text
Worklist
Case Review Workspace
Datasets / workspace data
Models & Audit
Settings
```

Normal labeling path:

```text
Worklist
→ Context
→ Review
→ Grade
→ Findings
→ Finish
→ Next case
```

## 10.1 Optional persistent Case Review Workspace

MAIN may evaluate whether Review → Grade → Findings can share a more persistent case shell so the retinal image stays stable while the task panel changes.

Allowed only if:

- all three confirmations remain explicit;
- backend APIs/persistence remain compatible;
- browser navigation stays predictable;
- deep links are preserved/redirected safely;
- the change materially reduces burden;
- scope remains bounded.

If this creates excessive regression risk, keep existing routes and converge them visually instead.

The UX goal matters more than route consolidation.

---

# 11. Worklist / Confirm Image

The Worklist remains a dense queue, not a dashboard.

Show:

- thumbnail;
- concise patient/eye identity;
- context/modality state;
- review state;
- one obvious action;
- compact active-workspace context.

Avoid technical IDs and multiple equally prominent row actions.

Confirm Image:

- prefill safely supported context;
- expand only unresolved fields;
- remember reviewer;
- keep optional metadata collapsed;
- never overwrite confirmed/manual context.

---

# 12. Review / evidence

Phase 2 mask behavior is frozen.

P3-0 may improve hierarchy:

```text
Original
Analysis
Mask
AI evidence
Explainability
```

Rules:

- Original = reference truth image.
- Mask = processing evidence.
- Explainability = model evidence.
- AI unavailable never blocks manual review.
- technical IDs/provenance should not dominate the image.
- detailed provenance belongs in `Processing details` / `Audit details`.

Do not reopen mask algorithms.

---

# 13. Grade

Normal path remains:

```text
inspect image
→ select grade
→ Confirm grade
```

Clinical label dominates numeric storage value.

Do not add probability interpretation, referral logic, DME logic, or model tuning.

---

# 14. Annotation Editor — required P3-0 refinement

The following are mandatory because they were explicitly deferred by Owner UAT.

## P3-0-ANN-1 — One-row primary toolbar

Current findings controls use too much vertical space.

Desktop target:

```text
Select | Box | More ▾ | Undo | Delete | Lock | Finding [class ▾] | AI | Human
```

Always visible when applicable:

```text
Select
Box
Undo
Delete selected
Finding class
```

Contextual:

```text
Lock / Unlock
```

Compact visibility toggles:

```text
AI
Human
```

Responsive fallback:

```text
>=1280    one row when practical
1024–1279 one row or deliberate compact wrap
tablet    compact two-row arrangement
mobile    wrapped/overflow without hiding required actions
```

Do not violate accessible target sizes merely to force one line.

## P3-0-ANN-2 — More tools = popover / overflow

`More tools` becomes a real contextual popover/menu.

Candidate secondary tools:

```text
Polygon
Point
Circle
```

Other low-frequency controls may move there only if they remain discoverable.

Requirements:

- adjacent to trigger;
- keyboard accessible;
- Escape closes;
- outside click closes safely;
- focus returns to trigger;
- active tool is obvious;
- popup stays inside viewport.

Do not hide Undo in More tools.
Box remains the normal primary drawing tool.

## P3-0-ANN-3 — Contextual geometry help

Do not permanently show polygon instructions when Polygon is inactive.

Examples:

```text
Box     → Drag to draw a box
Polygon → Click points; double-click to finish
Point   → Click to place
Circle  → Drag to size
```

Only show the active tool's concise guidance.

## P3-0-ANN-4 — Remove `Record partial review`

The primary clinician UI must not ask users to manage:

```text
Record partial review
```

If Advanced was never entered:

```text
ADVANCED = NOT_REVIEWED
```

without user action.

If Advanced remains available, use clinical wording:

```text
Advanced findings
Optional
[ Review advanced findings ]
```

If there is no meaningful Advanced workflow yet, a deferred/unavailable explanation is preferable to an artificial state-management button.

Do not set `PARTIALLY_REVIEWED` merely because a panel was opened.

A partial state may arise only from meaningful contract-safe clinical interaction.

Do not invent Advanced reviewed-none semantics.

## P3-0-ANN-5 — Compact completion panel

### Before finish — findings exist

Example:

```text
Complete review
1 Core finding recorded
Reviewer: Test   Change

[ Finish image & next ]
```

### Before finish — no Core human findings

Keep deliberate reviewed-none:

```text
Complete review
No Core findings recorded

Finishing confirms that Core findings were reviewed and none were found.

[ Finish — reviewed none found ]
```

### After completion

Remove pre-completion explanatory paragraphs.

Example:

```text
Review complete
No Core findings recorded
Reviewer: Test

[ Open next image ]
Edit confirmed findings
```

## P3-0-ANN-6 — Remove duplicate next-step guidance

If `Open next image` is the clear CTA, do not also show a large banner telling the user to open the next case from Worklist unless the state is genuinely different.

One state → one dominant guidance path.

## P3-0-ANN-7 — Keep canvas dominant

The compact toolbar should move the retina upward, not shrink it unnecessarily.

At common desktop widths, the first viewport should contain:

- case context;
- primary toolbar;
- substantial retinal image area;
- visible/discoverable completion action.

No giant dead whitespace caused by column mismatch.

---

# 15. Reviewer identity

When a reviewer is remembered:

```text
Reviewer: <name>   Change
```

is preferred.

A full input appears only when:

- no reviewer is available;
- user chooses Change;
- persisted context requires clarification.

Reviewer default remains workstation convenience, not authentication.

---

# 16. State follows clinical action

Adopt this design rule:

```text
clinical action
→ application maps to internal state
```

Examples:

```text
Finish — reviewed none found
→ CORE = REVIEWED_NONE_FOUND

Finish image & next with active Core findings
→ CORE = REVIEWED_FINDINGS_RECORDED

Advanced never entered
→ ADVANCED = NOT_REVIEWED
```

Mapping must remain explicit and tested even if enum names are hidden.

---

# 17. Design-system freeze

Reduce ad hoc styling.

Freeze token layers for:

```text
primitive colors
semantic colors
component colors
retinal overlay colors
spacing
radius
typography
control heights
focus ring
viewer background
```

Prefer intent-based names:

```text
brand.universityAccent
brand.medicinePrimary
action.primary
surface.canvas
surface.panel
status.info
status.success
status.warning
status.danger
```

Retinal lesion palette remains separate from brand/status.

Typography priorities:

```text
Thai/Latin legibility
clinical density
stable numeric alignment
clear hierarchy
no oversized marketing headings
```

Do not introduce a new font dependency solely for branding.

---

# 18. Accessibility freeze

Target WCAG 2.2 AA where applicable.

Validate:

- contrast;
- focus-visible;
- keyboard operation;
- buttons/dialogs/popovers;
- disabled states;
- local error association;
- no color-only meaning;
- reduced motion;
- readable image context;
- responsive zoom.

For `More tools`:

- correct menu/popover semantics;
- keyboard navigation;
- Escape close;
- focus return;
- active tool not conveyed by color alone.

---

# 19. Responsive / workstation audit

P3-0 must include visual evidence at:

```text
1920 × 1080
1440 × 900
1366 × 768
1280 × 720
1024 × 768
representative mobile width
```

Verify:

- no page horizontal scroll;
- viewer remains useful;
- primary action is discoverable;
- toolbar does not overlap;
- popover stays in viewport;
- no giant dead whitespace;
- Thai/English labels wrap safely;
- supporting panel does not crush image.

---

# 20. Browser UX audit

Playwright and Stagehand are locally available according to Phase 2 closeout evidence.

Use as local QA tools, not automatically as product/runtime dependencies.

## Playwright

Prefer deterministic evidence:

- viewport screenshots;
- keyboard flow;
- overflow checks;
- focus checks;
- 10-case continuous flow;
- final browser screenshots.

## Stagehand

May be used for exploratory agent-assisted usability inspection.

It does not replace deterministic tests or Owner UAT.

Do not commit external credentials/secrets.

---

# 21. Surfaces to audit

At minimum:

```text
Worklist
Confirm Image
Review
Clinician Review / Grade
Annotation Editor
Annotation Editor completed state
Datasets
Models & Audit
Settings
```

Spend most effort on the normal clinician path. Do not visually refactor every secondary page merely for symmetry.

---

# 22. Workstreams

## P3-0A — Current-state evidence

Before coding:

- baseline screenshots;
- current route/task map;
- burden baseline;
- deferred Phase 2 UAT findings.

## P3-0B — Reference study

Create Keep / Adapt / Reject matrix for MONAI Label / OHIF / CVAT / current app.

## P3-0C — Institutional design/token freeze

- audit current tokens;
- verify institutional source material;
- separate brand/status/lesion;
- centralize changed-surface tokens.

## P3-0D — Core flow convergence

Optimize:

```text
Worklist
Confirm Image
Review
Grade
Findings
Finish
Next
```

Remove repeated inputs, duplicate guidance, and technical vocabulary.

## P3-0E — Annotation Editor convergence

Implement P3-0-ANN-1 through ANN-7.

Highest-priority visible workstream.

## P3-0F — Thai/copy audit

- reduce internal terminology;
- verify Thai Unicode/long-label resilience;
- keep clinical terms recognizable;
- errors remain actionable.

## P3-0G — Accessibility/responsive

Deterministic browser tests + manual review.

## P3-0H — 10-case continuous audit

Collect:

```text
clicks
manual fields
route transitions
scroll friction
duplicate instructions
unexpected technical concepts
```

Improve until no in-scope BLOCKER/REQUIRED FIX remains.

## P3-0I — Documentation/freeze evidence

Update affected clinician/developer docs and final screenshots/evidence.

Phase 3 remains NOT_STARTED.

---

# 23. Allowed scope

May change:

- React composition;
- navigation presentation;
- spacing/layout;
- semantic theme tokens;
- labels/microcopy;
- progressive disclosure;
- popover/menu organization;
- responsive behavior;
- compact reviewer presentation;
- non-semantic client convenience state;
- browser tests;
- affected documentation.

A small additive backend/UI adaptation is allowed only when necessary to preserve existing semantics under a simpler UI and remains backward compatible.

---

# 24. Prohibited scope

Do not:

- change ICO grading semantics;
- redefine Core findings;
- create new Advanced taxonomy;
- redefine reviewed-negative policy;
- change/train models;
- adopt MONAI runtime here;
- change Model API for a new model;
- alter source authorization;
- authorize hospital data;
- add new clinical outcomes;
- replace PostgreSQL architecture;
- replace the app with MONAI Label/OHIF;
- create authentication;
- redesign Phase 4 export.

---

# 25. Regression matrix

| Contract | Required proof |
|---|---|
| Confirm Image | resolved/unresolved evidence + manual override safety |
| Reviewer | remembered value + Change path |
| DR grade | confirm/reopen/edit without drift |
| Findings | Box create/edit/delete + legacy geometry display |
| AI ROI | untouched/correct/reject provenance |
| Finish with findings | findings-recorded + annotation confirmation |
| Finish without findings | explicit reviewed-none + no fabricated negative |
| Advanced unopened | stays NOT_REVIEWED |
| Annotation hash | edit invalidates confirmation |
| Mask unavailable | manual path remains |
| Candidate mask | review-only remains |
| AI unavailable | full manual case completes |
| PostgreSQL | revision/CAS/workspace isolation preserved |
| Original image | immutable |
| Coordinates | original-image pixels |
| Restart | state survives |
| Errors | no raw exception/object in clinician UI |

---

# 26. Validation

Use focused tests while iterating.

Before review run applicable full validation:

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

Run repository docs QA.

If PostgreSQL is available, run restart/persistence/CAS evidence.

If unavailable, do not claim it was retested in P3-0; preserve/report the Phase 2 evidence boundary honestly.

---

# 27. Visual acceptance

A candidate is not ready merely because tests pass.

Must demonstrate:

## Annotation toolbar
- coherent compact toolbar;
- More tools popover;
- Box primary;
- Undo/Delete easy;
- finding class obvious;
- keyboard operation.

## Completion
- no `Record partial review` primary control;
- Advanced clearly optional;
- compact completion panel;
- reviewed-none remains explicit;
- completed state removes unnecessary copy;
- one dominant next action.

## Layout
- no giant dead whitespace;
- image remains primary;
- normal page feels like a workstation, not a form;
- controls do not overpower image.

---

# 28. Self-audit mandate

After the first coherent candidate, MAIN performs a complete local P3-0 self-audit.

Evaluate as a clinician workstation:

```text
functional correctness
clinical semantic preservation
manual burden
visual hierarchy
duplicate guidance
technical terminology leakage
keyboard path
responsive behavior
Thai/English resilience
error states
AI-off flow
restart/persistence where available
```

MAIN may fix all in-scope `BLOCKER` and `REQUIRED FIX` findings without owner input.

Stop only if the fix would alter:

- clinical meaning;
- frozen persistence/provenance;
- privacy/security;
- hospital-data authorization;
- Phase 3/4 scope;
- official institutional brand use that cannot be verified safely.

---

# 29. Review policy

Use:

```text
one bounded IMPLEMENT stream
→ local self-audit/improvement
→ one exact-candidate independent REVIEW
→ fix BLOCKER / REQUIRED FIX
→ changed-diff re-review only
```

Finding classes:

```text
BLOCKER
REQUIRED FIX
NON-BLOCKING / DEFER
```

Do not create a broad review loop for every visual detail.

If reviewer independence is weakened by local account infrastructure, report it honestly.

---

# 30. Git/worktree policy

Follow `AGENTS.md`.

Expected baseline:

```text
f288ae5e8a527f124aaa99eedc6f3d6f7a3e32cb
```

Suggested branch:

```text
feat/pre-phase3-clinical-ux-freeze
```

Implementation must be in a bounded feature worktree, not application writes directly on main.

After acceptance:

```text
merge
→ main validation
→ frontend build on authoritative main
→ push origin/main
→ remove feature worktree/branch
→ refresh Brain
```

---

# 31. Efficiency rule

Be thorough without repeating Phase 2 orchestration cost.

- Audit before editing.
- One coherent implementation stream.
- If delegated worker transport fails before useful edits, MAIN may implement directly in the bounded worktree.
- Focused tests while iterating.
- Full validation once stable.
- One substantive independent review.
- Do not reopen accepted Phase 2 findings without regression evidence.
- Do not polish indefinitely after acceptance criteria are met.

---

# 32. Owner UAT

After integration, stop before Phase 3.

## UAT-A — 10-case continuous flow

Ask:

- Did I type anything the system already knew?
- Did I manage any state the system should manage?
- Did I need to scroll to find the next action?
- Did I see technical terms that did not help the clinical decision?
- Did I ever wonder what to click next?

## UAT-B — Annotation toolbar

Verify Select / Box / Undo / Delete / Finding are coherent.

Open More tools and verify popup behavior.

## UAT-C — Advanced

Do not enter Advanced.

Core completion must remain normal.

No `Record partial review`.

## UAT-D — reviewed-none

No Core finding case remains explicit and safe.

## UAT-E — target workstation resolution

Inspect the actual deployment/owner workstation resolution.

## UAT-F — institutional design

Result should feel appropriate for:

```text
Faculty of Medicine
Khon Kaen University
clinical/research workstation
```

without decorative branding or color-semantic confusion.

---

# 33. Completion state

Stop at:

```text
PRE-PHASE 3 CLINICAL UX FREEZE READY_FOR_OWNER_UAT
```

Authoritative states remain:

```text
Phase 1 = DONE
Phase 2 = DONE
Phase 3 = NOT_STARTED
Phase 4 = NOT_STARTED
Phase 5 = NOT_STARTED
```

Do not automatically start Phase 3.

After Owner UAT acceptance, use a documentation-only freeze closeout before Phase 3 authorization.

---

# 34. Required receipt

The candidate evidence record is maintained in `PRE_PHASE3_CLINICAL_UX_FREEZE_EVIDENCE.md`. It records source/test evidence separately from browser and 10-case checks that remain `NOT_RUN` until an authorized workstation runtime is available.

Return:

```text
Starting SHA:
Candidate SHA:
Final main SHA:

Reference study:
- patterns reviewed:
- Keep/Adapt/Reject summary:

User-effort baseline:
- clicks/case:
- manual fields/case:
- route transitions:
- scroll friction:

Final user-effort:
- clicks/case:
- manual fields/case:
- route transitions:
- scroll friction:

Institutional design:
- authoritative sources verified:
- brand tokens:
- clinical-status separation:
- lesion palette preserved:

Annotation Editor:
- one-row toolbar:
- More tools popover:
- contextual help:
- Record partial review removed:
- Advanced default:
- completion panel:
- duplicate guidance:
- image dominance:

Thai/clinical UX:
- internal terminology removed:
- Thai/English resilience:
- reviewer behavior:

Responsive:
- 1920x1080:
- 1440x900:
- 1366x768:
- 1280x720:
- 1024x768:
- mobile:

Accessibility:
- keyboard:
- focus:
- contrast:
- popover:
- reduced motion:

Regression:
- Confirm Image:
- grade:
- findings:
- AI provenance:
- reviewed-none:
- annotation hash:
- AI-off/manual:
- restart/persistence:
- PostgreSQL/CAS if available:

Validation:
- backend:
- frontend:
- Ruff:
- typecheck:
- build:
- root smoke:
- docs QA:
- git diff --check:
- Playwright/browser:

10-case continuous audit:
Self-audit:
Independent review:
Required fixes:

Known limitations:

Brain:
main == origin/main:
clean worktree:
feature worktree/branch removed:

Phase 2:
DONE

Phase 3:
NOT_STARTED

Owner UAT:
READY

Final marker:
PRE-PHASE 3 CLINICAL UX FREEZE READY_FOR_OWNER_UAT
```

---

# 35. Freeze decisions carried into Phase 3

After Owner approval, Phase 3 treats these as frozen unless a real model-integration conflict exists:

```text
clinical page hierarchy
primary interaction patterns
institutional token system
brand/status/lesion separation
annotation toolbar pattern
progressive disclosure
one-primary-action rule
reviewer compaction
Advanced optional behavior
internal-state hiding
responsive baseline
accessibility baseline
```

Phase 3 model evidence must fit this workstation contract.

The workstation should not become progressively more complicated merely because more model outputs become available.

> The model adapts to the clinical workstation; the clinician should not have to adapt to the model implementation.

---

# 36. Future Phase 3 note

P3-0 deliberately does not adopt MONAI.

After the UX freeze, Phase 3 should separately evaluate MONAI as a medical-AI engineering foundation:

```text
Retinal Review Workbench
        ↓
Model API
        ↓
MONAI transforms / inference / Bundle candidate
        ↓
qualified UWF grading/localization candidates
```

That is a model-engineering decision and must remain separate from this UX freeze.

---

# 37. Reference note

Reference material for this specification includes:

- current Retinal Review Workbench repository and accepted Phase 2 evidence;
- Project MONAI core;
- Project MONAI Label and its medical-viewer workflows;
- OHIF / CVAT / 3D Slicer interaction patterns;
- official Khon Kaen University material governing university symbols/identity.

Exact institutional brand values/logo use must be verified from current authoritative KKU / Faculty of Medicine material before being described as official.

# End — P3-0 Clinical UX & Design System Freeze
