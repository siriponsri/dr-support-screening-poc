# DR Screening M1 — Phase 1 PostgreSQL Foundation

**Document path:** `docs/milestone/m1/M1_PHASE1_POSTGRES.md`  
**Milestone:** M1  
**Phase:** 1 — Data Foundation & PostgreSQL  
**Status:** READY_FOR_EXECUTION  
**Owner decision date:** 2026-09-25  
**Parent plan:** `docs/milestone/m1/M1_MASTER_PLAN.md`

---

## 1. Purpose

Phase 1 replaces the application's authoritative SQLite persistence with PostgreSQL while preserving the established clinician workflow, workspace behavior, source-image safety, review semantics, and auditability.

This phase is an infrastructure and persistence phase. It must make later M1 work possible without prematurely freezing unresolved clinical taxonomy or changing model behavior.

The target is one PostgreSQL application database with workspace-scoped records. Local PostgreSQL is used for development. AWS RDS PostgreSQL is the intended UAT deployment target later, without changing the application domain model.

Phase 1 is complete only when the application can use PostgreSQL as its authoritative runtime store, legacy eligible SQLite state can be migrated safely and reproducibly, workspace isolation is preserved, revision/concurrency behavior remains correct, and backup/restore has been demonstrated.

---

## 2. Authority and instruction order

Work under the repository instruction hierarchy:

1. explicit owner decisions;
2. root `AGENTS.md` and frozen/normative repository requirements;
3. `docs/milestone/m1/M1_MASTER_PLAN.md`;
4. this Phase 1 specification;
5. applicable repository skills and implementation conventions.

If actual repository behavior conflicts with this document in a way that affects a frozen contract, security/privacy, workspace behavior, review semantics, source-image integrity, or clinical provenance, stop and report the conflict before changing that behavior.

The Phase 1 orchestrator may update milestone status/evidence documentation on `main` as integration bookkeeping after successful validation. Application implementation must not be authored directly on the `main` worktree.

---

## 3. Owner-approved decisions

The following decisions are frozen for Phase 1 unless the owner explicitly changes them.

### 3.1 PostgreSQL topology

Use one PostgreSQL application database.

Workspace isolation is represented by a stable `workspace_id` on all workspace-scoped authoritative records.

Do not create one PostgreSQL database per workspace.

Development uses local PostgreSQL. UAT later uses AWS RDS PostgreSQL through configuration rather than a separate application architecture.

### 3.2 Workspace behavior

Preserve the user-facing Workspace Manager concepts:

- create workspace;
- open/select workspace;
- switch active workspace;
- remove/delete a workspace profile without deleting source images or clinical data.

The previous local SQLite database-file path is an implementation detail being retired. It must not remain a required user choice in normal PostgreSQL mode.

Workspace profile deletion must remain non-destructive with respect to clinical/review data and source images. A future destructive purge, if ever added, is a separate owner-approved operation and is out of scope here.

### 3.3 Legacy SQLite migration scope

Eligible migration sources are:

1. the current workspace catalog SQLite database; and
2. per-workspace SQLite databases referenced by the authoritative catalog.

SQLite files found elsewhere, including orphaned files under runtime state, are inventory-only unless they can be tied to an authoritative catalog record or are explicitly approved by the owner.

Do not infer authority from a filename alone.

Legacy SQLite files are read-only migration sources. Migration must not rename, rewrite, move, delete, vacuum, or otherwise mutate them.

### 3.4 No dual-write architecture

Do not introduce long-lived SQLite/PostgreSQL dual-write behavior.

The supported end state is PostgreSQL-authoritative runtime persistence.

A migration/cutover tool may read SQLite and write PostgreSQL, but normal application writes must have one authoritative destination.

### 3.5 Clinical/model boundaries

Phase 1 must not:

- redefine DR grading;
- freeze the advanced UWF finding taxonomy;
- change RETFound or PRISM-DR modality metadata;
- enable CFP inference on UWF;
- implement the temporary CFP-on-UWF fallback approved elsewhere in M1;
- change UWF masking/admission behavior;
- change longitudinal clinical semantics;
- treat empty AI detections as negative ground truth;
- promote untouched AI suggestions to physician-confirmed training labels.

Those are later-phase concerns unless a persistence compatibility change is strictly required.

---

## 4. Verified Phase 0 baseline

Phase 0 audited repository state at:

- branch: `main`;
- HEAD: `7af3ef1a11fc9de12b871d82c73d8be53d2ffa84` at the time of the audit;
- React/Vite clinician application;
- FastAPI backend;
- review cases stored as JSON documents in SQLite;
- workspace profiles stored in a separate SQLite catalog and pointing to per-workspace SQLite databases;
- no PostgreSQL driver/configuration identified in the audited project dependencies;
- UWF admission and deterministic retinal-field preparation already present;
- workstation inference currently CFP-gated;
- RETFound and PRISM-DR currently advertise CFP only;
- filename resolution does not yet provide a first-class visit/capture relationship;
- annotation/export behavior preserves untouched AI suggestions as AI-only and excludes them from training-ready output;
- existing regression coverage includes workspace, workflow, UWF intake, resolver, dataset, profile, remote/model, and frontend tests.

The implementation agent must re-check actual repository state before writing. This section is a baseline, not permission to ignore newer commits or local changes.

---

## 5. Phase objective

Deliver a PostgreSQL persistence foundation that satisfies all of the following:

1. PostgreSQL is the authoritative runtime persistence for review/case state.
2. PostgreSQL is the authoritative runtime persistence for workspace/catalog state.
3. Existing clinician workflow behavior remains functionally compatible.
4. Workspace isolation is explicit and testable.
5. Revision/stale-write protection remains correct under multiple database connections.
6. Existing audit/provenance information is preserved.
7. Eligible catalog-referenced SQLite data can be imported with dry-run, verification, and idempotency protections.
8. Legacy sources are not mutated.
9. Backup and restore can be executed and verified.
10. The schema and persistence API leave room for later patient/eye/visit, model-prediction, annotation-version, and completeness-state work without hard-coding unresolved clinical taxonomy now.

---

## 6. Scope

### 6.1 In scope

- PostgreSQL runtime dependency and server-side configuration.
- Database connection/session/transaction abstraction consistent with existing project style.
- Schema migration mechanism.
- PostgreSQL workspace/catalog persistence.
- PostgreSQL review/case persistence.
- Stable workspace scoping using `workspace_id`.
- Existing case revision/stale-write semantics.
- Existing review, resolver, inference-evidence, and annotation provenance payload preservation.
- Legacy SQLite inventory and migration tooling.
- Dry-run migration reporting.
- Migration idempotency and source provenance.
- Restart persistence tests.
- Workspace isolation tests.
- Transaction rollback tests.
- Concurrent revision/stale-write conflict tests using independent PostgreSQL connections.
- Development setup/configuration documentation.
- Backup/restore procedure and smoke verification.
- Minimum Workspace Manager compatibility changes required by the removal of per-workspace runtime SQLite paths.
- Phase completion evidence and tracker updates.

### 6.2 Explicitly out of scope

- new DR grading models;
- lesion model training;
- longitudinal model training;
- CFP-on-UWF fallback execution;
- new UWF annotation taxonomy UX;
- Advanced Findings UI;
- Processing Details UI;
- Workspace Data query/export UI;
- new dataset manifest semantics beyond persistence compatibility;
- new patient/eye/visit autofill behavior;
- clinical referral logic;
- DME inference;
- AWS deployment itself;
- production authentication/SSO redesign;
- destructive workspace/clinical-data purge;
- Redis, Celery, Kafka, MLflow, or other infrastructure not proven necessary for this phase.

---

