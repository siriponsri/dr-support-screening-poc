# AGENTS.md

## Repository basics

- `dr_support/`: Python/FastAPI backend.
- `frontend/`: React/Vite clinician UI.
- `web/`: legacy static UI.
- `tests/`: backend/API/browser/root smoke tests.
- `docs/`: normative specs, runbooks, architecture notes.
- `local-state/`: runtime state only; never treat as source data.

## Commands

From repo root:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m ruff check dr_support tests
npm ci && npm test
```

React:

```bash
cd frontend
npm ci
npm test
npm run typecheck
npm run build
```

Use focused tests while iterating, then run the required full validation before handoff.

## Coding rules

- Python: 4 spaces, existing Ruff config, PEP 8 naming.
- TypeScript: strict mode, `PascalCase` components, `camelCase` functions/variables.
- Prefer existing contracts, services, theme tokens, and Lucide icons.
- Make the smallest compatible change; do not refactor unrelated code.

## Security and privacy

This is a clinician-support/public-synthetic research POC.

Never commit or expose:

- tokens/passwords/API keys;
- CVAT credentials;
- model weights;
- private patient data / PHI;
- local Workspace databases;
- runtime secret files.

Secrets stay server-side. Never store raw secrets in React, localStorage,
sessionStorage, Workspace SQLite, logs, or API responses.

---

# Branch and worktree policy

`main` is the authoritative integration/orchestration branch.

Feature/fix/refactor/UI/backend implementation MUST NOT be written directly on
`main` unless the owner explicitly authorizes a documentation-only or
integration-only change.

## Mandatory branch write gate

Before the first implementation write, report and verify:

```text
repository root
current worktree path
current branch
current HEAD
git status --short --branch
```

If the active implementation shell is on `main`, STOP.

Create/switch to the approved bounded feature/fix branch and its worktree first.

A branch existing elsewhere does not authorize editing `main`.

## Required lifecycle

```text
clean synchronized main
  -> create bounded branch/worktree
  -> implement only in that worktree
  -> focused tests
  -> required full branch validation
  -> commit + push feature branch
  -> integration review
  -> merge into main
  -> validate main
  -> rebuild frontend/dist on main if frontend changed
  -> push main
  -> delete feature worktree
  -> delete local + remote feature branch
```

If `origin/main` advances while the feature is in progress, integrate the latest
main into the feature branch, resolve/test there, then continue.

Do not choose a version merely because its commit is newer.

If a bug is found after merge, create a bounded `fix/...` branch. Do not patch
implementation files directly on `main`.

## Unexpected changes on main

If `main` contains an unexpected modification, STOP and inspect it.

At minimum:

```bash
git status --short
git diff -- <file>
git diff --stat
git log -5 --oneline -- <file>
```

Do not reset, restore, checkout, stash, clean, overwrite, or absorb the change
without owner confirmation.

## Branch naming

Prefer:

```text
feat/<bounded-task>
fix/<bounded-task>
docs/<bounded-task>
```

Avoid vague long-lived branches such as `dev`, `new`, `test`, or `temp`.

---

# Parallel work

Parallel work is allowed only after shared contracts are sufficiently frozen.

Before parallelizing:

- define API/schema/data contracts;
- identify file ownership;
- avoid overlapping migrations/shared contracts;
- use one worktree per branch.

Do not let separate agents invent competing shared types, schemas, constants,
or theme tokens.

---

# Merge gate

Do not auto-merge just because branch tests pass.

Merge only when:

- branch/worktree is clean;
- required tests pass;
- implementation remains in scope;
- no unexpected API/schema/model/clinical-workflow drift exists;
- no secrets/PHI/model weights/local-state files are included;
- milestone acceptance criteria are satisfied.

If a conflict touches shared contracts, DB schema/migrations, model behavior,
admission semantics, patient/eye semantics, annotation provenance, clinical
workflow, security/privacy, or authoritative specs, STOP for integration review.

---

# Frontend build rule

`frontend/dist/` is generated and gitignored.

A build in a feature worktree does NOT update the bundle served by `main`.

After merging frontend changes:

1. switch to authoritative `main`;
2. verify expected merge commit and clean state;
3. run frontend tests + typecheck;
4. run `npm run build` from `frontend/` on main;
5. restart the app if needed;
6. perform owner/browser smoke after the main build.

---

# Frozen behavior and source of truth

Read `HANDOFF.md` before substantial work.

Frozen milestones must not be casually changed.

`DESIGN.md` is the visual/interaction source of truth.

Normative milestone requirements live under `docs/`.

Protected areas include, when marked frozen:

- clinician viewer behavior;
- Workspace Manager;
- image-admission semantics;
- patient/eye resolver semantics;
- model/provider contracts;
- annotation provenance;
- original-image coordinate behavior;
- clinician-review semantics.

If a task conflicts with frozen behavior, STOP and report it.

---

# Milestone specification rule

For substantial milestones, keep `/goal` concise.

Put detailed requirements in a version-controlled normative spec under `docs/`,
including:

- product behavior;
- state machines;
- safety/privacy rules;
- clinician-facing wording;
- API/schema expectations;
- compatibility constraints;
- acceptance criteria;
- deferred scope.

Agents must read the referenced spec completely before planning or implementing.

The spec defines WHAT; the agent decides HOW after auditing the repository.

If code reality conflicts with the normative spec:

1. STOP;
2. report the exact conflict;
3. identify the affected frozen contract/behavior;
4. propose the smallest compatible amendment;
5. wait for owner approval.

Do not silently weaken safety, privacy, auditability, or clinician semantics.

---

# Clinician-facing UI

Do not expose raw internal enums, rule codes, runtime codes, or exception text
in the primary clinician UI.

Use short, plain-language labels.

Technical details belong in audit/details/log surfaces.

Preserve the visual direction in `DESIGN.md`: minimal, professional, clinical,
readable, and information-efficient.

---

# Scientific/model boundaries

Unless explicitly authorized:

- do not change RETFound/PRISM identities or checkpoint provenance;
- do not change remote inference contracts;
- do not weaken admission gating;
- do not fabricate XAI;
- do not present softmax confidence as calibrated clinical probability;
- do not treat empty lesion detections as proof of no lesions.

Human review remains authoritative.

---

# Local data safety

Workspace/profile operations must not casually delete, move, rename, rewrite,
or recompress source images.

Profile deletion means catalog/profile deletion unless an explicitly separate
destructive operation is owner-approved.

Original admitted images remain immutable unless a future normative spec says otherwise.

---

# Interrupted work

Before resuming interrupted work:

```bash
git branch --show-current
git rev-parse HEAD
git status --short --branch
git diff
```

Never use destructive cleanup merely to obtain a clean state:

```text
git reset --hard
git clean -fd
git checkout -- .
git restore .
history rewrite / force reset
```

unless the owner explicitly authorizes that exact action.

If the authoritative repo/workspace is unavailable, STOP. Do not reconstruct it
from memory.

---

# Completion checklist

Before declaring an implementation task complete:

```text
[ ] Correct feature/fix worktree used for all implementation writes
[ ] Branch validation passed
[ ] Feature branch committed and pushed
[ ] Integration review passed
[ ] Feature branch merged into main
[ ] Main regression validation passed
[ ] frontend/dist rebuilt on main if needed
[ ] Main pushed and synchronized
[ ] Feature worktree removed
[ ] Local and remote feature branch deleted
[ ] Known limitations reported
```

Do not report completion while implementation is stranded only on a feature
branch, `main` is dirty, or the served frontend bundle is stale.
