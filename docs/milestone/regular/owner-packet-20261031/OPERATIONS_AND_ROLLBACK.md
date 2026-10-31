# Operations, installation candidate and rollback requirements

This document defines what Claude must implement/verify and record. It does not claim an installed service exists. Follow [the spec](REGULAR_SERVICE_SPEC.md), [authorization](AUTHORIZATION_AND_QUOTAS.md) and [evidence matrix](VALIDATION_MATRIX.md). Concrete commands/owned process locations must be filled from the tested implementation; do not invent a helper name or paste credentials into examples.

## 1. Target ownership and configuration

- Windows review app per user/workstation, normal loopback `/app/`, managed PostgreSQL and approved local image/output roots. Keep each app's workspace/store selection private to that context.
- Shared private Model API on dr-train under the existing DR identity/project. Reuse the verified private route and backend-only credential mechanism. The recorded QA defaults were app8010, local tunnel47860 -> remote loopback7860; those QA defaults are not proof that the normal8000 launcher is connected. Record the actual tested mapping for every app context.
- Only approved RTX UUID, fresh exclusive DR allocation/headroom checks, no overlap/interference with other owners. V100/[other team], [other team]/team services and their processes/volumes stay untouched. No public listener or unapproved firewall/ACL/service change.
- Approved daily caps:1500 admitted model invocations and43200 GPU reservation seconds, Thai calendar day. AI opportunity06:00–22:00; idle DR models unload and compute exhaustion blocks new AI. CPU/manual/history/export/readback can remain available without model load.
- Version the new regular authority/configuration digest and record owner evidence. Preserve old closed ledgers/windows/locks/history; never make a new daily allowance by copying an old directory, clearing state or restoring an old operational snapshot.

Identity/credential/role/TLS/privileged autostart provisioning is a concrete security action:prepare exact scope/least privileges/rollback and obtain action-time permission if not already established. Routine startup/status/coding/tests within existing authorization need no repeated blanket confirmation. Never read/print private-key bytes or expose server tokens through React, Workspace DB, logs or archives.

## 2. Normal user workflow to document and demonstrate

1. Open the installed local app with the canonical launcher. It verifies/uses only its owned app/DB/private connection and shows the correct user's workspace and truthful model status. It must not need an operator to run SSH/readback for each image.
2. Import/select the approved daily image batch once. Show durable100-image backlog, per-case context/quality/manual steps and both model-stage status. Duplicate/reconnect finds existing progress.
3. For eligible confirmed cases, dispatch grader then protected PRISM through the fair shared service. Queue progress is separate from model execution; user's normal review can continue as permitted by existing guards. No silent context confirmation or input-acknowledgement bypass.
4. Show results only with validated provenance and correct persisted/readback status. Clinician edits/saves/reopens/exports through the existing authoritative workflow. Analysis completion is not physician review completion.
5. On hours/budget/connection/quality blockage, show the actual plain-language reason and usable next action. Display remaining daily model/compute capacity, queue/backlog and next eligible time. If compute is exhausted, next eligibility is the next approved Thai day/AI window, unless unknown work/ownership/security blocks remain. Never promise guaranteed readiness at a time when reconciliation or another GPU owner can still block it.
6. Reopen after app/network interruption and recover without submitting old accepted/sent/uncertain stages again. Existing results and human annotations remain intact.

## 3. Operator start/status/stop and fault handling

Start only the accepted tested source/build and new regular authority, after fresh private-route/authentication, DB, model asset/environment pins, ports, current journal/clock, device ownership/headroom and funds checks. Status distinguishes CPU/app/DB, authentication, assets, actual loaded models, bound-protocol qualification, source gates, hours, quota holds/intents, compute reservations, queue, in-flight/native-entry certainty and last real readback.

Health/status/polling must not initialize an unapproved load/forward or renew/reset a reservation. Loading multiple models on one owned worker consumes one funded residency interval, not one charge per model. Reserve before GPU use, avoid overlapping intervals, and show conservative charged time separately from observed elapsed/busy time. Choose/test bounded idle and healthy-retirement policy; no 'always-on' GPU beyond43200s.

Stop prevents new dispatch, persists backlog/intent state, drains within funded native/cleanup bounds, proves only the exact owned child/listener/tunnel stopped and releases only owned resources. It must not stop a team-wide service or delete DB/volumes/images. Routine safe child recycling under the new authority is allowed after confirmed cleanup; replay/restart of old uncertain work is not.