## 7. Persistence design requirements

This section defines required behavior, not a mandatory ORM or library choice. The implementation agent must follow existing repository conventions where practical and explain any new persistence dependency.

### 7.1 One authoritative PostgreSQL store

Normal application operation must use PostgreSQL for both:

- workspace/catalog state; and
- review/case state.

The application must not silently create or fall back to SQLite when PostgreSQL is unavailable in PostgreSQL mode.

A PostgreSQL outage must fail clearly and safely rather than create a divergent local database.

### 7.2 Workspace scoping

Every authoritative record that belongs to a workspace must be associated with the stable workspace identifier.

The persistence layer must prevent a request operating in workspace A from reading or modifying records in workspace B unless an explicit cross-workspace administrative/query function is added later.

At minimum, isolation must be enforced in service/repository queries and verified by tests. Database-level constraints should be used where they reduce risk without introducing disproportionate complexity.

### 7.3 Stable case identity and revisions

Preserve the current externally meaningful case identity.

The PostgreSQL representation must support:

- stable case ID;
- workspace scope;
- current case payload/state;
- monotonic or otherwise explicit revision/version used for stale-write rejection;
- create/update timestamps sufficient for persistence/audit operations.

A uniqueness rule equivalent to `(workspace_id, case_id)` must prevent accidental cross-workspace collision or duplicate active case identity.

### 7.4 Compatibility-first case storage

Phase 1 should prioritize semantic compatibility over premature normalization.

The existing case document may remain represented as a versioned JSON/JSONB payload where that is the smallest safe migration path, provided that:

- stale-write/revision behavior is explicit;
- workspace scoping is explicit;
- stable identifiers needed for integrity are not hidden only inside opaque JSON when a database constraint is required;
- migration verification can compare legacy and imported case contents deterministically;
- later schema evolution remains possible.

Do not normalize unresolved clinical taxonomy merely to make the schema appear relational.

### 7.5 Future-ready but clinically neutral schema

Phase 1 must not hard-code the eventual UWF lesion taxonomy.

The persistence design must nevertheless avoid blocking later first-class support for:

- pseudonymous patient identity;
- left/right/unknown eye;
- visit/capture identity and acquisition evidence;
- immutable source-image identity/hash;
- model predictions and model provenance;
- physician review revisions;
- per-annotation origin and confirmation state;
- annotation group completeness such as not reviewed versus reviewed-none-found;
- audit events;
- inference jobs.

It is acceptable for some of these to remain inside versioned case payloads during Phase 1 if their normalization is not required to meet Phase 1 acceptance criteria.

### 7.6 Transactions

Operations that are logically atomic must commit or roll back atomically.

At minimum, tests must demonstrate rollback behavior for representative review/case updates and workspace mutations.

Do not leave partial workspace creation, partial migration state, or partially updated case revisions after a failed transaction.

### 7.7 Concurrency and stale writes

The current stale-revision protection must remain effective when two independent application/database connections modify the same case.

The test must not rely only on one in-process lock.

A stale writer must receive a deterministic conflict outcome and must not overwrite the newer committed state.

### 7.8 Secrets and configuration

Database credentials remain server-side.

Do not expose PostgreSQL passwords/DSNs in:

- React code;
- localStorage/sessionStorage;
- browser API responses;
- logs;
- committed `.env` files;
- milestone documentation containing real credentials.

Document a placeholder/example configuration only.

The exact environment variable name should follow the repository's existing configuration style unless the repository has no suitable convention. If a new variable is introduced, document it consistently in the example environment/configuration and operations documentation.

---

## 8. Workspace Manager compatibility contract

Workspace Manager is protected behavior. Phase 1 changes storage implementation, not the user's mental model of a workspace.

### 8.1 Required retained behavior

A user can still:

- create a workspace;
- name it according to current rules;
- select/configure the input/source folder according to current rules;
- select/configure the output/export folder according to current rules;
- open/select a workspace;
- switch active workspace;
- remove/delete the profile according to current user-facing semantics.

