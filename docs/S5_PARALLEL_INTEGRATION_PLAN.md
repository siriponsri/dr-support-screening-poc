# S5 Parallel Integration Plan

## Stage 0 — docs

Commit this complete S5 package to main first.

All implementation branches must start from a main HEAD that contains these specs.

## Stage 1 — foundation

Create:

```text
feat/s5f-imaging-foundation
```

Implement `S5_FOUNDATION_SPEC.md`.

Then:

```text
merge S5F -> main
focused regression
push main
```

Only then create the three parallel lanes.

## Stage 2 — parallel lanes

Create from the same post-foundation main HEAD:

```text
feat/s5a-integrity-core
feat/s5b-dicom-ingest
feat/s5c-derivative-delivery
```

### Ownership

| Lane | Primary ownership | Avoid |
|---|---|---|
| S5A | admission/integrity/store additive metadata | DICOM decoder, frontend |
| S5B | DICOM modules, DICOM optional deps/tests | Worklist/viewer UI, duplicate engine |
| S5C | derivatives/display API/viewer/model payload adapter | DICOM parser internals, duplicate engine |

### Shared-file hotspots

Likely:

```text
pyproject.toml
dr_support/api/_factory.py
frontend/src/lib/api.ts
shared imaging contracts
```

Ownership rules:

- S5B owns DICOM dependency edits in `pyproject.toml`;
- S5C owns display-route registration and frontend API types;
- S5F owns shared imaging contracts;
- S5A avoids these unless required.

Any ownership break must be reported in handoff.

## Stage 3 — integration

Recommended merge order:

```text
1. S5A -> main
2. sync latest main into S5B branch -> resolve/test there -> merge
3. sync latest main into S5C branch -> resolve/test there -> merge
```

Never resolve substantive conflicts directly on main.

If a post-merge source fix is needed:

```text
feat/s5-integration-fix
```

## Stage 4 — final validation

From final authoritative main:

```text
backend tests
Ruff
frontend tests
typecheck
production build
root smoke
git diff --check
```

Then rebuild `frontend/dist` and run WS05 owner acceptance.

## Stage 5 — cleanup

Only after final validation + owner acceptance:

- push main;
- remove S5 worktrees;
- delete local/remote S5 branches;
- never commit real clinical DICOM/PHI.

## Freeze

After owner acceptance, freeze S5 before S6 Review Evidence & QA.
