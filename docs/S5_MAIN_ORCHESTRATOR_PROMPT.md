# Main Orchestrator Prompt — S5

```text
S5 ORCHESTRATION — MEDICAL IMAGE INGESTION & DATA INTEGRITY

Follow AGENTS.md.

Authoritative branch: main

Before any action report:
- repo root
- main worktree
- main HEAD
- git status --short --branch
- origin/main sync

Main must be clean and synchronized.

Read:
- docs/S5_MASTER_SPEC.md
- docs/S5_FOUNDATION_SPEC.md
- docs/S5A_INTEGRITY_CORE_SPEC.md
- docs/S5B_DICOM_INGEST_SPEC.md
- docs/S5C_DERIVATIVE_DELIVERY_SPEC.md
- docs/S5_PARALLEL_INTEGRATION_PLAN.md
- docs/WS05_ACCEPTANCE_PLAN.md

STAGE 1 — FOUNDATION

Create:
feat/s5f-imaging-foundation

It must start from the current docs-bearing main HEAD.

Do not implement from main.

Return:
worktree path
branch
HEAD
clean status

The foundation lane must implement/test/commit/push separately.

After foundation is complete:
- review diff
- merge to main
- focused regression
- push main
- verify clean/synchronized

STAGE 2 — PARALLEL LANES

From the SAME post-foundation main HEAD create:

feat/s5a-integrity-core
feat/s5b-dicom-ingest
feat/s5c-derivative-delivery

Verify each worktree/branch/HEAD/status.
Push each branch and establish upstream.

Do NOT implement feature code from main.

Ownership:
S5A = raster/source integrity
S5B = DICOM ingestion/codecs
S5C = display/analysis derivatives + viewer delivery

All feature lanes STOP after:
implementation + branch validation + commit + push.

They must NOT merge main or delete their own worktrees.

When all lanes finish, integrate sequentially per
docs/S5_PARALLEL_INTEGRATION_PLAN.md.

Resolve substantive conflicts on the incoming feature branch after syncing latest main,
not by guessing directly on main.

After all merges run:
- backend tests
- Ruff
- frontend tests
- typecheck/build
- root smoke
- git diff --check
- rebuild frontend/dist
- WS05 owner acceptance

Only after all pass:
push main and clean up S5 branches/worktrees.

Return SHAs, merge order, validation, WS05 blockers, and cleanup status.
```