### 8.2 Retired behavior

A normal PostgreSQL workspace must not require the user to select a runtime SQLite database file.

Any old `database_path` value imported from the legacy catalog becomes migration/provenance information, not the active persistence destination.

### 8.3 Delete-profile behavior

Deleting/removing a workspace profile must not:

- delete source images;
- delete exported files;
- cascade-delete clinical/review records from PostgreSQL;
- delete a legacy SQLite source file;
- silently purge audit history.

A reasonable implementation is to archive/deactivate the workspace profile so it disappears from the normal active list while authoritative records remain recoverable. The exact physical implementation may vary, but the non-destructive behavior is mandatory.

### 8.4 Frontend scope

Frontend changes must be minimal and limited to compatibility with PostgreSQL-backed workspaces.

Do not redesign Workspace Manager styling or navigation in this phase.

If the current UI exposes a native SQLite database picker, replace/remove only that storage-specific control and present a short English managed-storage state if needed. Do not expose raw DSNs or database credentials.

---

## 9. Legacy SQLite migration contract

### 9.1 Discovery

Migration tooling must identify:

- the authoritative legacy workspace catalog supplied/configured for migration;
- workspace entries in that catalog;
- each catalog-referenced per-workspace SQLite database;
- missing referenced databases;
- duplicate/ambiguous references;
- orphan SQLite files discovered in configured runtime locations.

Orphans are reported, not imported automatically.

### 9.2 Source integrity

Before import, record sufficient source identity such as:

- normalized source path;
- file size;
- modification metadata where useful;
- SHA-256 of the legacy SQLite file;
- workspace/catalog identifier.

The migration process must open legacy sources without modifying them.

### 9.3 Dry run

A dry-run mode is mandatory.

Dry run must produce a human-readable report containing at least:

- number of workspace records discovered;
- number of referenced workspace databases;
- missing/invalid sources;
- orphan files found but not selected;
- case counts per workspace where readable;
- duplicate/conflict conditions;
- planned target workspace mappings;
- whether the run is safe to proceed.

Dry run must perform no PostgreSQL application-data mutation beyond optional temporary/test state that is rolled back and documented. Prefer no mutation at all.

### 9.4 Import

Actual import must:

- use explicit target PostgreSQL configuration;
- preserve workspace identity or record an explicit deterministic mapping;
- preserve case IDs;
- preserve case payload semantics and audit/provenance fields;
- preserve current review state;
- preserve source image references without copying/mutating images;
- record migration source provenance;
- detect an already imported identical source and avoid duplication.

### 9.5 Idempotency

Running the same approved migration twice must not create duplicate workspaces, cases, annotations, or audit state.

If source content has changed after an earlier import, the tool must not silently merge divergent state. It must stop or require an explicit reviewed action.

### 9.6 Verification

After import, verification must compare at least:

- workspace counts/mappings;
- case counts per workspace;
- case IDs;
- current revisions;
- deterministic payload hashes or equivalent canonical content checks;
- selected critical status fields;
- migration source hashes.

Any mismatch must fail the migration verification report.

### 9.7 Cutover

There must be a clear operator-visible distinction between:

- legacy SQLite source;
- migration verification;
- PostgreSQL runtime mode.

Do not automatically switch a real workspace to PostgreSQL merely because a dry run completed.

For M1 development, cutover may be an explicit configuration/startup step after verification.

### 9.8 Legacy rollback expectation

Legacy SQLite files remain intact, but they are not a safe automatic rollback target after new PostgreSQL-only edits have occurred because the stores would diverge.

Document this limitation explicitly.

Backup/restore of PostgreSQL is the supported recovery mechanism after cutover.

---

## 10. Backup and restore

Phase 1 must include a documented, executable backup and restore path for PostgreSQL development/UAT preparation.