If process/route/model/result/DB/evidence logging fails, distinguish model/persistence/accounting facts and preserve durable records. Unknown send/native entry/cleanup keeps charge, source fence/quarantine and exact job reference. A timeout, cancel acknowledgement, day rollover, new worker epoch, ordinary app restart or stale PID is not proof of safe unlock. Reconcile authenticated old-job/owned terminal evidence before new conflicting inference. Report exact action/target/reason and whether outcome is denied/pending/uncertain.

No OS clock/timezone mutation to test midnight. No broad process kills, GPU resets, protection changes, ledger file deletion or hidden retries. Apply planned fault tests with synthetic/public inputs and explicit accounting; do not use real clinical data for debugging.

## 4. Installation candidate contents and checks

Build from an accepted clean bounded source/integrated main using existing allowlisted release builder. Verify source commit, frontend source digest/output set, software manifest/checksums, dependencies, platform/runtime requirements and model/provider/checkpoint/preprocessing inventory. `frontend/dist` is generated/ignored:rebuild on main and bind the final accepted main commit before packaging. A worktree build or older documentation-successor build identity does not satisfy exact release identity.

Include:

- Version/source/build identity, manifest and SHA256 inventory.
- Canonical no-code first-run/start/status/stop and regular-service integration steps that actually work on the tested topology.
- Secret-free examples for actor/workspace/project/backend connection, approved daily model/GPU/hours policy and private deployment paths; real values remain in operator-only config.
- Model asset/dependency/environment identity and offline delivery boundaries; no unqualified generic setup over qualified model environments.
- User batch/review/export and operator lifecycle/monitoring/recovery/rollback guides, evidence matrix and known limitations.
- Ownership/support contacts or responsible role and maintenance steps, without sending messages on the owner's behalf.

Exclude secrets/private keys/env files, weights, real patient images/PHI, runtime PostgreSQL/SQLite/Workspace state, ledgers/locks, dependency trees, caches, raw operational logs and unreviewed owner archives. Model assets/approved data use separately controlled inventory. Existing contract-only model helpers reporting BLOCKED/NOT_RUN must not be relabelled as a deployed GPU service.

First verify archive names/allowlist/checksums, then extract to a new isolated destination without overwriting any install. Test first launch/status/stop using synthetic/public data and explicit isolated config/DB where needed; never select the real source database by inherited `.env`. Confirm no model/network request outside the approved commissioning scope and no source-image mutation. Label installation candidate; do not label final medical/clinical release.

## 5. Rollback without destroying clinical work or quota history

Record accepted previous application/build identities and migration/authority compatibility before changing the running app. Keep old software package/config references and immutable evidence; do not include raw secrets in backup manifests. Back up approved local clinical state/images only through the existing authorized recovery process, not by copying an arbitrary live DB directory.

Rollback application code only when compatible with current schema, daily authority, source guards and pending job state. Stop/drain the exact new owned app/worker safely, preserve all results/labels/manifests/journals/unknown states, select the prior compatible build and verify isolated readiness before returning to service. A prior app that lacks the new authority cannot dispatch through an old raw route as a rollback shortcut; keep AI blocked/manual mode until compatible.

Do not restore an older ledger/counter/runtime directory, resurrect a closed finite window, reset the day, requeue a terminal/sent job, drop a schema/volume or overwrite clinician data. Database restore/role/grant changes are separate actions needing their explicit target and authority. Guard-aware restore is still unqualified in the historical source; retain refusal and report the limitation unless separately amended/tested. An unguarded rehearsal or dataset export is not a full recovery backup.

Required rollback proof:software selection/health/private identity, unchanged clinical/source hashes/revisions and new-service accounting history, no duplicate execution, no other-team process/volume changes, exact remaining blocked items. If safe application rollback is incompatible, preserve state and report a bounded operational block; do not force destructive cleanup.

## 6. Final handoff evidence

Provide accepted source and remote refs; main tracked/index state plus preserved owner-untracked list; required test results/skips; served frontend identity; installation candidate path/manifest/checksums; authenticated multiuser isolation/fairness; actual per-model/modality result/readback/human-edit/reopen/export proof; commissioning/daily counters and exclusive GPU reservations; safe owned start/status/stop/idle/exhaustion behavior; measured performance limits; and exact not-run/blocked/full-M1/hospital/guarded-recovery statuses.

No statement of500-image throughput, continuous16h AI readiness, clinical validation or all-Hospital-M1 completion follows merely from1500/day authorization or a successful smoke.
