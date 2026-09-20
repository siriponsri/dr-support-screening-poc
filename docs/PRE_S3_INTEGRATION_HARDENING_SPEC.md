# PRE-S3 Integration Hardening Specification

**Status:** Normative  
**Milestone:** PRE-S3  
**Project:** DR Support Screening POC

## 1. Goal

Harden the clinician-facing app before S3 without reopening frozen S1/S2/S2A1/S2A2 semantics.

This milestone must:

- simplify the Worklist so no horizontal scroll is needed on normal desktop;
- remove legacy synthetic/public demo cases from normal clinician startup;
- compact Workspace Settings;
- add provider-neutral AI Model Connection settings;
- leave reusable Worklist components ready for S3.

Dataset collection/review is the primary product. AI inference is optional assistance.

---

## 2. Frozen boundaries

Do not change:

- S1 viewer interaction/coordinates;
- S2 Workspace lifecycle;
- S2A1 admission semantics/inference guard;
- S2A2 patient/eye resolver semantics/audit history;
- RETFound / PRISM-DR model identity or result contracts;
- CVAT behavior;
- SQLite review-storage authority;
- original-image immutability.

If implementation conflicts with frozen behavior, STOP and report.

---

## 3. Worklist UX

Use a formal table/list, not card-based UI.

Primary columns:

```text
IMAGE | PATIENT / EYE | AI RESULT | REVIEW | ACTION
```

At desktop width >=1280 px:

- no horizontal scrollbar;
- ACTION always visible;
- do not reduce font size merely to fit;
- hide/collapse secondary text before primary clinical information.

### IMAGE

Show thumbnail + filename.

Do not show long internal `image_id` in the primary queue.

Filename rules:

- one line only;
- fixed/max cell width;
- ellipsis when long;
- never wrap;
- never auto-expand the table;
- hover/focus tooltip shows full filename.

Admission is exception-driven:

- normal accepted case: no permanent admission badge/column;
- attention needed: short clinician-safe note inside IMAGE;
- raw enums/reason codes stay hidden.

Examples:

```text
fundus_01.jpg
```

```text
unknown_photo.jpg
Needs review
```

```text
broken.jpg
Cannot analyze
```

### PATIENT / EYE

Resolved:

```text
P00014 · Left
```

Incomplete states must be actionable:

```text
Patient not linked
[Link patient]
```

```text
P00014 · Eye not confirmed
[Confirm eye]
```

Use a compact popover/drawer/modal. Do not put multiple dropdowns in every table row.

All changes must use the frozen S2A2 resolver/audit contract.

### AI RESULT

Combine prediction and analysis state:

```text
Grade 2
Not analyzed
AI unavailable
```

Do not keep a separate Analysis Status column if it duplicates this.

### REVIEW

Show effective clinician-review state only:

```text
Pending review
Verified
Needs annotation
Escalated
```

### ACTION

Keep:

```text
[Review] [⋯]
```

Overflow may include:

```text
Exclude from queue
```

This must not delete data.

When excluded:

- image/case/annotations/history remain;
- state is distinct from admission blocking;
- row may be visually muted;
- Review becomes disabled or replaced with `Excluded`;
- blocked visual state must be obvious;
- hover/focus tooltip explains why;
- overflow provides `Restore to queue`.

Prefer `Exclude from queue`, not ambiguous `Disable`.

---

## 4. Progressive disclosure

Move these out of the primary Worklist:

- internal image ID;
- admission/resolver reason codes;
- audit timestamps;
- model/runtime diagnostics;
- technical warning strings.

They belong in Case Review, Models & Audit, or explicit Details.

---

## 5. Legacy fixture isolation

Normal `START.cmd` / `/app/` must not automatically inject:

- `SYNTH_001`;
- old public sample cases;
- legacy demo cases;
- hard-coded DR-DEMO filenames.

With an active Workspace, show Workspace cases only.

With no images:

```text
No images in this workspace
Add images to the input folder, then scan the folder.
```

Do not blindly delete fixtures required by tests. Isolate test-only fixtures behind explicit test setup/configuration.

---

## 6. Workspace Settings compaction

Keep Saved Workspaces formal but denser.

Target shape:

```text
WS03_IDENTITY_PREVIEW                  [Switch] [Edit] [Delete]
WS03 – Identity Preview
Input    C:\...\WS03_IDENTITY_PREVIEW
Output   C:\...\OUTPUT
Storage  SQLite · C:\...\database.sqlite
```

Requirements:

- reduce row spacing;
- fixed metadata-label width;
- compact monospace paths;
- single-line ellipsis;
- full path on hover/focus;
- no path wrapping;
- no card expansion from long paths.

Copy controls must be less visually noisy.

Preferred:

- show copy on hover/focus, or
- retain copy only for Input and Storage.

Sidebar remains name + optional note + Manage workspace only.

---

## 7. Model Gateway

Settings adds:

```text
AI Model Connection
```

Fields:

```text
Connection name
Model API URL
Access token (optional)
[Test connection] [Save]
```

Clinician-safe states:

```text
Connected
Not configured
Unavailable
Connection could not be verified
```

When connected:

```text
RETFound    Ready
PRISM-DR    Ready
```

Do not make architecture/UI Lightning-specific.

The same connection must support:

- Lightning-hosted Model API;
- hospital LAN GPU server;
- local GPU API.

Keep existing API contract:

```text
GET  /health
GET  /v1/models
POST /v1/predict/dr
POST /v1/predict/lesions
```

### Secret rules

Token is backend-only.

Never store/return/log raw token in:

- localStorage/sessionStorage;
- Workspace SQLite;
- React state persisted across reload;
- API responses;
- logs.

Frontend may receive only:

```text
token_configured: true|false
```

Environment-variable configuration remains supported.

Do not invent custom reversible encryption with its key stored beside the secret.

### Connection lifecycle

Preferred:

```text
Test connection
 -> GET /health
 -> GET /v1/models
 -> Save
 -> validated provider configuration
 -> atomic provider swap
```

Requirements:

- no restart where practical;
- failed test/save preserves prior working configuration;
- missing connection does not block app startup;
- no local RETFound/PRISM fallback in review profile;
- AI failure never breaks Workspace/admission/resolver/annotation/review.

---

## 8. START.cmd

`START.cmd` is the single normal Windows launcher.

Expected:

```text
START.cmd
 -> clinician workstation starts
 -> no hard-coded image required
 -> no Model API required
 -> Workspace/review works

Model Gateway configured
 -> AI available

Not configured
 -> AI unavailable
 -> local dataset/review workflow still works
```

Do not restore `START_DEMO.cmd` as a normal owner workflow.

---

## 9. S3 preparation only

Reusable Worklist presentation components may be created, e.g.:

```text
WorklistTable
ImageCell
PatientEyeCell
AIResultCell
ReviewStatusCell
ReviewActionCell
```

Do not implement S3 yet:

- patient-grouped sections;
- search;
- filters;
- queue prioritization;
- eye-group navigation.

---

## 10. Branch/worktree guardrail

Follow `AGENTS.md`.

Before ANY implementation write, report:

```text
repository root
worktree path
branch
HEAD
git status --short --branch
```

If the implementation shell is on `main`, STOP.

Create/switch to the bounded feature worktree first.

Creating a branch elsewhere while continuing to edit the main worktree is prohibited.

Recommended branches:

```text
feat/pre-s3-worklist-ux
feat/pre-s3-fixture-isolation
feat/model-gateway
```

Workspace Settings compaction may share the UX branch.

Required lifecycle:

```text
implement on feature branch
 -> test
 -> commit + push feature
 -> integration review
 -> merge into main
 -> validate main
 -> rebuild frontend/dist on main when needed
 -> push main
 -> delete worktree
 -> delete local + remote feature branch
```

If `origin/main` advances, integrate it into the feature branch and resolve/test there.

Do not choose a version merely because its commit is newer.

Post-merge source fixes require a new bounded `fix/...` branch.

---

## 11. Validation

Worklist:

- no horizontal scroll at >=1280 px;
- ACTION always visible;
- long filename never wraps or expands column;
- full filename available on hover/focus;
- internal image ID absent from primary queue;
- Patient/Eye incomplete state has direct corrective action;
- exclude/restore is reversible and distinct from admission blocking.

Fixtures:

- normal `/app/` has no legacy synthetic/public cases;
- active Workspace shows appropriate Workspace cases only;
- empty Workspace has useful empty state;
- test fixtures remain deterministic.

Workspace Settings:

- visibly reduced vertical density;
- paths remain one line;
- copy affordances are less noisy.

Model Gateway:

- app starts with no Model API;
- valid connection can be tested/saved;
- invalid/unreachable endpoint fails gracefully;
- optional token works when required;
- raw token never reaches frontend/Workspace DB/logs;
- failed reconnect preserves previous valid connection;
- no local model loading in review profile.

Regression:

- backend tests;
- Ruff;
- frontend tests;
- typecheck;
- production build;
- root smoke;
- S1/S2/S2A1/S2A2/CVAT relevant regression.

After frontend merge, rebuild `frontend/dist` from authoritative main before owner/browser smoke.

---

## 12. Acceptance criteria

PRE-S3 is complete when:

1. Worklist uses IMAGE / PATIENT-EYE / AI RESULT / REVIEW / ACTION only.
2. No horizontal scroll is required on normal desktop.
3. Long filenames stay single-line with ellipsis + tooltip.
4. Patient/Eye unresolved states provide direct corrective actions.
5. Clinicians can exclude/restore queue cases without deleting data.
6. Legacy synthetic/public cases do not leak into normal startup.
7. Workspace Settings is materially more compact.
8. Model URL + optional token can be configured in Settings.
9. Secrets remain backend-only.
10. App works for dataset/review with no AI server.
11. No local model fallback occurs on review workstation.
12. Worklist components are ready for S3 extension.
13. Frozen S1/S2/S2A1/S2A2 semantics remain intact.
14. `main` is clean/synchronized and temporary branches/worktrees are deleted.