The exact tools may follow standard PostgreSQL utilities and project deployment conventions.

Acceptance requires a smoke exercise:

1. create representative workspace/review state;
2. take a database backup;
3. modify or recreate the test target safely;
4. restore into a clean target database;
5. start the application against the restored target;
6. verify workspace and case/revision state;
7. verify representative audit/provenance state;
8. record the commands and result.

Do not include patient data, secrets, or real production credentials in committed backup artifacts.

Backup files are runtime artifacts and must not be committed.

---

## 11. Testing requirements

### 11.1 Existing behavior to preserve

At minimum preserve regression coverage for:

- workspace create/open/switch behavior;
- workspace isolation;
- non-destructive workspace/profile deletion semantics;
- review/case persistence across restart;
- stale-revision rejection;
- resolver provenance;
- UWF source-image immutability;
- deterministic retinal-field preparation behavior;
- UWF inference rejection by CFP-only providers/routes where currently required;
- RETFound CFP-only metadata/behavior;
- PRISM-DR CFP-only metadata/behavior;
- dataset export exclusion of untouched AI suggestions from training-ready labels;
- existing clinician workflow API behavior unrelated to storage implementation.

### 11.2 New PostgreSQL tests

Add tests demonstrating:

- schema can be created/upgraded from a clean database;
- migration mechanism is deterministic and repeatable;
- application restart preserves state;
- two workspaces cannot leak cases across workspace boundaries;
- transaction failure rolls back the intended operation;
- two independent database connections enforce revision conflict/stale-write behavior;
- workspace profile removal does not cascade-delete clinical/review data;
- migration dry run is non-destructive;
- eligible legacy catalog-referenced SQLite import preserves counts/IDs/revisions/content;
- repeated identical migration does not duplicate data;
- changed/conflicting legacy source is detected rather than silently merged;
- orphan SQLite files are reported and not automatically imported;
- backup/restore smoke restores representative state.

### 11.3 Test database safety

Automated PostgreSQL integration tests must use an explicitly designated test database/configuration.

Tests must fail safely if pointed at an obviously non-test target according to the chosen project convention.

Do not drop, truncate, or recreate an arbitrary operator-supplied database.

### 11.4 Validation commands

Follow the current root `AGENTS.md` commands and any newer repository commands discovered at execution time.

The expected final validation includes, as applicable:

```bash
python -m pytest -q
python -m ruff check dr_support tests
```

If frontend code changed:

```bash
cd frontend
npm ci
npm test
npm run typecheck
npm run build
```

The orchestrator must record exact commands and outcomes in the Phase 1 completion evidence.

---

## 12. Documentation requirements

Update only documentation that is made stale by Phase 1 implementation.

Likely areas include:

- root `README.md` if current setup/storage instructions require changes;
- configuration documentation;
- backup/restore documentation;
- deployment/local setup documentation;
- developer persistence/API notes;
- clinician/workspace documentation only where user-visible Workspace Manager behavior changed.

Do not create multiple new planning documents for worker tasks.

This file is the Phase 1 working specification and completion ledger.

---

## 13. Orca execution model

Phase 1 uses a simple orchestrator pattern.

### 13.1 Roles

**Owner**

- approves product/architecture decisions;
- resolves unexpected destructive or clinical-contract changes.

**Main Luna Max orchestrator**

- runs from the authoritative main worktree;
- reads this specification and `AGENTS.md` fully;
- does not author application implementation directly on `main`;
- creates bounded implementation worktrees when needed;
- supervises agents/tasks;
- reviews branch diffs and tests;
- merges in dependency order;
- runs final validation on `main`;
- updates Phase 1 evidence/status;
- stops for owner/auditor review.

**Worker Luna Max agent(s)**

- work only in assigned bounded worktrees;
- follow file-ownership/scope boundaries;
- run focused tests while iterating;
- commit coherent implementation checkpoints;
- report exact tests, limitations, and commit SHA.

