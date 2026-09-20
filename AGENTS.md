# AGENTS.md

## Repository

- `dr_support/`: Python/FastAPI backend.
- `frontend/`: React/Vite clinician UI.
- `web/`: legacy static UI.
- `tests/`: backend/API/browser/root smoke tests.
- `docs/`: normative specs, runbooks, architecture notes.
- `local-state/`: runtime state only; never treat as source data.

Read `HANDOFF.md` before substantial work.

## Skills

Repository-specific skills live under `.agents/skills/`.

Use a repository skill when its description matches the task.
Read the selected skill completely before following its workflow.
Do not load unrelated skills merely because they exist.

Instruction priority:

1. explicit owner instructions;
2. `AGENTS.md` and frozen/normative repository requirements;
3. referenced milestone/spec documents;
4. applicable skills.

If these conflict in a way that affects frozen behavior, safety, privacy,
security, clinical semantics, or authoritative contracts, STOP and report it.

## Commands

From repo root:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m ruff check dr_support tests
npm ci && npm test
```

Frontend:

```bash
cd frontend
npm ci
npm test
npm run typecheck
npm run build
```

Use focused tests while iterating. Run required full validation before handoff.

## Coding rules

- Python: 4 spaces, existing Ruff config, PEP 8 naming.
- TypeScript: strict mode, `PascalCase` components, `camelCase` functions/variables.
- Prefer existing contracts, services, theme tokens, and Lucide icons.
- Make the smallest compatible change.
- Do not refactor unrelated code.

---

# Git and worktree policy

`main` is the authoritative integration/orchestration branch.

Implementation changes MUST NOT be written directly on `main` unless the owner
explicitly authorizes a documentation-only or integration-only change.

## Mandatory write gate

Before the first implementation write, verify and report:

```text
repository root
current worktree path
current branch
current HEAD
git status --short --branch
```

If the implementation shell is on `main`, STOP.

Create or switch to the approved bounded feature/fix branch and worktree first.
A branch existing elsewhere does not authorize editing `main`.

Preferred branch names:

```text
feat/<bounded-task>
fix/<bounded-task>
docs/<bounded-task>
```

Avoid vague long-lived branches such as `dev`, `new`, `test`, or `temp`.

## Required lifecycle

```text
clean synchronized main
→ bounded branch/worktree
→ implementation
→ focused tests
→ full branch validation
→ commit + push branch
→ integration review
→ merge into main
→ validate main
→ rebuild frontend/dist on main if frontend changed
→ push synchronized main
→ remove feature worktree
→ remove local/remote feature branch when no longer needed
```

If `origin/main` advances during feature work, integrate the latest main into
the feature branch and resolve/test there.

Do not choose a version merely because its commit is newer.

If a bug is discovered after merge, create a bounded `fix/...` branch.
Do not patch implementation files directly on `main`.

## Unexpected or interrupted state

If `main` contains unexpected modifications, STOP and inspect:

```bash
git status --short
git diff -- <file>
git diff --stat
git log -5 --oneline -- <file>
```

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

Do not reset, restore, stash, clean, overwrite, absorb, or discard unexpected
work without owner confirmation.

If the authoritative repository/workspace is unavailable, STOP.
Do not reconstruct it from memory.

---

# Integration and merge gate

Do not merge merely because branch tests pass.

Merge only when:

- branch/worktree is clean;
- required tests pass;
- implementation remains within scope;
- milestone acceptance criteria are satisfied;
- no unexpected API/schema/model/clinical-workflow drift exists;
- no secrets, PHI, model weights, runtime databases, or local-state artifacts
  are included.

STOP for integration review if a conflict affects:

- shared API/data contracts;
- DB schema or migrations;
- model/provider behavior;
- admission semantics;
- patient/eye semantics;
- annotation provenance;
- clinician workflow;
- security/privacy;
- authoritative or frozen specifications.

## Parallel work

Parallel work is allowed only after shared contracts are sufficiently frozen.

Before parallelizing:

- define API/schema/data contracts;
- assign file ownership;
- avoid overlapping migrations or shared-contract changes;
- use one worktree per branch.

Do not let parallel agents invent competing shared types, schemas, constants,
or theme tokens.

---

# Frontend build rule

`frontend/dist/` is generated and gitignored.

A feature-worktree build does NOT update the bundle served by `main`.

After merging frontend changes:

1. switch to authoritative `main`;
2. verify expected merge commit and clean state;
3. run frontend tests and typecheck;
4. run `npm run build` from `frontend/`;
5. restart the app if needed;
6. perform owner/browser smoke against the main build.

---

# Sources of truth and frozen behavior

`DESIGN.md` is the visual/interaction source of truth.

Normative milestone requirements live under `docs/`.

Frozen milestones and protected behavior must not be casually changed.
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

## Milestone specs

For substantial milestones, keep `/goal` concise.

Put detailed requirements in a version-controlled normative spec under `docs/`,
including as applicable:

- product behavior and state machines;
- safety/privacy rules;
- clinician-facing wording;
- API/schema expectations;
- compatibility constraints;
- acceptance criteria;
- deferred scope.

Agents must read the referenced spec completely before planning or implementing.

The spec defines WHAT. The agent decides HOW after auditing the repository.

If code reality conflicts with a normative spec:

1. STOP;
2. report the exact conflict;
3. identify the affected frozen contract or behavior;
4. propose the smallest compatible amendment;
5. wait for owner approval.

Do not silently weaken safety, privacy, auditability, or clinician semantics.

---

# Security, privacy, and local data

This is a clinician-support/public-synthetic research POC.

Never commit or expose:

- tokens, passwords, or API keys;
- CVAT credentials;
- model weights;
- private patient data / PHI;
- local Workspace databases;
- runtime secret files.

Secrets stay server-side.

Never store raw secrets in React, localStorage, sessionStorage, Workspace SQLite,
logs, or API responses.

Workspace/profile operations must not casually delete, move, rename, rewrite,
or recompress source images.

Profile deletion means catalog/profile deletion unless a separate destructive
operation is explicitly owner-approved.

Original admitted images remain immutable unless a future normative spec states
otherwise.

---

# Clinician-facing UI

Do not expose raw internal enums, rule codes, runtime codes, or exception text
in the primary clinician UI.

Use short plain-language labels.
Technical details belong in audit/details/log surfaces.

Preserve the visual direction in `DESIGN.md`:

```text
minimal
professional
clinical
readable
information-efficient
```

---

# Scientific and model boundaries

Unless explicitly authorized:

- do not change RETFound/PRISM identities or checkpoint provenance;
- do not change remote inference contracts;
- do not weaken admission gating;
- do not fabricate XAI;
- do not present softmax confidence as calibrated clinical probability;
- do not treat empty lesion detections as proof of no lesions.

Human review remains authoritative.

---

# Definition of done

Do not declare an implementation task complete until all applicable conditions
are true:

- implementation used the approved bounded branch/worktree;
- required branch validation passed;
- feature branch was committed and pushed;
- integration review passed;
- changes were merged into `main`;
- main regression validation passed;
- `frontend/dist` was rebuilt on main when frontend code changed;
- `main` is clean, pushed, and synchronized with `origin/main`;
- temporary feature worktree/branch was removed when no longer needed;
- skipped validation and known limitations are explicitly reported.

A task is NOT complete while implementation exists only on a feature branch,
`main` is dirty, or the served frontend bundle is stale.
