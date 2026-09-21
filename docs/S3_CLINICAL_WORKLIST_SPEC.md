# S3 Clinical Worklist Specification

**Status:** Normative milestone specification  
**Milestone:** S3 — Clinical Worklist  
**Project:** DR Support Screening POC

## 1. Purpose

S3 turns the existing Worklist into a clinician-friendly queue for reviewing and organizing retinal images while preserving the compact PRE-S3 layout.

The Worklist must help the clinician answer:

1. Which image/case am I looking at?
2. Which patient and eye does it belong to?
3. Has AI analysis been run?
4. Has clinician review been completed?
5. What action is needed next?

S3 consumes the frozen S2A1 admission and S2A2 patient/eye contracts. It must not reimplement admission, OCR, identity resolution, or AI inference logic.

Dataset collection/review remains the primary product objective.

---

## 2. Frozen dependencies

Do not change the semantics of:

- S1 viewer;
- S2 Workspace Manager;
- S2A1 image admission and inference guard;
- S2A2 patient/eye resolver and audit history;
- PRE-S3 Model Gateway;
- RETFound / PRISM-DR;
- CVAT;
- annotation geometry/provenance;
- original-image immutability.

If S3 requires changing a frozen contract, STOP and report the conflict.

---

## 3. Worklist density budget

The primary table remains:

```text
IMAGE | PATIENT / EYE | AI RESULT | REVIEW | ACTION
```

Hard UX limits:

- maximum 5 primary columns;
- no horizontal scrolling at desktop width >=1280 px;
- filename never wraps;
- long filename uses ellipsis + full hover/focus tooltip;
- no internal image ID in the primary queue;
- ideally 0–2 badges per row;
- maximum 2 permanently visible row actions;
- no multi-field inline forms;
- no raw enums/reason codes;
- normal states should not consume permanent badges/columns.

Use exception-driven UI:

```text
normal state        -> quiet/minimal
action required     -> visible
technical detail    -> Details/Audit
```

Do not convert the Worklist to large cards.

---

## 4. Core Worklist views

S3 supports two presentation modes using the same underlying queue.

### 4.1 Cases view

Flat image/case queue.

Recommended for:

- quick review;
- filenames;
- unresolved cases;
- operational scanning.

Each row uses the frozen 5-column layout.

### 4.2 Patients view

Group images by `patient_key`, then by eye.

Example:

```text
P00014
├─ Left
│  ├─ image_01.jpg
│  └─ image_02.jpg
└─ Right
   └─ image_03.jpg
```

Unlinked images appear in a dedicated group:

```text
Patient not linked
```

Unknown laterality remains under the patient:

```text
P00014
└─ Eye not confirmed
```

Patient grouping is organizational only. It must not create or infer new identity.

Do not duplicate the same image into multiple groups.

A compact segmented control may switch:

```text
Cases | Patients
```

Avoid large dashboard navigation cards.

---

## 5. Worklist toolbar

Use one compact toolbar above the table.

Recommended controls:

```text
[Search________________] [Filters] [Sort] [Cases | Patients]
```

Do not add many permanent filter chips across the page.

### Search

Search may match:

- filename;
- pseudonymous patient key.

Search must not depend on raw PHI or OCR text.

### Filters

Use a compact popover/drawer.

Useful filter categories:

#### Readiness
- All
- Needs patient / eye confirmation
- Needs image review
- Ready

#### Review
- Pending
- Reviewed
- Excluded

#### AI
- Analyzed
- Not analyzed
- AI unavailable

Filters must use existing stored/effective state rather than invent parallel status fields.

### Sort

Non-clinical operational sorts only, for example:

- Patient / eye;
- Filename;
- Review status;
- Recently updated.

Do not implement medical-severity prioritization in S3.

---

## 6. IMAGE cell

Display:

```text
[thumbnail] filename.jpg
```

Rules:

- one line;
- ellipsis;
- fixed/max width;
- tooltip with complete filename;
- no internal image ID.

Normal admitted images need no admission badge.

Exception examples:

```text
Needs image review
Cannot analyze
```

If an image needs admission action, expose one compact corrective action through the row/action menu or focused readiness dialog.

Do not restore the large admission form inside AI Review.

---

## 7. PATIENT / EYE cell

Resolved automatic:

```text
P00014 · Left
Auto-linked    [Edit]
```

Clinician-confirmed/corrected, when provenance supports distinction:

```text
P00014 · Left
Confirmed      [Edit]
```

Unresolved:

```text
Patient not linked
[Link patient]
```

or:

```text
P00014 · Eye not confirmed
[Confirm eye]
```

Editing must use the existing S2A2 resolver API and audit history.

Resolved values remain editable.

Do not create a parallel patient assignment path.

---

## 8. AI RESULT cell

Examples:

```text
Grade 2
Not analyzed
AI unavailable
```

Do not show confidence as calibrated clinical probability.

Do not add a separate Analysis Status column.

If AI is unavailable, local dataset/review workflows remain usable.

---

## 9. REVIEW cell

Show only effective clinician-review state:

```text
Pending review
Reviewed
Needs annotation
Escalated
```

Exact mapping must derive from existing clinician review/annotation state.

Avoid duplicating detailed reviewer names/timestamps in every row.

Detailed audit belongs in Review / Models & Audit.

---

## 10. ACTION cell

Primary:

```text
Review
```

Secondary:

```text
⋯
```

The overflow menu may include context-relevant actions such as:

- Edit patient / eye;
- Resolve image readiness;
- Exclude from queue;
- Restore to queue.

Do not show irrelevant actions.

Queue exclusion remains reversible and non-destructive.

System-blocked admission and clinician-excluded queue state are distinct.

---

## 11. Focused readiness resolution

The Worklist owns case readiness, but it must not become a form-heavy page.

When corrective input is needed, open a focused dialog/drawer.

Possible tasks:

```text
Patient / eye
Image readiness
```

Each focused surface should show only fields required for that task.

Do not combine patient resolver, admission review, clinician grade, and annotation editing into one modal.

After a correction:

- persist through the existing frozen API;
- refresh only the affected row where practical;
- preserve audit history;
- return the clinician to the queue.

---

## 12. Attention summary

A small text summary is allowed, for example:

```text
24 cases · 3 need attention
```

Do not add KPI cards.

`Need attention` may include operationally unresolved states such as:

- patient/eye confirmation needed;
- image readiness review needed.

Do not interpret disease severity as queue urgency.

---

## 13. Review navigation

Clicking `Review` opens AI Review / clinician review for that case.

AI Review remains focused on:

- retinal viewer;
- Analyze;
- AI outputs;
- clinician review;
- Edit annotations.

Patient/eye and admission appear there only as compact read-only context or blocked guidance.

Do not move intake forms back into AI Review.

---

## 14. Empty and filtered states

No Workspace images:

```text
No images in this workspace
Add images to the input folder, then scan the folder.
```

No search/filter results:

```text
No cases match these filters.
Clear filters
```

Patients view with unlinked images must still make them discoverable.

---

## 15. State ownership

S3 should compute display/group/filter behavior from existing authoritative data:

- admission metadata;
- patient/eye resolver data;
- queue state;
- AI results;
- clinician review;
- human annotations.

Do not introduce redundant persistent status fields solely for UI convenience unless clearly necessary.

Prefer derived selectors/view models in the frontend/backend presentation layer.

---

## 16. Performance

S3 must remain usable with substantially more than demo-sized queues.

At minimum:

- avoid unnecessary full-page reload after a single row action;
- stable row keys;
- deterministic sorting;
- avoid decoding full-resolution images merely to render queue rows if thumbnails/previews already exist;
- do not trigger model inference while listing/filtering/grouping.

Large-folder scan optimization remains a separate known performance concern unless explicitly pulled into scope.

---

## 17. Accessibility

- keyboard-accessible search/filter/actions;
- tooltip content available on focus, not hover only;
- icon-only actions require accessible labels;
- color must not be the only status signal;
- disabled actions explain why when clarification is useful.

---

## 18. S3 non-scope

Do not implement:

- OCR changes;
- Typhoon integration changes;
- production PHI identity vault;
- DICOM/PACS;
- dataset export/manifest finalization;
- model benchmarking;
- model fine-tuning;
- XAI/heatmaps;
- dynamic lesion taxonomy registry;
- medical-severity queue prioritization;
- bulk destructive operations.

These belong to later milestones/future work.

---

## 19. Branch/worktree guardrail

Follow `AGENTS.md`.

Before any implementation write report:

```text
repository root
active worktree path
current branch
current HEAD
git status --short --branch
```

If the implementation shell is on `main`, STOP.

Create/switch to the bounded feature worktree before editing.

Recommended branch:

```text
feat/s3-clinical-worklist
```

If implementation is split, freeze shared presentation/API behavior before parallel branches.

Required lifecycle:

```text
clean main
 -> feature worktree
 -> implement/test
 -> commit + push feature
 -> integration review
 -> merge into main
 -> validate main
 -> rebuild frontend/dist on main
 -> push main
 -> remove worktree
 -> delete local + remote feature branch
```

Do not patch implementation directly on main.

---

## 20. Validation

Focused S3 tests must cover:

- 5-column Worklist remains intact;
- no horizontal scroll at >=1280 px;
- filename ellipsis + full tooltip/focus title;
- Cases/Patients view switching;
- patient grouping;
- Left/Right/Unknown grouping;
- unlinked group;
- search by filename;
- search by pseudonymous patient key;
- readiness/review/AI filters;
- non-clinical sorts;
- resolved Patient/Eye remains editable;
- focused resolver action uses existing API;
- admission exception can route to focused readiness action;
- exclude/restore remains reversible;
- AI Review navigation remains correct;
- no raw enums in primary clinician UI.

Regression:

- backend tests;
- Ruff;
- frontend tests;
- typecheck;
- production build;
- root smoke;
- S1/S2/S2A1/S2A2/PRE-S3 relevant regression.

After merge, rebuild `frontend/dist` from authoritative main before owner/browser smoke.

---

## 21. Acceptance criteria

S3 is complete when:

1. Clinician can use Cases and Patients views.
2. Patient grouping reflects existing S2A2 assignments only.
3. Search/filter/sort do not increase table density.
4. Worklist still uses only five primary columns.
5. No horizontal scrolling is needed on normal desktop.
6. Patient/eye and readiness issues are directly actionable without inline form clutter.
7. Normal states remain visually quiet.
8. Review action remains immediately visible.
9. Queue exclusion remains reversible/non-destructive.
10. AI unavailable does not block local review/dataset workflow.
11. No frozen S1/S2/S2A1/S2A2/PRE-S3 semantics are weakened.
12. Owner browser smoke confirms the queue is understandable without technical explanation.
13. Main is clean/synchronized and temporary branch/worktree is deleted.