### 13.2 Parallelism rule

Parallelism is an optimization, not a requirement.

The orchestrator may create parallel workers only when all are true:

1. the shared persistence contract is stable;
2. file ownership is sufficiently non-overlapping;
3. task dependencies permit useful independent progress;
4. parallel work will reduce elapsed time more than it increases merge risk.

If these conditions are not true, work sequentially.

Maximum recommended concurrent implementation workers for Phase 1: **2**.

Do not create additional workers merely because Orca supports them.

---

## 14. Recommended worktree/task graph

The orchestrator should adapt this graph after re-auditing actual files. It is a recommended execution shape, not permission to ignore code reality.

### Stage P1-F — PostgreSQL foundation

Recommended branch:

`feat/m1-p1-postgres-foundation`

Purpose:

- select/add PostgreSQL runtime dependency consistent with repository style;
- add server-side configuration;
- add connection/session/transaction foundation;
- add schema migration framework;
- establish shared table/key/revision conventions;
- establish PostgreSQL test fixture/integration-test safety;
- avoid migrating all domain behavior yet.

This stage is sequential and must stabilize before fan-out.

**Foundation gate:**

- focused tests pass;
- configuration is documented;
- migration framework works against a clean test database;
- no application feature semantics were changed;
- shared contract is sufficiently stable for child branches.

### Stage P1-A — Review/case persistence

Recommended branch:

`feat/m1-p1-case-persistence`

Start from the exact approved Foundation commit, not merely from a visually nested Orca parent.

Primary scope:

- review/case store PostgreSQL implementation;
- revision/stale-write semantics;
- existing payload/provenance preservation;
- restart persistence;
- transaction/concurrency tests;
- eligible per-workspace case SQLite import path.

Avoid Workspace Manager frontend/service implementation unless a shared compatibility change is explicitly assigned.

### Stage P1-B — Workspace persistence

Recommended branch:

`feat/m1-p1-workspace-persistence`

Start from the same approved Foundation commit.

Primary scope:

- workspace/catalog PostgreSQL persistence;
- stable workspace IDs;
- create/open/switch/delete-profile compatibility;
- removal/retirement of runtime SQLite database-path selection;
- legacy catalog import/mapping;
- workspace isolation tests;
- minimal frontend/API compatibility changes if needed.

Avoid review/case-store internals except shared interfaces already frozen by Foundation.

### Stage P1-I — Integration, migration verification, recovery

Performed by the main orchestrator after worker branches are ready.

Recommended order:

1. verify and integrate Foundation;
2. verify and integrate P1-A;
3. verify and integrate P1-B;
4. resolve integration-only conflicts on an approved bounded fix branch if substantive code changes are required;
5. complete migration dry-run/verification tooling gaps;
6. complete backup/restore documentation/smoke;
7. run full backend validation;
8. run full frontend validation/build if frontend changed;
9. perform application smoke on authoritative `main`;
10. update Phase 1 and master-plan evidence;
11. push synchronized `main`;
12. only then remove completed worktrees/branches according to repository policy.

If P1-A and P1-B overlap materially in shared files after Foundation, the orchestrator should serialize them instead of forcing parallel execution.

---

## 15. Worker branch completion gate

A worker branch is not merge-ready merely because the agent says it is complete.

The orchestrator must verify:

- branch/worktree is the expected one;
- branch is based on the required Foundation/main revision;
- `git status --short --branch` is clean except explicitly expected generated/untracked runtime artifacts that must not be committed;
- diff remains within assigned scope;
- no secrets, PHI, model weights, runtime databases, backups, or local-state files are staged;
- focused tests pass;
- required branch validation passes;
- no frozen behavior changed unexpectedly;
- commit(s) exist with meaningful messages;
- branch is pushed before final integration if required by root `AGENTS.md`;
- worker reports known limitations honestly.

