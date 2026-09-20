# Repository Guidelines

## Project Structure

- `dr_support/` contains the Python/FastAPI backend. Keep profile dispatch in `app.py`, API surfaces under `api/`, deployment services under `services/`, model adapters under `providers/`, and shared schemas under `contracts/`.
- `web/` is the legacy static UI; `frontend/` is the React/Vite migration (`frontend/src/` for application code and `frontend/tests/` for Vitest tests).
- `tests/` contains backend pytest, API, browser, and root UI smoke tests. `docs/` holds runbooks and architecture/deployment notes; `examples/` contains public sample manifests.
- `local-state/` is runtime state and must not be treated as source data. Use `.env.example` as the configuration reference.

## Build, Test, and Development

From the repository root:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m ruff check dr_support tests
python -m dr_support.run
npm ci && npm test
```

The Python command starts the local API; `START.cmd` is the Windows shortcut. Root `npm test` runs the legacy overlay, API-hardening, UI, and preview smoke tests. For the React app:

```bash
cd frontend
npm ci
npm run dev       # Vite development server
npm run build
npm run typecheck
npm test
```

## Coding Style and Naming

Use four spaces in Python and the existing 110-character Ruff limit. Follow PEP 8 naming (`snake_case` functions/modules, `PascalCase` classes). TypeScript is strict: use `PascalCase` React components, `camelCase` variables/functions, and `useX` names for hooks. Prefer existing contracts, profile boundaries, theme tokens, and Lucide icons over new parallel abstractions.

## Testing Guidelines

Name Python tests `test_*.py`, root Node tests `*.test.cjs`, and frontend tests `*.test.tsx`. Backend tests are offline by design and use disposable SQLite state; do not add network-dependent tests. Run the focused suite while iterating, then run the full commands above. Browser smoke tests are optional: `python -m pytest -q tests/test_browser_ui.py`.

## Commits and Pull Requests

Use the established Conventional Commit style, such as `feat(remote): ...`, `fix(review): ...`, `docs: ...`, or `refactor: ...`. Keep commits focused. PRs should describe behavior and affected profile/UI, link the relevant issue or plan, list validation commands, and include screenshots for frontend changes. Call out new environment variables, model/runtime requirements, or security implications.

## Security and Configuration

This is a public/synthetic research POC, not an autonomous diagnostic system. Never commit tokens, model weights, or private patient data. Keep CVAT credentials server-side, use environment variables, and follow `docs/LOCAL_RUNBOOK.md` before exposing the API beyond localhost.

## Branching and Orchestration Policy

`main` is the authoritative integration branch and should remain clean between milestones. Treat work on `main` as orchestration/integration work, not as the default place for feature implementation.

### Main as orchestrator

For each milestone:

1. Start from a clean, synchronized `main`.
2. Audit the current repository state and define task boundaries, dependencies, shared contracts, and acceptance criteria.
3. Create one bounded feature branch per independent implementation task.
4. Use separate worktrees/directories when tasks run in parallel. Do not run multiple implementation agents against different branches in the same working directory.
5. Assign one clear goal per branch. Parallelize only tasks that can proceed without guessing each other's unfinished contracts or schemas.
6. Each implementation branch must run its focused tests while iterating and the required full validation before handoff.
7. Each branch must commit and push its work, then report:
   - branch name;
   - commit SHA;
   - changed files;
   - contract/schema changes, if any;
   - validation results;
   - known limitations or blockers.
8. Merge only after an integration review confirms the branch is within scope and compatible with current `main`.
9. Re-run relevant regression tests on the merged `main`.
10. After successful integration, delete the completed local and remote feature branch/worktree so `main` remains the single long-lived branch unless a task explicitly requires otherwise.

### Branch naming

Prefer scoped names such as:

- `feat/s2-workspace-backend`
- `feat/s2-workspace-frontend`
- `feat/s2-patient-identity`
- `fix/viewer-coordinate-transform`
- `docs/design-system`

Do not use vague long-lived branches such as `dev`, `new`, `test`, or `work`.

### Parallel work

Parallel backend/frontend work is encouraged only after shared contracts are frozen sufficiently for both sides to implement independently.

Before parallelizing, define the shared API/schema/data contract in writing. If one branch depends on a schema or behavior that another branch has not yet frozen, keep the work sequential rather than duplicating assumptions.

When agents work in parallel:

- prefer one worktree per branch;
- avoid overlapping file ownership where possible;
- do not silently duplicate shared types, constants, schemas, or theme tokens;
- do not let two agents edit the same migration or shared contract concurrently without explicit coordination;
- never use a feature branch as an integration branch for unrelated work.

### Merge gate

Do not auto-merge merely because a branch reports success. Merge only when all applicable conditions are true:

- working tree is clean;
- branch is based on the expected `main`;
- required tests pass;
- no unexpected API/model/database/clinical-workflow drift is present;
- no secrets, private patient data, model weights, local-state files, or generated credentials are included;
- no unexpected deletion or replacement of authoritative docs/artifacts occurred;
- the implementation satisfies the milestone acceptance criteria.

If a merge conflict touches shared contracts, database schema/migrations, model behavior, annotation semantics, clinical workflow, or authoritative design documentation, STOP and request integration review. Do not make a semantic auto-resolution.

### Frontend integration artifact rule

`frontend/dist/` is generated and gitignored. A successful build in a feature worktree does not update the main worktree's served React bundle.

After merging any frontend-affecting branch into `main`:

1. switch to the authoritative `main` worktree;
2. verify `main` is clean and at the expected merge commit;
3. run frontend tests and typecheck;
4. run `npm run build` from the `main` worktree;
5. restart the local application if it serves `frontend/dist/`;
6. perform owner/browser smoke testing only after the main-worktree build.

Do not treat a feature-worktree build artifact as the bundle served by `main`.

### Protected baselines and scientific boundaries

Do not rewrite or move protected release/demo tags. Preserve accepted model checkpoints, hashes, provider behavior, scientific thresholds, and clinician-review semantics unless the current task explicitly authorizes a change.

Feature branches must not casually alter RETFound, PRISM-DR, remote inference contracts, annotation provenance, original-image coordinate behavior, or protected demo/research baselines.

### Design authority

`DESIGN.md` is the normative visual and interaction design source for the React frontend. Existing or legacy theme documents must not override it.

Visual implementation must preserve accepted viewer behavior and must not introduce product, API, model, database, or scientific changes unless those changes are explicitly part of the active milestone.

## Agent Handoff Discipline

When resuming interrupted work, inspect the current branch, HEAD, `git status`, and existing diff before changing files. Existing uncommitted changes may be intentional work in progress.

Never run `git reset --hard`, `git clean -fd`, destructive restore commands, history rewrites, or broad regeneration steps merely to obtain a clean state unless the owner explicitly authorizes that exact destructive action.

If the authoritative workspace/repository is unavailable, stop implementation and report the access blocker. Do not reconstruct the repository from memory or create substitute files that could later overwrite authoritative work.