If any item fails, return the task to the worker rather than merging.

---

## 16. Phase 1 acceptance criteria

Phase 1 can be marked `DONE` only when all applicable criteria pass.

### A. Authoritative persistence

- [ ] Normal application mode uses PostgreSQL for review/case persistence.
- [ ] Normal application mode uses PostgreSQL for workspace/catalog persistence.
- [ ] PostgreSQL outage does not silently create a new SQLite authority.
- [ ] No long-lived dual-write path exists.

### B. Workspace compatibility

- [ ] Create workspace works.
- [ ] Open/select workspace works.
- [ ] Switch workspace works.
- [ ] Workspace isolation is verified.
- [ ] Delete/remove profile is non-destructive to clinical/review data and source images.
- [ ] Normal PostgreSQL workspace setup no longer requires selecting an SQLite database file.

### C. Review compatibility

- [ ] Existing review workflow persists and reopens correctly after restart.
- [ ] Existing audit/provenance state is preserved.
- [ ] Stale revision is rejected across independent PostgreSQL connections.
- [ ] Transaction rollback is demonstrated.

### D. Migration

- [ ] Legacy catalog discovery works.
- [ ] Catalog-referenced workspace databases are identified.
- [ ] Orphan SQLite files are inventory-only by default.
- [ ] Dry run performs no destructive source or target mutation.
- [ ] Actual import preserves expected workspace/case counts.
- [ ] Case IDs and revisions are preserved.
- [ ] Deterministic content verification passes.
- [ ] Legacy source SHA-256/provenance is recorded.
- [ ] Re-running identical migration is idempotent.
- [ ] Changed/divergent legacy source is not silently merged.
- [ ] Legacy SQLite source files remain unchanged.

### E. Recovery

- [ ] PostgreSQL backup command/process is documented.
- [ ] Restore command/process is documented.
- [ ] Restore smoke was performed against a clean target.
- [ ] Restored application state was verified.

### F. Regression boundaries

- [ ] UWF source immutability behavior remains intact.
- [ ] UWF admission/mask behavior remains intact.
- [ ] CFP-only model metadata remains intact.
- [ ] Current UWF inference restriction remains intact for this phase.
- [ ] Untouched AI suggestions remain excluded from training-ready labels.
- [ ] No clinical taxonomy was silently frozen or changed.

### G. Validation and integration

- [ ] Required backend tests pass.
- [ ] Ruff/static checks pass.
- [ ] Required frontend tests/typecheck/build pass if frontend changed.
- [ ] Authoritative main application smoke passes.
- [ ] `main` is clean and synchronized with `origin/main`.
- [ ] No runtime database, backup, PHI, secret, or model-weight artifact is committed.
- [ ] Phase evidence is recorded below.

---

## 17. Stop conditions requiring owner/auditor decision

Stop and report rather than invent a solution if any of the following occurs:

- preserving Workspace Manager behavior requires destructive clinical-data deletion;
- migration source authority cannot be determined;
- a catalog references multiple conflicting databases for the same workspace;
- imported case IDs/revisions cannot be mapped without changing clinician-visible history;
- a proposed schema requires freezing unresolved UWF clinical taxonomy;
- PostgreSQL migration would require changing source images;
- the implementation would weaken annotation provenance or training-label safeguards;
- a worker needs to change CFP/UWF model modality contracts;
- an unexpected dirty `main` state appears during integration;
- credentials, PHI, runtime databases, or weights are found staged for Git;
- backup/restore or migration verification reveals unexplained data loss;
- a worker cannot satisfy branch validation without bypassing or deleting existing tests.

---

## 18. Phase status ledger

Update this section during execution. Do not mark an item `DONE` without evidence.

| Work item | Status | Branch / commit | Evidence / notes |
|---|---|---|---|
| P1-F PostgreSQL foundation | TODO | — | — |
| P1-A Review/case persistence | TODO | — | — |
| P1-B Workspace persistence | TODO | — | — |
| Legacy SQLite dry-run/import verification | TODO | — | — |
| Backup/restore smoke | TODO | — | — |
| Full backend validation | TODO | — | — |
| Frontend validation/build if changed | TODO | — | — |
| Main smoke and synchronization | TODO | — | — |
| Owner/auditor review | TODO | — | — |

Allowed statuses:

- `TODO`
- `IN_PROGRESS`
- `BLOCKED`
- `READY_FOR_REVIEW`
- `DONE`

---

## 19. Completion evidence template

The main orchestrator must complete this section before asking the owner/auditor to close Phase 1.

### Repository state

```text
Repository root:
Main HEAD before Phase 1:
Main HEAD after Phase 1:
Main status:
Origin synchronization:
```

### Integrated branches

| Branch | Base | Final commit | Validation | Merge result |
|---|---|---|---|---|
| `feat/m1-p1-postgres-foundation` | | | | |
| `feat/m1-p1-case-persistence` | | | | |
| `feat/m1-p1-workspace-persistence` | | | | |

Remove rows for branches not used. Add rows for owner-approved bounded fix branches if required.

### Database/migration evidence

```text
PostgreSQL version used:
Schema/migration version:
Legacy catalog source SHA-256:
Eligible workspace databases discovered:
Eligible workspace databases imported:
Orphan SQLite files reported:
Workspace count verification:
Case count verification:
Revision/content verification:
Idempotency result:
Backup/restore result:
```

Do not paste real credentials, PHI, or patient-identifying paths into this document.

### Validation evidence

```text
Focused tests:
Full backend tests:
Ruff/static checks:
Frontend tests:
Frontend typecheck:
Frontend build:
Application smoke:
Skipped tests/checks and reason:
```

### Known limitations

```text
- 
```

### Blockers deferred to later phases

```text
- 
```

### Final Phase 1 state

Choose exactly one:

```text
BLOCKED
READY_FOR_REVIEW
DONE
```

`DONE` requires owner/auditor approval after reviewing this evidence.

---

## 20. Suggested `/goal` for the main Luna Max orchestrator

Use a short goal; this specification contains the detail.

```text
Complete M1 Phase 1 — PostgreSQL Foundation according to
`docs/milestone/m1/M1_PHASE1_POSTGRES.md`.

Act as the Phase 1 orchestrator from the authoritative main worktree.
Read `AGENTS.md`, `docs/milestone/m1/M1_MASTER_PLAN.md`, this Phase 1 spec,
and the relevant current repository documentation before acting.

Do not author application implementation directly on main.
Re-check repository root, worktree, branch, HEAD, and status first.
Use bounded Orca worktrees for implementation. Stabilize the shared PostgreSQL
foundation before any fan-out. Parallelize only when contracts are stable,
file ownership is sufficiently non-overlapping, and useful progress can occur
independently; otherwise work sequentially. Use no more than two concurrent
implementation workers for this phase.

Review each worker diff and validation before integration. Merge in dependency
order, run required full validation on authoritative main, perform migration and
backup/restore evidence checks, update the Phase 1 status ledger and completion
evidence, synchronize main, and stop at READY_FOR_REVIEW for owner/auditor review.

Do not change clinical taxonomy, UWF/CFP model modality semantics, UWF admission,
source-image behavior, or clinician review semantics merely to complete this phase.
Stop for owner decision on any frozen-contract or destructive-data conflict.
```

---

## 21. Phase closeout rule

When Phase 1 is approved as `DONE`:

1. update `docs/milestone/m1/M1_MASTER_PLAN.md` with Phase 1 completion status, final main commit, evidence summary, and remaining blockers;
2. keep this file as the detailed Phase 1 audit trail;
3. do not start Phase 2 implementation until its scope is reviewed against the actual post-Phase-1 repository state;
4. create only the Phase 2 working specification needed at that time.

