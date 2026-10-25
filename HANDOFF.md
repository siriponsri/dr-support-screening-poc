# DR Screening — Hospital M1 detailed handoff

> Checkpoint: 23 October 2026, approximately 17:10 Asia/Bangkok (10:10 UTC).
> Recipient: Pepo GPT Dot / the next explicitly assigned engineering owner.
> Operational status: **PAUSED BY OWNER. M1 IS NOT COMPLETE.**
> The owner subsequently requested creation of this exact `HANDOFF.md` in the repository.
> This document is a checkpoint, not an instruction to resume automatically.
> Read-only re-verification addendum: section 22 (23 October 2026, 10:53 UTC).
> **Engineering resumed by the owner; progress checkpoints: sections 23 and 24.**

## 1. Read this first

The owner paused implementation and requested a detailed handoff. No new model
requests, GPU windows, builds, tests, migrations, runtime restarts or integration
merges are authorized merely by reading this file. Resume only when the owner
requests it. The documentation delivery itself is separately authorized.

The final engineering goal remains **two usable Hospital M1 QA profiles from one
codebase: QA Server and QA Local, with deployment packages, reproducible manual
step-by-step operation, actual model API inference, physician review/labeling,
PostgreSQL persistence, reopen/edit/export, and recovery**. A metadata probe,
HTTP health 200, loaded model, synthetic fixture or closed batch does not meet
that goal.

Important current distinctions:

- Authoritative `main` source is at `7be279deb422c1fb1d50e076f58d008b293e733a`.
  It was synchronized with the actual remote before this document was created.
- A newer, clean, pushed **candidate** at
  `8329c31dfbe973b6819479f435e0c146906e85e6` passed the latest full backend run:
  **1771 passed, 67 skipped, 512 warnings, 148.10 seconds, exit 0**.
  It is **not merged into main**.
- The ordinary app factory integration is **unfinished** in a separate worktree:
  one uncommitted file, `dr_support/api/_factory.py`, 92 insertions / 3 deletions.
  Preserve it; do not serve or merge it as a finished implementation.
- Actual new runtime/authority password authentication and actual app/PG context
  qualification passed. The context qualification made **zero model RPCs and
  zero inference requests**.
- Original batch: **467 PASS_READBACK, 9 FAILED_NO_RETRY, 4 BLOCKED_PREMODEL**;
  all 480 original jobs remain terminal. There is no original pending work.
- Current preserved use is **525 requests**. Owner-approved cumulative cap is
  now **549**, leaving **24 requests**, subject to durable activation and exact
  scope. **No Hospital M1 window has been activated.**
- Actual main-browser interactive inference acceptance for all three models is
  **NOT_RUN**. Hospital hardware acceptance and complete dual-profile packages
  are **NOT_RUN / incomplete**.
- Local listeners observed at the pause checkpoint: app `127.0.0.1:8000`, PG
  `127.0.0.1:54805`; no listener at `47860` or `17860`. Listener presence is not
  model/API acceptance. The existing app process was not restarted onto the new
  source during this checkpoint.
- Do not claim production readiness, clinical validation, improved diagnostic
  accuracy, or a measured Lightning AI T4 comparison.

The earlier approximately **50%** estimate was a subjective estimate of overall
engineering/delivery progress against the full dual-profile goal. It is not an
acceptance score, a test completion fraction, or a clinical metric. Foundations
and source controls are substantially ahead of installed service and user E2E
acceptance. Do not increase this percentage from test counts alone.

The goal service returned `goal: null` when pause was requested; consequently no
tool-side `paused` transition could be recorded. Work is nevertheless paused by
the owner's explicit instruction. Do not create a replacement goal/orchestration
to conceal that state.

## 2. Authoritative paths, instructions and reading order

```text
Repository / authoritative main:
C:\Users\User\Desktop\myProject\dr-support-screening-poc

Existing artifact base (preserve):
C:\Users\User\Documents\Codex\2026-10-21\task

Canonical Python:
C:\Users\User\Desktop\myProject\dr-support-screening-poc\.venv\Scripts\python.exe

New approved private credential directory:
C:\Users\User\AppData\Local\DRScreening\M1PrivateConfig

Private QA host:
dr-train / 100.77.149.83

Private QA project:
/home/siripon/projects/dr-model-api-qa
```

Read in this order before resuming substantial work:

1. `AGENTS.md`, referenced `C:\Users\User\.codex\RTK.md`, current `README.md`,
   `DESIGN.md`, and relevant operational/user manuals.
2. `docs/milestone/m1/HOSPITAL_M1_RELEASE_CANDIDATE_SPEC.md`.
3. `docs/milestone/m1/M1_MUTABLE_PRISM_ENTRY_AUTHORITY.md`.
4. `docs/planning/HOSPITAL_M1_GPU_REQUEST_PROPOSAL_20261023.md`.
5. `docs/planning/BATCH_THIRTEEN_TERMINAL_FAILURES_20261023.md`.
6. `docs/operations/M1_TEST_CREDENTIALS.md` and `BACKUP_RESTORE.md`.
7. This handoff plus the actual current Git state and relevant component source.
8. Historical owner-provided artifacts, under the artifact base:
   - `CLI_SINGLE_WRITER_HANDOFF_20261022.md`
   - `local-app-candidate-c02/LOCAL_C02_STATUS.json`
   - `local-app-candidate-c02/LOCAL_C02_FROZEN_RECEIPT.json`
   - `local-feature-evidence-c02/LOCAL_VERIFICATION_FINAL.json`
   - `batch-runtime-candidate-b02/OPERATIONAL_MEMORY.md`

The earlier AGENTS wording that there was no separate HANDOFF source describes
the repository before the owner requested this new file. This file does not
replace frozen normative specifications or operating manuals.

Use `rtk` / `rtk proxy` for shell commands. The current environment reports no
RTK hook installed; do not install/reconfigure hooks as incidental work.
PowerShell builtins need a PowerShell process under the proxy. Preserve
`CODEX_HOME`, existing SSH identity, provider environments and workflow.

## 3. Scope and acceptance contract

### QA_SERVER

- Windows/hospital app, PostgreSQL and originals use approved local storage.
- Model API is on the existing private QA route to dr-train, when that route and
  data transfer are actually approved for the target environment.
- Use an authenticated, owned SSH loopback tunnel when the remote API binds
  loopback. Never place remote `127.0.0.1` in Windows configuration without the
  corresponding verified tunnel.
- A closed hospital VLAN is not assumed to reach Tailscale or dr-train.

### QA_LOCAL

- App, PostgreSQL, models, weights and images stay on the hospital target.
- Ordinary operation must work offline, with no silent dr-train/cloud fallback.
- HTTP `remote` runtime can still mean a separate loopback model process.
  It does not necessarily mean an external machine.
- Explicit `DR_SUPPORT_DEPLOYMENT_PROFILE=QA_LOCAL`; preserve the approved
  loopback / existing `gateway` Compose service rules. The image name
  `model-gateway` is not the Compose DNS service name.
- Actual hospital target hardware is not available/qualified at this checkpoint.
  Do not open its named GPU window on another host and call it hospital proof.

### Acceptance matrix at pause

| Requirement | Current evidence | Remaining acceptance |
| --- | --- | --- |
| A: reusable service lifecycle | Source controls and earlier finite sessions exist | Installed start/status/stop, actual native supervision, bounded queue/deadlines, service remains available during user session |
| B: install / cold start | Earlier local DB autostart workflow and startup helpers qualified in their recorded scope | Complete two-profile package, fresh install and restart on intended targets, offline inventory |
| C: physician workflow | Earlier local real-image + simulated-AI PG/export flow; closed real batch results | Fresh main UI with all three real models, physician edits, save/reopen/edit/export, test/physician data separation |
| D: mask / reversible post-filter | Actual retained PRISM raw/post-filter/undo evidence | Chosen-stage UI proof and human adjudication of peripheral false ROIs / potentially hidden true lesions |
| E: persistence / recovery | Actual DB fence controls, new role logins, app context proof; earlier isolated backup/restore | Complete guard-aware Hospital M1 backup/restore + originals + reopen/export on target |
| F: two-profile evidence | Partial historical evidence, component source tests | Profile-specific real acceptance, screenshots, failures, package/manual commands and resource behavior |

No frozen admission, patient/eye, clinician-review, annotation provenance,
original-coordinate, model identity or source-policy contract may be weakened
to finish these rows. Clinical validation remains separate.

## 4. Git checkpoint and preservation requirements

### Authoritative main before this documentation-only delivery

```text
root/worktree: C:\Users\User\Desktop\myProject\dr-support-screening-poc
branch: main
HEAD: 7be279deb422c1fb1d50e076f58d008b293e733a
origin/main (actual ls-remote): same SHA
tracked changes: none before HANDOFF.md creation
existing untracked files: 287, preserved
```

Existing untracked paths include:

```text
.vscode/
DR_M1_LOCAL_CODEX_HANDOFF.md
docs/benchmarks/
docs/deployment-preparation/
docs/presentation/CLAUDE_DECK_REVIEW_AND_REVISION_HANDOFF_20261016.md
docs/presentation/CLAUDE_IMPLEMENTATION_EVIDENCE_HANDOFF_20261016.md
docs/presentation/CLAUDE_TEAM_PROGRESS_DECK_REVIEW_20261016.md
docs/presentation/dr-screening-demo/
```

These are existing owner work. Do not absorb, overwrite, delete, stash, reset,
clean, blanket-stage or reinterpret them as generated cleanup. In particular,
`DR_M1_LOCAL_CODEX_HANDOFF.md` is not this newly requested file.

This handoff was explicitly authorized as a documentation-only addition on
main. It does not authorize implementation edits directly on main. After its
commit, `main` will have a documentation successor of `7be279d`; use the actual
new HEAD for delivery verification, while retaining the implementation base
above. Do not make this document falsely claim a future self-referential hash.

### Active candidate branches/worktrees

All paths below are relative to the existing artifact base. Short SHAs are
identifiers for navigation; full key SHAs follow the table.

| Worktree | Branch | HEAD at pause | State / integration |
| --- | --- | --- | --- |
| `m1-native-accounting-worktree` | `feat/m1-native-accounting` | `8329c31` | Clean, pushed; latest combined backend validation; NOT in main |
| `m1-app-workspace-runtime-worktree` | `feat/m1-app-workspace-runtime` | `1dfdeba` | One uncommitted `_factory.py` diff; no remote branch observed; interrupted |
| `m1-workspace-remote-worktree` | `feat/m1-workspace-remote` | `6c0de66` | Clean, pushed; final checkpoint-name delta review pending; NOT in main or `8329c31` |
| `m1-workspace-executor-worktree` | `feat/m1-workspace-executor` | `1408977` | Clean, pushed, independent review approved; included in `8329c31` |
| `m1-prism-checkpoint-pins-worktree` | `fix/m1-prism-checkpoint-pins` | `2c1c390` | Clean, pushed, independent review approved; included in `8329c31` and WIP app branch |
| `m1-context-qualification-worktree` | `feat/m1-context-qualification` | `8dc56ee` | Clean, pushed, independent review approved; actual context PASS; included in `8329c31` |
| `m1-workspace-transport-worktree` | `feat/m1-workspace-transport` | `5c9288c` | Parent transport/host changes reviewed with executor changes; retained |

```text
Combined native/accounting candidate:
8329c31dfbe973b6819479f435e0c146906e85e6

Unfinished app integration base:
1dfdeba18f6ee161aee17c6a598512833bbd1bac

Remote provider candidate:
6c0de66478f6f37d504c52a98c48f9c13787a978

Workspace executor candidate:
14089774853761511dfbe20717bc1e69100a88c1

Checkpoint-key fix:
2c1c3905cf7c434673b669fea5c00fc6e661fffe

Actual-context helper:
8dc56eebff34f21341e42561a5618311bba65de0

Native consumer repair included in 8329c31:
248a9ee3d9075dd0a66bcb733bdfebe2ee6a4391
```

The WIP app branch has dependency merges of remote `6c0de66` and core fix
`2c1c390` on the main implementation base. It does not thereby include all
changes in `8329c31`. Reconcile exact ancestry/source during resumed work;
never select a version merely because its timestamp is newer.

### Retained earlier worktrees

These were not deleted at pause. Recheck actual ancestry before any eventual
cleanup, and remove only branches/worktrees owned by this task after integration.

| Worktree | Branch / checkpoint |
| --- | --- |
| `m1-preview-authority-hooks-worktree` | `feat/m1-preview-authority-hooks`, `7be279d` |
| `m1-test-credentials-worktree` | `feat/m1-test-credentials`, `24bc948` |
| `m1-workspace-context-worktree` | `feat/m1-workspace-context`, `de22021` |
| `m1-workspace-authority-core-worktree` | `feat/m1-workspace-authority-core`, `11a6ef7` |
| `m1-writer-fence-worktree` | `feat/m1-app-writer-fence`, `be143a9` |
| `m1-factory-writer-fence-worktree` | `feat/m1-factory-writer-fence`, `c9a49f7` |
| `m1-store-writer-fence-worktree` | `feat/m1-store-writer-fence`, `afe2b5d` |
| `m1-accounting-continuation-worktree` | `feat/m1-accounting-continuation`, `728f8c3` |
| `m1-hospital-recovery-v3-worktree` | `feat/m1-hospital-recovery-v3`, `02b0675` |

Other owner worktrees, including the separate clinician UI checkout and older
Orca checkout, are outside this cleanup scope.

## 5. Exact unfinished work: ordinary app factory binding

Worktree:
`C:\Users\User\Documents\Codex\2026-10-21\task\m1-app-workspace-runtime-worktree`.

At pause, only `dr_support/api/_factory.py` is modified, with 95 changed lines
(92 additions / 3 deletions), unstaged. No tests, new context-reader changes or
new integration document are present in that worktree's current diff.

The partial patch introduces:

- A `_workspace_composition` decorator and private optional
  `workspace_authority` / `workspace_prism_provider` arguments to `create_app`.
- Exact authority/provider/context-reader type and object-identity checks.
- Synchronous authority / bind locks around app composition.
- Explicit QA profile, PostgreSQL workspace and migration-verify requirements.
- Matching loopback endpoint and cached loaded-identity checks.
- Actual runtime DB principal preflight before normal app composition writes.
- A partial owned-provider branch and cached metadata/connection probes.

It is visibly incomplete at the stopping point:

1. `owned_connection(request)` is called by the model-connection endpoints but
   no definition is present in the inspected factory file.
2. The inspected `ReviewPrismPreview(...)` construction still does not receive
   the workspace authority.
3. `PrismPreviewService` still registers plans only for old fixed/batch profiles;
   the ordinary workspace authority registration is not connected there.
4. No `context_reader.bind(...)` call is present in the inspected factory file.
5. The new branch assigns a PRISM-only provider dictionary. Preserve/assemble
   the supported USPEC and RETFound paths; do not finish a PRISM-only demo and
   present it as all-three-model acceptance.
6. The context reader's exact provider allowlist has not yet been updated in
   this WIP diff for the new `WorkspaceRemotePRISM` class.
7. No focused/full tests or independent review qualify this partial patch.

Do not execute the WIP factory against live data expecting a complete session.
Do not discard it and start over without inspecting its intent and dependencies.

### Agreed integration constraints for the next implementation owner

- Private `create_app` pair: both authority and workspace PRISM provider, or
  neither. Exact supported types; `provider.authority is authority`; exact
  unbound `WorkspaceContextReader` before first composition.
- Explicit selected PostgreSQL `workspace_id`; no latest-open selection fallback.
- Genuine least-privilege runtime preflight before any composition write;
  migration mode must be `verify`.
- Hold authority ownership during synchronous composition only. No lock held
  across ASGI `await`. Bind the reader exactly once before exposing the app.
- Install the owned provider and preview service before route installation.
  Existing route closures capture their original service; replacing only an
  `app.state` attribute later is insufficient.
- Preserve separately assembled supported USPEC/RETFound providers.
- Cached model/capability/connection GETs and connection-test POST must not
  perform RPC, replace the provider, mutate plan generation or pretend liveness.
- Entry-fenced connection operations must refuse appropriately. URL/token swap
  must be rejected before probing or changing state. Cosmetic display-name
  changes should not invalidate an otherwise unchanged source/plan.
- Cached identity means last authenticated LOADED identity; do not update
  `checked_at` during passive polling or claim inference passed.
- Preserve the protected PRISM preview acknowledgment and reject legacy raw
  lesion-route bypasses.
- Context capture must use exact cached provider identity, without an RPC.

## 6. Source already integrated into main

### Existing local features and startup/recovery foundation

Earlier qualified local source/assets were integrated rather than replacing the
project with a new orchestration. Existing workflow includes clinician review,
raw AI separation, grade/lesion persistence, mask preview/reversible suppression,
training exports and physician-confirmed grading-folder behavior in its recorded
qualified scope. Current M1 actual-model acceptance remains a separate task.

Main also includes deployment-profile controls, owned Docker startup help,
migration-verify startup, recovery source/target protections, and continuation
accounting foundations. Read the current manuals rather than using old candidate
launch commands after renames.

### App/store writer fence

`dr_support/services/source_mutation_gate.py` and its integrated call sites:

- In-process gate uses an `RLock` for short state updates, not an ASGI-wide lock.
- Writer scopes track generation and active writers. Entry acquisition refuses
  busy/stale/fenced state; there is no timeout-based automatic unlock.
- `invalidate=False` supports enriching reads: entry is blocked while active,
  while a generation increment follows actual nested mutation.
- Store, workflow, WorkspaceManager, artifact prepare/restore, relevant factory
  writes, model connection changes and result saves use the gate.
- Plain 409 refusals preserve unsaved work when entry is fenced.
- Legacy `None` behavior is retained; supported supplied boundary uses exact type.
- Fixed/batch QA and frozen clinician semantics remain distinct.

### Workspace entry authority

`dr_support/services/prism_workspace_authority.py`:

- Unregistered internal authority binds a context reader, PostgreSQL fence and
  authenticated old-job status reader.
- Private-root validation precedes creation; exclusive owner file uses `O_EXCL`
  plus a real retained OS lock, not just a filename convention.
- Full canonical raw context, exact object identities and runtime context are
  bound to a staged plan; matching revision alone is insufficient.
- Original/wire context is staged before preparation. Registered snapshot and
  binding are frozen and checked again before accounting and send.
- Final entry requires app gate, authenticated challenge and committed DB fence.
- Consumed plan IDs/high-water state are durable. Uncertain outcomes retain
  quarantine across restart. No replay, reset, TTL unlock or cancel-ACK unlock.
- Only the authenticated original binding's native-entry/terminal proof can
  release the entry. A new epoch cannot clear the old one.
- A post-release logging failure poisons subsequent inference while permitting
  a valid completed result to be saved after verified fence release.

**Known main-only defect still open:** checkpoint keys are validated with an RPC
identifier regex that rejects real checkpoint path-like names. The approved
`2c1c390` fix is in the candidate, not main. It accepts bounded opaque printable
checkpoint keys without interpreting paths or changing model/weight identities.
Do not change expected real pin hashes to make the old validator pass.

### Actual workspace context reader

`dr_support/services/m1_workspace_context.py`:

- Exact approved test DB/roles and explicit loopback PG target, including actual
  driver/current/session principal checks and non-elevated role/membership checks.
- No PostgreSQL service/options/environment override escape.
- Joined raw case + raw workspace JSON in one read-only statement.
- Exact app/store/provider/WorkspaceManager/derivative-service identities.
- No default/enrichment writes or mutation of observed case caches while reading.
- Nonblocking manager-then-store acquisition avoids the opposite lock order.
- Complete nonsecret runtime identity is included; credentials/DSNs are not.
- Real principal catalog checks use OIDs so missing guard-schema privileges are
  not worked around by grants.
- PostgreSQL timestamp representation differences are normalized for comparison
  only; the raw authoritative catalog is not rewritten.

External privileged file replacement or administrator mutation is outside the
in-process gate's ownership. Do not claim that an app lock prevents that.

### Preview hooks

`dr_support/services/prism_preview_runtime.py` supports an optional exact
workspace authority and shared gate, stages before prepare, registers the exact
plan and authorizes execution outside validation/store locks. The lock order is
authority -> manager -> store. It does not change the old fixed/batch path.
The ordinary factory still needs the binding described in section 5.

## 7. Candidate components not yet fully integrated

### Loaded workspace executor / existing host

`1408977` adds the workspace executor and trusted existing-host registration:

- Exact loaded PRISM provider, existing checkpoint/preprocessing identity,
  one-load guard; no fabricated warmup/model forward for readiness.
- CPU prepare can use internal unknown-origin data only for mask computation;
  execute reconstructs the actual bound origin/modality and still enforces
  source policy, FUNDUS_ACCEPTED and GRADABLE conditions.
- CFP and UWF use the protected native-entry callback after load; fatal entry
  errors cannot fall through to fallback/retry.
- Existing authenticated child application is extended. No new public listener,
  alternative orchestration or environment-selectable provider shortcut.
- Trusted `enable_workspace_executor` registration is exact-type/identity bound
  and rejects a host with previous jobs/tickets or fixed/demo/batch ownership.
- Loaded capability metadata advertises HOSPITAL_M1, CFP/UWF support and protocol
  only when actual identity matches pins. It is not an inference/clinical pass.
- Existing fixed UWF-only contracts remain unchanged.

Independent source review approved the combined transport/executor changes.
Actual live GPU/native supervision and accounting assembly remain NOT_RUN.

### Workspace remote PRISM client / status reader

`6c0de66`, `dr_support/providers/prism_workspace_remote.py`:

- Exact owned `ExplicitHttpChannel`, authority, URL/auth/transport identities and
  independently supplied five-field pin expectation.
- Authenticated capabilities plus same-epoch/pin LOADED readiness are required.
- Cached metadata remains research-only, CFP-trained / UWF experimental;
  `inference_validation` remains NOT_RUN until real acceptance.
- No proxy/environment redirect escape, automatic retry or silent renegotiation.
- Authority authorization precedes inherited execution.
- Independent status reader checks the durable old job/epoch binding, scope,
  pins and native proof flags. It does not infer readiness from client cache.
- Latest `6c0de66` corrects opaque real checkpoint-name validation. The earlier
  review requested this change. Final independent delta approval was not
  received before pause; do not relabel that review APPROVE automatically.

### Native admission / accounting consumer

Candidate `scripts/qa/batch_runtime/m1_admission.py`, including repair `248a9ee`:

- Reuses existing continuation ledger, named budget window, funded lifetime
  lease and actual owned `WorkerSupervisor` child identity.
- Durable intent/admission is written before native supervisor admission/ACK.
- Uncertain ACK is consumed and never retried automatically.
- PRISM HTTP 202 is not terminal completion. Authenticated terminal/ordinary
  model response permits RESPONSE_RETAINED; independent real PG readback is a
  separate PASS_READBACK step.
- Actual response observation, response-log retention, DB persistence and
  accounting/supervision outcomes remain separate facts.
- A log failure cannot erase a genuine subsequent database readback.
- If ledger integrity is uncertain, status reports uncertain usage and a lower
  bound, not a falsely exact low count.

The 19 targeted controls use the actual durable ledger/budget with controlled
clock/child boundaries, not a live native model. Independent source review of
`248a9ee` approved the repair. The combined candidate is pushed at `8329c31`.

**Remaining own-code work:** attach the ordinary owned demo/session lifecycle to
this consumer and the actual child HTTP/admission ACK/status/result/readback
adapters. This has not been implemented/qualified as a real running M1 service.
Do not open a GPU session merely because the standalone consumer tests pass.

## 8. Approved private credentials and actual PG security proof

### Exact approval and applied directory scope

The owner explicitly approved creation of:

```text
C:\Users\User\AppData\Local\DRScreening\M1PrivateConfig
```

Protected DACL, inheritance disabled on that new directory, only the actual
owner account `DESKTOP-C8EHASQ\User`, SYSTEM and Administrators with FullControl;
new files inherit from it. Applied successfully and passed the existing privacy
checker before and after credential creation. Old directories/ACLs were not
changed. This approval does not extend to other paths, firewall or Linux token.

The exact isolated test objects previously approved and now retained:

| Object | Identity |
| --- | --- |
| Database | `dr_support_m1_interactive_test_20261023` |
| NOLOGIN owner | `dr_support_m1_owner_test` |
| Runtime LOGIN | `dr_support_m1_runtime_test` |
| Authority LOGIN | `dr_support_m1_authority_test` |

The two new LOGIN role passwords were generated and stored only through the
reviewed helper after directory privacy passed. No existing role/password was
changed. Both genuine password connections passed (`pgconn.used_password == 1`),
with matching driver/current/session role and no superuser, CREATEDB, CREATEROLE,
replication or BYPASSRLS privileges.

Private files, **never print, commit, attach or include in a package**:

```text
M1PrivateConfig\m1_runtime.env       # secret runtime DSN
M1PrivateConfig\m1_authority.env     # secret authority DSN
```

Secret-free receipts retained in the same directory:

```text
credentials-staged.json
credentials-login-proof.json
```

Do not casually read private files into terminal output even when a receipt is
expected to be secret-free. Use the reviewed safe reader/metadata path.

`scripts/qa/configure_m1_test_credentials.py` and
`docs/operations/M1_TEST_CREDENTIALS.md` are integrated into main. Provisioning
checks exact objects, initially NULL passwords, non-elevated memberships and
idle fence, writes new exclusive/fsynced files, then uses SCRAM verifiers in a
transaction. It does not automatically overwrite/resume.

**Do not rerun `--apply-test-credentials`: existing files/non-NULL passwords now
intentionally refuse.** Correct app key is
`DR_SUPPORT_DATABASE_MIGRATION_MODE=verify`; an earlier incorrect schema-mode key
was repaired before the successful apply.

### Old Windows ACL finding, separate from the new directory

Historical report: artifact `M1_ACL_READONLY_FINDINGS_20261023.md`.
Old `local-state/release` / `postgres.env` inherited four non-allowlisted
Modify/Synchronize allows:

```text
S-1-5-21-3985673817-1618037573-1800918682-984004028
S-1-5-21-2710376491-1507090220-2196537897-2811563990
DESKTOP-C8EHASQ\CodexSandboxUsers
S-1-5-21-1793372616-2446623825-2318635416-2137801790
```

Three unresolved SIDs and the managed sandbox group are not the same as four
identified unrelated humans. The grants do permit read/modify by their holders;
the checker conservatively refused its allowlist. No Everyone/AuthenticatedUsers
entry was identified among these four. Do not infer safe/unsafe solely from the
number of rules, and do not modify those old ACLs under the new-directory grant.

### Actual DB entry fence

Existing approved test provisioning created the new isolated DB/roles and
`dr_support_entry_guard` sidecar with an entry sentinel/functions and statement
triggers on `workspaces`, `review_cases` and `legacy_migration_receipts`.
Runtime has intended SELECT/INSERT/UPDATE only; no owner/authority membership.

Actual SQL qualification: **12/12 PASS** in its recorded scope, including
two-connection blocking, committed fence survival after connection close,
same-revision changed-payload refusal and denied DDL/trigger-disable/guard-clear/
TRUNCATE/role-escalation/replication-role attempts. Its initial session-role
permission controls are distinct from the later genuine password-login proof.

`PostgresEntryFence` commits before granting entry, uses bounded lock/statement
timeouts, and requires authenticated old-status proof before clear. No TTL unlock.

**Do not rerun test-scope provisioning or drop/reset the existing DB.** Names now
exist and collision refusal is intentional. Do not broaden grants to simplify QA.

## 9. Actual app + PostgreSQL context qualification

Reviewed helper candidate: `8dc56ee`.
One apply was executed successfully; no automatic retry/resume.

```text
Receipt:
C:\Users\User\Documents\Codex\2026-10-21\task\
  m1-context-qualification-20261023-01\CONTEXT_QUALIFICATION.json

Retained workspace:
m1_context_75b3b5bb32f84c58bda5fa2fea24c6d2
```

| Receipt field | Actual result |
| --- | --- |
| Overall | APP_CONTEXT_PASS |
| Genuine authenticated runtime preflight | PASS |
| Migration verification | PASS |
| Actual app construction / complete context | PASS |
| Raw DB readback / exact object identity | PASS |
| Observed caches | UNCHANGED |
| Gate generation | 6 |
| Source origin | SYNTHETIC |
| Model identity | CONTROL_ONLY_NO_MODEL |
| Model RPC / inference requests | 0 / 0 |
| Native model / inference / clinical validation | NOT_RUN / NOT_RUN / NOT_RUN |
| Evidence logging | PASS |
| Partial state retained / automatic resume | true / false |

It uses actual factory/catalog/manager/store, one engineering synthetic case at
revision 0, and an explicit reject-all mock transport with control-only pins.
No real image/model inference, physician label or clinical gold was created.
Input/output directories are retained. This is actual app/PG/context proof, not
actual AI proof. The helper's documentation follow-up recording this actual
receipt was not committed before pause; this section supplies the checkpoint.

Do not rerun into the same output or overwrite the retained workspace.

## 10. Validation and independent review matrix

Counts apply only to their recorded revisions and command scope. They are not
additive, and older skipped/ignored tests must not be counted as passes.

| Component / revision | Evidence | Limit |
| --- | --- | --- |
| Combined candidate `8329c31` | Full backend 1771 PASS / 67 SKIP, 512 warnings, 148.10 s, exit 0; whole Ruff passed before run | NOT main; no GPU/browser/installed-service acceptance |
| Native consumer repair `248a9ee` | 19 focused controls; independent APPROVE | Controlled child/clock, not live native execution |
| Core checkpoint fix `2c1c390` | 74 PASS / 1 SKIP; independent APPROVE | Real key-shape/source compatibility, no model call |
| Workspace remote `6c0de66` | Full 1708 PASS / 67 SKIP, 161.85 s; focused 156 PASS / 1 SKIP; Ruff | Final delta approval pending after previous REQUEST_CHANGES |
| Workspace executor `1408977` | Focused 183 PASS; earlier full 1550 PASS / 51 SKIP in recorded narrower scope; independent combined review APPROVE | Earlier full excluded historical ACL-mutation module; latest combined run covers new default-skip policy |
| Context helper `8dc56ee` | 118 focused PASS; full 1663 PASS / 52 SKIP, 156.33 s; Ruff; independent APPROVE | Earlier full excluded historical ACL-mutation module; actual context result is separate section 9 |
| App factory WIP | No qualifying test/review | Must not infer PASS from dependency branches |
| New main after eventual candidate integration | NOT_RUN | Must run appropriate main regression before claiming integrated acceptance |

The full `8329c31` run was already in flight before pause; its completed output
was collected after pause (exec session 95030). **No new test was started to
obtain that result after the stop request.** The completion is console evidence;
do not invent a persisted JSON report if no such report is present.

Native permission-mutation fixtures now require explicit opt-in. Do not set
`DR_SUPPORT_TEST_ALLOW_PERMISSION_MUTATIONS=1` as routine validation. Default
skip is intentional; a normal test run must not change real filesystem ACLs.

Agent states at pause:

- Root: documentation/checkpoint only; implementation stopped.
- `deployment_profile_map`: interrupted; explicitly told not to resume or edit.
- `interactive_runtime_review`: completed, APPROVE for `248a9ee` and `2c1c390`;
  did not run new tests/live calls and relied on parent-reported test output.
- `postgres_recovery_map`: completed actual context checkpoint; remote review
  still REQUEST_CHANGES pending the corrected checkpoint-name delta approval.

No release of ownership to a new autonomous writer was performed. Pepo must
receive explicit resumption/ownership and preserve the single-writer arrangement.

## 11. GPU ledger, approved budget and activation gap

### Immutable closed batch

| Quantity | Preserved value |
| --- | ---: |
| Unique images | 240 = UWF 186 + CFP 54 |
| Original planned jobs | 480 = PRISM 240 + USPEC 186 + RETFound 54 |
| New batch ATTEMPT_INTENT | 476 |
| Historical use | 49 |
| Total used | 525 |
| PASS_READBACK | 467 = USPEC 184 + RETFound 53 + PRISM 230 |
| FAILED_NO_RETRY | 9 = USPEC 2 + RETFound 1 + PRISM 6 |
| BLOCKED_PREMODEL | 4 PRISM |
| Original pending | 0 |

Ledger:
`demo-batch-evidence-20261022-b03/accounting/LEDGER.jsonl`, 1423 rows at the
recorded closed anchor. Preserve it byte-for-byte and verify before new work.
Never replay terminal jobs, reset historical 49, reset clocks or auto-retry an
uncertain send. PREMODEL is not a native inference failure.

### Owner-approved extension

`docs/planning/HOSPITAL_M1_GPU_REQUEST_PROPOSAL_20261023.md` is
**OWNER_APPROVED, NOT ACTIVATED**:

- 20 added requests plus old 4 remaining = **24 available**.
- Cumulative cap **549**, used **525**.
- Server allocation 9: fresh 3, restart 3, explicit failure/recovery 3.
- Local allocation 6: fresh 3, restart 3, only when actual target exists.
- Post-fix verification allocation 9: new separately scoped intents after
  concrete repair; historical failed jobs remain terminal.
- Initial mask comparison uses retained actual PRISM outputs: **0 new requests**.
  A new pre-mask/model-input ablation is outside that allowance.
- At most two named windows:
  `HOSPITAL_M1_QA_SERVER_20261023` and `HOSPITAL_M1_QA_LOCAL_20261023`.
- Each window GPU0 <= 10800 seconds / wall <= 14400 seconds.
- No automatic renewal, paid service, window reset or reservation refund.

Some earlier normative/planning prose records the historical cap529/four slots.
The exact later owner-approved extension above governs new scope; it does not
rewrite old files/ledger to pretend they originally had cap549.

### Preserved time accounting

| Historical reservation | Seconds |
| --- | ---: |
| Original session, including full 600-second recovery lease | 4772.230 |
| Approved second PRISM session, 66 leases | 9800.644 |
| Closed interactive preload, zero inference requests | 2430.000 |
| Conservative aggregate across sessions | 17002.874 |

These are conservative reservations/charges across sessions, not measured GPU
kernel occupancy, one session's duration or an end-user latency benchmark.
Preload observed time was 521.948 seconds; the full 2430 reservation remains.

### Still not activated / not assembled

- No new Hospital M1 window, funded lease or model request has been opened in
  this implementation work.
- Actual durable proposal/approval binding and the 24 unique operation manifest
  are not materialized/activated for the live runtime.
- Continuation needs pinned old anchors, exact source/model/parameter identity,
  exact unique operation/job IDs, one owner/installation/clock and durable intent
  before dispatch. An agent-created file is not itself new human approval.
- Existing code can enforce one full 10800-second lifetime reservation; actual
  service ownership/native watchdog integration is still incomplete.
- QA Local adoption is `M1_LOCAL_ADOPTION_NOT_QUALIFIED`; do not create an
  independent local counter and lose the shared history.
- Check current durable ledger before **every** future request. If actual scope
  exceeds the remaining allowance, propose exact extra requests/time once and
  continue CPU/source work while waiting. Do not spend the cap merely to exhaust it.

Approved GPU identity only:

```text
GPU0: RTX 2080 Ti
UUID: GPU-044a8b11-4729-458b-a07b-297e45439419
```

Never touch GPU1/V100/Ollama. Never infer permission for other GPUs from a new
window or general willingness to expand budget.

## 12. Model API, SSH tunnel and current local runtime

### Existing remote configuration

Only confirmed approved host: `100.77.149.83`, user `siripon`, existing SSH key.
Do not substitute a hostname from old Windows `.env` or guess an API port.

Known historical paths:

```text
/home/siripon/projects/dr-model-api-qa
/home/siripon/projects/dr-model-api-qa/deployments/demo-batch-20261022-b03r8
.../runs/interactive-main-20261023-01
.../runs/INTERACTIVE_REMAINING_FOUR_20261023.json
```

The retained remaining-four marker is intentional. Do not remove/reset it to
make an old launcher run. A new continuation must preserve its history.

Existing Linux token location was inspected read-only:

```text
config                         owner/group siripon, mode 0700
config/private                 owner/group siripon, mode 0700
config/private/model-api.env   owner/group siripon, mode 0600
```

No symlinks were found in that inspected configuration path. Reuse the existing
approved token via its runtime loader; do not print/read its value into output or
create replacement Linux credentials. The new missing credential need was the
Windows DB runtime/authority pair; it has now been resolved separately.

Do not assume `stage/source42/approved_token_reader.py` exists; it was absent in
the earlier inspection. Resolve the loader from the actual start script rather
than copying a guessed path.

### Historical remote load-only proof

The prior finite interactive session loaded actual models without image forwards:

| Model | Recorded load time |
| --- | ---: |
| RETFound | 15.150 s |
| PRISM | 5.731 s |
| USPEC | 11.171 s |

It made zero image requests, then explicitly stopped for native request-watchdog
repairs. Its completion receipt confirmed owned cleanup/listener closure. This
is historical actual load proof, **not current service liveness or inference**.
The remote service was last verified stopped; no fresh remote restart was done
for this handoff.

### Known SSH identity / historical mapping

The existing approved command identity/options, without tokens:

```powershell
rtk proxy C:/Windows/System32/OpenSSH/ssh.exe -T `
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes `
  -o ConnectTimeout=8 `
  -i C:/Users/User/.ssh/id_ed25519_dr_train `
  siripon@100.77.149.83
```

Historical tunnel option:

```text
-o ExitOnForwardFailure=yes -L 127.0.0.1:47860:127.0.0.1:7860
```

This is a recorded mapping, **not a currently working M1 start command**. On
resume, read the actual remote runtime/listener configuration, check free local
ports, establish the approved owned tunnel and verify both ends/ownership.
`17860` is not reserved or proven merely because it was discussed as an option.
Do not open a public listener or change firewall/credentials/persistent access.

### Why the old service command must not be reused

The previous finite demo/session launcher still assumes the old remaining-four
cap/activation marker and ordinary API assembly. It is not the completed M1
native consumer/authority service. Existing process caps (worker around 2700 s,
Linux child hard cap <=2730 s, native request deadline 30 s) do not automatically
become a three-hour process lifetime because a budget allows three hours.
Resolve a bounded lifecycle within the approved envelope; no automatic renewal.
Do not broadly raise every timeout or remove the watchdog.

### Local runtime observed while preparing this handoff

| Surface | Checkpoint observation |
| --- | --- |
| App | LISTEN `127.0.0.1:8000`, PID 38564 |
| App process start | 23 October 2026, approximately 01:02:52 local time |
| PG | LISTEN `127.0.0.1:54805`, owning PID 9520 |
| Old tunnel local port 47860 | No listener observed |
| Candidate local port 17860 | No listener observed |
| Remote API | Historical stopped state only; not re-probed during handoff |

Existing local app URL: `http://127.0.0.1:8000/app/`.
No claim is made that this still-running process loaded the current main source.
Do not terminate unrelated Python/Node/SSH processes from a broad process list.
Pausing engineering did not mean deleting/stopping the user's existing app/DB.

Managed PG identity retained from earlier checks:

```text
container: dr-support-workstation-f40ca99eac2bf474-postgres-1
host:      127.0.0.1:54805
engine:    npipe:////./pipe/dockerDesktopLinuxEngine
version:   PostgreSQL 16.15 in the recorded qualification
```

No volume reset, container teardown or DB deletion is part of this handoff.

## 13. Closed batch failures: all nine FAILED and four PREMODEL

Full IDs/evidence and plans are in
`docs/planning/BATCH_THIRTEEN_TERMINAL_FAILURES_20261023.md`.
Prefixes below are navigation aids only; do not use a truncated ID for dispatch.
The historical report was inspected read-only; no job was resubmitted.

| Job prefix | Model/state | Supported retained finding | Remaining plan |
| --- | --- | --- | --- |
| `d5e8689c2d3c` | RETFound FAILED | App rejection; original HTTP/body missing; no recorded remote forward | Exact old cause UNKNOWN; new scoped CFP acceptance needs load/source/request/response/deadline proof |
| `4f81b1385489` | USPEC FAILED | App503 MODEL_UNAVAILABLE_AT_APP_BOUNDARY; underlying RPC detail missing; no execute | Preserve unknown root cause; serialization-only control is not inference |
| `b55fcbf67128` | USPEC FAILED | 503 after 5172 ms with 8,355,507-byte payload; no worker execute; reproduced 5 s ingress rejection | Batch upload allowance repaired; ordinary main large-body path still needs separate bounded proof |
| `cca990e31bc5` | PRISM FAILED | App502 before forward; repeated hook attach reproduced FORWARD_HOOK_ATTACH_ONCE defect | Batch attach-once repair exists; ordinary protected adapter still required |
| `f62327e97fc9` | PRISM FAILED | ADMITTED, zero recorded forwards, no completed model response | Exact cause UNKNOWN; admission is not model completion |
| `b4ae1fec4374` | PRISM FAILED | Executor409, recorded image-forward1, 5160.99 ms; hidden underlying exception | Retain UNKNOWN exception; preserve safe diagnostics/strict forward caps |
| `d00b79a3552e` | PRISM FAILED | FatalForwardBudget; old warmup21/image1 split, 11331.7 ms | Actual warmup-callsite accounting repair exists; do not reinterpret old split as reliable |
| `067b04056744` | PRISM FAILED | WORKLOAD_DEADLINE at 271.08 s; eighth admitted after seven completions, 17 image forwards, no full response | Reserve enough request/drain time; actual per-request native watchdog and bounded queue required |
| `78f185de1519` | PRISM FAILED | App502 / PRISM_INFER503 / unclassified transport failure after 171.999 ms; no correlated remote detail | Root cause UNKNOWN; do not call this a proven model-forward failure |
| `132dd9deb578` | PRISM CFP PREMODEL | Representative prepare/automated acknowledgment never reached execute | Verify one-use preview/timeout control; do not bypass acknowledgment |
| `0bc5cd24a6b5` | PRISM UWF PREMODEL | APP_REJECTED before inference; exact preparation diagnostic missing | Later body-span reproduction is not proof of this old cause |
| `3291bcd62794` | PRISM UWF PREMODEL | APP_REJECTED; missing per-job diagnostic/remote execution | Exact cause UNKNOWN; retain phase-specific refusal evidence |
| `f60eef2c84c2` | PRISM UWF PREMODEL | Preparation TransportError before second lease job's inference; exact transport reason missing | Persist allowlisted preparation diagnostics; old cause remains NOT_RETAINED |

App/transport, actual model forward, DB persistence, accounting and logging
failures must remain separate. In particular, failure to write a HANDOFF/log is
not an inference failure. Later passes/regression fixes do not turn these old
terminal records into successful jobs.

## 14. Images, masks, labels, exports and browser evidence

### Local C02 proof

Historical C02 used two actual UWF/CFP demo images with **simulated AI results**:
DB autostart -> app -> PostgreSQL readback -> export -> Chrome screenshots,
72.156 seconds. No model/QA requests. This demonstrated local wiring and is not
AI E2E or clinical validation. Continue from integrated source; do not restart
the project from isolated C02 or assume renamed B03 was frozen without checking.

### Actual retained batch results and post-filter

- 467 model results have recorded fresh PG readback in the closed batch scope.
- Retained 230 PRISM outputs support a CPU/no-new-request post-filter comparison.
- Historical gallery measurement: 65,639 raw ROIs, 8 proposed suppressed, 3
  UI-hidden, 7 undo operations in its recorded exercise. These are engineering
  counts with different states, not accuracy, recall or clinical benefit.
- Generic CPU method is preview / reversible ROI assist; it does **not** mask
  model input. Older 0/92 suppression and cached P4 1/92 are not new inference.
- Keep original bytes, raw ROI coordinates/IDs, uncertainty and undo. Do not
  force mask confirmation for every image or erase uncertain edge lesions.
- Any model-input pre-mask ablation is distinct from post-filter, must be labeled
  and needs separately approved new requests/time if outside current scope.
- Human adjudication of false peripheral ROIs / true lesions potentially hidden
  is still required; suppression count alone cannot prove reduced error.

### Export status

Historical new batch export: 240 records, 160 byte-preserving image copies in
UNREVIEWED, 80 skipped by existing admission, zero DR labels and zero lesion
labels. Those zero labels intentionally avoid auto-generated clinical gold.

Physician-confirmed labels and grading folders must remain separate from AI and
unreviewed material. Engineering test grade/workspaces must not enter physician
training datasets. Originals must not be renamed/recompressed/overwritten by
profile deletion, export, masking or cleanup.

### Browser / HTML status

- Historical representative evidence: nine screenshots across four jobs, with
  actual USPEC reaching PostgreSQL; this is not fresh all-three-model main proof.
- Historical partial presentation:
  `demo-evidence-session04-20261023/demo.html`, index and partial Thai manual.
- An earlier main Settings screenshot was emitted in chat, not saved as a PNG.
  Do not invent a file path for it.
- Last main settings used a TEST_ONLY Hospital M1 workspace, input
  `C:/Users/User/Desktop/demoImages`, output
  `local-state/hospital-m1-qa-output`, reviewer TEST_ONLY_ENGINEERING.
- CUA browser/tab identifiers from the previous session may be stale. Discover
  the installed CUA capability on resumption; never evade denied viewer access.
- Fresh M1 screenshot sequence, all-case gallery, real interactive mask/PRISM
  presentation and final two-profile Thai manual are incomplete.

No frontend changes were made by the later backend control work. The earlier
main bundle was rebuilt in its recorded scope:

```text
JS:  index-BOeyst4c.js
CSS: index-B6Tg1UWr.css
index SHA256:
64ea6429acf4fced10d0fc0ed96d2f112ba54ee2a71866dbeeb09ce0f6c6d5cb
```

If frontend source changes after resumption, rebuild on authoritative main after
integration; a feature-worktree build does not update main's served bundle.

## 15. Backup, restore and rollback

Earlier isolated ordinary v2 rehearsal:

```text
artifact: hospital-m1-recovery-qualification-20261023-01
source test DB: dr_support_m1_source_test_20261023
restore test DB: dr_support_m1_restore_test_20261023
schema: m1_recovery_test
```

Backup/restore/original hash and reopened engineering grade1 passed in that
recorded synthetic scope. Export returned 409 because WORKSPACE source lacked
the required authority; this remains BLOCKED, not relabeled successful.

Integrated Hospital v3 controls add independently pinned source/restore maps,
exact UWF/CFP roots/hashes/linkage/origin inventory, collision checks and explicit
workspace selection. They do not bypass source/privacy/export policy.

**Guard-aware backup is not qualified.** The current implementation deliberately
refuses an external entry-guard trigger on source/target/restored DB rather than
silently creating an incomplete backup. Complete Hospital M1 guard-aware backup,
actual target roots/permissions, isolated restore and physician reopen/export
remain NOT_RUN.

Canonical manual: `docs/operations/BACKUP_RESTORE.md`. Dataset export is not a
full recovery backup. Preserve immutable originals, release/workspace identity,
migration checksums and source/target separation.

Rollback principles:

- Leave previous release/assets and all old DBs/volumes untouched.
- Do not run `git reset --hard`, `git clean`, blanket restore/stash or destructive
  schema cleanup to obtain a clean state.
- The new test DB/roles/private files remain retained; no deletion is authorized
  as a rollback shortcut. Reprovisioning is not the next action.
- Uncertain entry/lease state remains quarantined until authenticated old proof
  / approved owner recovery; no force-clear or elapsed-time unlock.
- Choosing an earlier release must respect actual DB migration compatibility.
  There is no newly qualified one-click downgrade command for M1 yet.

## 16. Hardware specification draft and unmeasured limits

Existing draft:
`docs/planning/HOSPITAL_LOCAL_QA_MIN_MAX_DRAFT_TH_20261023.md`.
Its baseline source revision and counts are historical; do not present them as
the latest `8329c31` validation. Its resource values are inferred planning inputs.

| Resource | Proposed minimum QA starting point | Proposed upper QA configuration |
| --- | --- | --- |
| Linux GPU host CPU | 8 physical cores | 16 cores |
| Host RAM | 32 GB | 64 GB |
| One GPU | 12 GB VRAM | 24 GB VRAM |
| NVMe | 1 TB | 2 TB |
| Windows review workstation | 4 cores / 16 GB RAM | 8 cores / 32 GB RAM |
| Initial use | Controlled single operator, one inference at a time | Headroom for QA/maintenance; no automatic concurrency increase |

Measured retained baseline: GPU0 RTX2080Ti11GB could run the qualified workloads
serially; 117 lease resource receipts, PRISM sampled maximum 5442 MiB (~5.31
GiB), worker-only RSS ~2.43 GiB. These do not prove a 6–8GB GPU minimum or that
all models can reside concurrently. Host/process-tree RAM was not measured.
PRISM whole-job p95 ~81.422 s, maximum109.375 s in retained passed jobs; this is
not the native execution deadline or promised interactive SLA.

Original240 images total 1,036,118,254 bytes; largest original ~9.32MB, largest
pixel count15,944,033. JSON/base64 wire payload can be larger than source bytes.
Do not recompress original images to avoid an ingress bug.

CPU saturation/core requirement, host RAM peak, IOPS, LAN RTT/throughput,
concurrency, simultaneous residency, onsite offline startup and Lightning AI T4
comparison are NOT_MEASURED. Hardware draft is not purchasing/clinical approval.
Keep provider dependency inventories isolated; do not install a generic latest
model extra over the qualified USPEC/PRISM environments.

## 17. Concrete failures repaired and lessons to retain

| Failure | Small repair / evidence boundary |
| --- | --- |
| Wrong DB migration configuration key | Corrected to `DR_SUPPORT_DATABASE_MIGRATION_MODE=verify` before successful credentials/context apply |
| Runtime PG principal preflight raised42501 on guard object casts | Catalog OID lookup without granting runtime guard access |
| Timestamp `.12` vs `.120000` / timezone spelling falsely changed context | Comparison-only aware timestamp normalization; raw catalog unchanged |
| Authority/manager/store inversion | Authority outer ordering; context reader nonblocking manager/store busy refusal |
| Logging failure after verified release could leave subsequent dispatch available | Poison future authorization while preserving actual completed save/readback |
| Owner-file creation race / redirect-parent side effect | `O_EXCL` + real OS lock; redirect validation before directory creation |
| Real21 checkpoint path keys rejected as RPC identifiers | Core2c1c390 / remote6c0de66 bounded opaque-key fix; do not change weights/hashes |
| Native admission log failure erased independent readback outcome |248a9ee separates response observed/retained, PG proof and accounting uncertainty |
| Historical tests mutated real ACL by default | Explicit opt-in; default skip, no silent permission modification |
| Earlier fixture/core method/hash/ingress/cleanup defects | Retained in operational memory and original repair evidence; do not repeat broad audit or replay closed batch |

An early inline Python credential setup attempt failed with a Python `\U`
SyntaxError before execution; corrected quoting/raw strings preceded the
successful apply. It was not an access denial or a reason to change ACLs again.

## 18. Blockers and work that can proceed after an explicit resume

### Own engineering gaps — fix at source, do not ask for approval per file

1. Review/integrate clean pushed candidate8329c31 after current-main verification.
2. Obtain final independent review of remote6c0de66's checkpoint-key delta.
3. Finish WIP factory/context/preview/provider binding and focused regressions.
4. Complete existing lifecycle/native consumer/watchdog/readback assembly.
5. Materialize and verify durable owner-approved continuation/operations before
   any GPU activation; retain all historical anchors and clocks.
6. Produce tested start/status/stop that stays alive for the user's bounded demo.
7. Fresh main-browser real USPEC/RETFound/PRISM -> SQL -> reopen/export proof.
8. Complete backup/restore, packages, screenshots/gallery/HTML and actual manuals.

Do not disable authentication, privacy checks or clinical/source gates to make
technical QA pass. A self-authored app/script gate can be repaired at its cause;
a real access denial must stop that action.

### Actual target / owner / IT dependencies

- Identify hospital QA_LOCAL machine, storage, OS/driver, offline assets and
  operational owner. Without it, onsite Local acceptance remains NOT_RUN.
- Confirm hospital-approved private route and data-owner authorization for
  QA_SERVER; compute approval does not authorize PHI transfer/network changes.
- Any new service account, ACL outside the exact approved directory, firewall,
  new credentials, persistent access/autostart or destructive change needs exact
  approval. Consolidate necessary IT questions with change/impact, not per-file
  engineering questions.
- Human adjudication/physician UAT is needed for clinical label/mask evaluation;
  do not generate clinical gold automatically while waiting.

The Windows credential blocker was resolved within its exact approved scope.
Do not tell the next owner the entire server needs to be set up again.

### Policy-rejected historical write — preserve refusal

Earlier automatic approval review rejected a composite command before process
creation, shaped as `rtk proxy python -c @' ... '@`, which would have:

- created `CLI_DR_TRAIN_READINESS_SUMMARY_20261023.json`;
- appended public Pepo handoff section7;
- created `CLI_PEPO_HANDOFF_RUNTIME_ADDENDUM_20261023.md`;
- appended `CLI_DEMO_OPERATIONAL_LOG_20261022.md`.

Only available reason: **blocked by policy**. No output from that rejected
action was created. Keep those exact actions stopped; no tool/path substitution
to evade the refusal. This new repository `HANDOFF.md` was subsequently directly
requested by the owner. It does not retry or retrospectively mark those old
actions successful. Failure to write an operational log is not model failure.
Do not transmit this handoff through email/chat to others without authorization.

## 19. Resume sequence and commands

These are resumption instructions, **not commands to run during the pause**.

### First checkpoint, before any implementation write

```powershell
Set-Location C:\Users\User\Desktop\myProject\dr-support-screening-poc
rtk proxy git rev-parse --show-toplevel
rtk proxy git branch --show-current
rtk proxy git rev-parse HEAD
rtk proxy git status --short --branch
rtk proxy git diff --stat
rtk proxy git worktree list
rtk proxy git ls-remote origin refs/heads/main
```

Then inspect the preserved WIP, without restoring or stashing it:

```powershell
Set-Location C:\Users\User\Documents\Codex\2026-10-21\task\m1-app-workspace-runtime-worktree
rtk proxy git branch --show-current
rtk proxy git rev-parse HEAD
rtk proxy git status --short --branch
rtk proxy git diff -- dr_support/api/_factory.py
```

The main documentation successor created by this handoff may be ahead of the
candidate bases. Integrate actual current main into bounded work branches when
appropriate; resolve/test there. Do not patch implementation directly on main.

### Suggested bounded order after owner resume

1. Confirm single-writer ownership and current repository/worktree state.
2. Review combined8329c31 exact content and latest-main compatibility; integrate
   only if all applicable review/acceptance gates are satisfied. Run main
   regressions and push synchronization. This alone does not activate AI.
3. Independently approve the corrected remote provider, then finish the retained
   factory patch/context allowlist/preview registration and tests on its branch.
4. Complete the real existing service/native admission/readback assembly with
   bounded watchdog/concurrency/queue and source/role/identity tests.
5. Freeze actual model/weight/preprocessing/parameter identities and compose the
   exact24 operation scope/approval/anchors. Verify ledger before spending.
6. Activate only the named QA_SERVER window after all preflights. Inspect actual
   remote listener and establish verified loopback tunnel. Load actual3 models;
   health/metadata/load remain separately reported.
7. Main browser acceptance, one admitted intent per request, no auto retry:
   USPEC UWF, RETFound CFP, protected-preview PRISM; retain phase timing/errors,
   request/result hashes, model pins, device, fresh PG readback, reopen/export.
8. Keep the owned API alive for the promised bounded user demo; status reports
   queue/in-flight/deadline and stop uses proven ownership/terminal rules.
9. Retained-result mask comparison/human review and step screenshots/gallery/HTML.
10. Complete target-specific package/manual/cold-start/restart/recovery acceptance.
    Do not activate QA_LOCAL until its real target exists and is approved.
11. Final code review, full applicable branch/main validation, commit/push/merge
    lifecycle and only task-owned worktree cleanup after they are no longer needed.

### Validation entrypoints, not a request to rerun them now

From the selected qualified worktree, use the existing canonical Python rather
than installing a new global environment:

```powershell
$m1Python = 'C:\Users\User\Desktop\myProject\dr-support-screening-poc\.venv\Scripts\python.exe'
rtk proxy $m1Python -m pytest -q
rtk proxy $m1Python -m ruff check dr_support tests
```

Choose focused tests first for actual changed files; run required full validation
at the branch/main handoff gates. Do not broaden/repeat tests after a passing
unchanged candidate without a concrete reason. Do not install dependencies or
enable permission-mutation tests just to reproduce historical counts.

If frontend changes, follow AGENTS frontend tests/typecheck/build from the correct
worktree, then rebuild `frontend/dist` on main after merge and perform main-browser
smoke. No frontend rebuild was required merely to write this document.

### Start/status/stop command readiness

**There is no newly verified complete Hospital M1 start/status/stop command at
this checkpoint.** The URL8000 and historical SSH options above are observations,
not a fully qualified launch recipe. Do not publish the old remaining-four
launcher as the new M1 command. Creating and testing this exact manual lifecycle
is a remaining implementation/acceptance item, not a documentation-only task.

## 20. Evidence pointers and selected integrity anchors

Paths are under the artifact base unless stated otherwise. Verify actual bytes
before relying on an anchor after another session; do not regenerate evidence to
match a remembered hash.

| Evidence | SHA256 / identity |
| --- | --- |
| Original ledger, 1423 rows | `ebc4f23ac5b9d89f136ada7a36b08350ddacf186e338a50c0ea5ba6f5ba14d98` |
| Original session budget | `bd99320debefd1a965e1bbc750b37804b01e833de6e0223508c4122f584588b9` |
| Second175 session budget | `26b921892bb16758d05b23760b435ffbe105f17d5f8e7cb0f9d42ec2de5f8f92` |
| B03 manifest | `3f7413e1b88d20482767db732a0afe8e97b6b85b2d02ff88539cd52dba28fa1f` |
| EXPECTED_BATCH_MODELS raw file | `ac399bfb9d4b5a3a397d18677efe37b30701a35bd1af71657d676aa7ded6ba1a` |
| Original jobs | `e8a1800a7e1545495ec4f5466f5e5d61a00dc33103d29d074808d0f563157dab` |
| Preload REQUESTS anchor-only | `3cc0930701e2466a1f67640f362a19d80901244e935cd0b225d3fe187110da7b` |
| Preload COMPLETE cleanup receipt | `9847e4da6c7d5c4fd0703c0141ccaad7c40feda90dab85b0d5ae94fc5e9d5a06` |
| Actual context receipt | `2d42b254dbb210bc4c81cbe9687af86a50b4b27281d92bf237f0c3a9c5d3df71` |
| Context helper source | `4165dc35d6577673a7bcef30a9eb40a1216dd6006d2fad9ad5cb242b21fcb401` |
| Context synthetic source | `141d5d2e0810bb2b877cd6f44ee62cb1c93bbbb97267cb0705f7f0f64d6bb021` |
| Context raw case | `307006d8f229d6e85d8b8a7858cb7c998c2dab348f3cbb3f85755e2e5ac4495b` |
| Context raw catalog | `a9180a960f75f12ae7b226298b6eeb0745322bbb7d8213271dfe55bc8289ca99` |
| Complete context | `c25c5566d80702a32600fb326450b436b4549e76fef45c9036df668f47cc7ed2` |
| Entry guard SQL | `6d300927351fe9987f4de50b1782408f8d62c471bcfd3d2b2f6b63545b3e14e0` |
| Role SQL | `da6747ab75354f3ac6e1798d26f1c60facb89dbaa93c71d4dbd34cc55e8d6086` |
| Recorded DB-fence pytest output | `40b77d63511837a494b2a6f1dba3c3773e596aa137c75207903b7dcbcd6acb44` |
| Earlier recovery QUALIFICATION | `a930ea2c34ea3ad2cd7d29f6d0689ec91f1487a9125756d54634c4debf1dec3c` |

Additional retained evidence locations:

```text
demo-evidence-session04-20261023/FINAL_STATUS.json
demo-evidence-session04-20261023/PER_JOB_EVIDENCE.json
demo-evidence-session04-20261023/demo.html
demo-batch-evidence-20261022-b03/failures/
m1-context-qualification-20261023-01/CONTEXT_QUALIFICATION.json
hospital-m1-recovery-qualification-20261023-01/
hospital-qa-spec-draft-20261023/MEASURED_BASELINE.json
CLI_DEMO_DELIVERY_20261023.json
CLI_DEMO_OPERATIONAL_LOG_20261022.md  (existing record; rejected append remains stopped)
M1_ACL_READONLY_FINDINGS_20261023.md
```

Do not blanket-copy these runtime artifacts, images, weights, databases or private
configuration into Git. Hashes and sanitized documentary pointers are sufficient.

## 21. Final checkpoint labels and transfer conditions

| Label | Meaning at this handoff |
| --- | --- |
| DONE / PASS | Historical closed batch preserved; actual new DB-role password auth; actual app/PG/context qualification; reviewed component source controls; latest combined backend candidate tests |
| PAUSED | Owner stopped further implementation/operations; agents interrupted/completed; no new inference/window/test launched for the handoff |
| NOT_IN_MAIN | Combined8329c31, remote6c0de66, completed executor/pin/helper candidate changes as identified above |
| INCOMPLETE | WIP factory binding; actual lifecycle/native consumer assembly; final dual-profile deployment/manual delivery |
| BLOCKED action | Historical policy-rejected composite HANDOFF/runtime/log writes; earlier recovery export409; guard-aware backup qualification refusal |
| DEPENDS_ON_TARGET | Actual hospital QA_LOCAL hardware/network/storage/offline inventory and onsite acceptance |
| NOT_RUN | Fresh all-three-model interactive main E2E, new M1 GPU window, complete hospital acceptance, final M1 screenshot/HTML package, clinical validation |

The next engineer must not label the whole project BLOCKED merely because one
viewer/log/IT step is blocked. After explicit resume, continue independent
authorized source work while preserving blocked actions and evidence limits.

The original commit/push/integration requirement remains part of the eventual
engineering definition of done. This documentation-only delivery does not merge
the unfinished candidates or complete M1. Do not claim `main` is wholly clean
while the preserved owner untracked files remain; report tracked-source state
and owner artifacts separately.

Smallest next engineering action after the owner resumes: inspect the preserved
factory diff and candidate/main relationship, then close the reviewed candidate
integration and remaining remote-provider review before connecting live runtime.
Do not begin by starting a batch or spending GPU requests.

End state for this handoff: **READY_FOR_REVIEW; ENGINEERING PAUSED; FINAL M1 NOT DONE.**

## 22. Read-only re-verification addendum, 23 October 2026 10:53 UTC

Owner-requested documentation update by Claude Code. Engineering remains
**PAUSED**. This addendum only re-reads Git state, file hashes and local listener
ownership. No tests, builds, migrations, inference, SSH, remote probes, HTTP
requests or database connections were made. Nothing was committed, staged,
deleted or cleaned. Sections 1–21 are kept unchanged as the 10:10 UTC record.

### Git and documents

| Check | Observed |
| --- | --- |
| Main HEAD / `origin/main` (actual `ls-remote`) | `49ad62fdef2ddc133b1e9f14f06aa24a2d2199af` / same SHA |
| Tracked/index changes on main | None |
| `HANDOFF.md` SHA-256 before this addendum | `7214155e8b7267fe16925f737685cec8c62ae4e3baa7a7d876cdf8da5e66ca8f`, matches the GOAL 1.0 anchor |
| Untracked owner paths listed in section 4 | Still present, preserved |
| New untracked documents since section 4 | `GOAL.md` (owner-requested GOAL, Thai); `CLAUDE.md` (Claude Code guidance: imports `AGENTS.md` and names `HANDOFF.md`/`GOAL.md` as required reading) |

### Candidate branches (section 4 table)

Every branch head is unchanged from the pause checkpoint:
`8329c31`, `6c0de66`, `1dfdeba`, `1408977`, `2c1c390`, `8dc56ee`, `5c9288c`.
`git merge-base --is-ancestor` confirms none of them is in main.
`feat/m1-native-accounting` (`8329c31`) and `feat/m1-workspace-remote`
(`6c0de66`) exist on origin at the same SHAs. `feat/m1-app-workspace-runtime`
still has no remote branch.

WIP worktree `m1-app-workspace-runtime-worktree`: `git status` was readable from
this session; the dubious-ownership refusal recorded in GOAL 1.0 did not occur.
It is still at `1dfdeba` with only `dr_support/api/_factory.py` modified,
unstaged, 92 insertions / 3 deletions. The diff content was not read or changed.

Retained worktrees in the "Retained earlier worktrees" table: all their heads
are ancestors of main.

### Worktrees not listed in section 4

`git worktree list` also shows these task-artifact worktrees. Their unique
commits are patch-equivalent to commits already in main (`git cherry` reports
`-` for each). That means the source is integrated, not that the branches are
safe to delete. Confirm ownership before any eventual cleanup.

| Worktree | Branch / head |
| --- | --- |
| `m1-deployment-profile-worktree` | `fix/m1-generic-mask-regression`, `974f3e9` |
| `m1-docker-start-worktree` | `fix/m1-docker-engine-start`, `23d7827` |
| `m1-postgres-recovery-worktree` | `feat/m1-postgres-recovery`, `57d7fa2` |
| `m1-recovery-source-binding-worktree` | `fix/m1-recovery-source-binding`, `5569096` |
| `interactive-model-demo-worktree` | `feat/m1-accounting-recovery-integration`, `046abe2` (ancestor of main) |
| `model-api-worktree` | `feat/qa-model-api-audit`, `001c12e` (ancestor of main) |

Other worktrees (`task-3/integration-review`, the separate clinician UI checkout and
Orca checkouts) remain outside this handoff's cleanup scope.

### Local listeners

| Port | Observed |
| --- | --- |
| `127.0.0.1:8000` | LISTEN, PID 38564 (same as section 12) |
| `127.0.0.1:54805` | LISTEN, PID 9520 (same as section 12) |
| `47860`, `17860` | No listener |

Listener presence only; no request was sent. Whether PID 38564 serves current
main source remains unverified.

### Status effect

No label in section 21 changes. The smallest next engineering action after an
explicit owner resume is still the one stated at the end of section 21.

## 23. Owner resume and progress checkpoint, 23 October 2026

### Owner decisions given in chat (the only authority for this section)

- Resume engineering to close the GOAL.md PARTIAL items with real consented
  images from `C:\Users\User\Desktop\demoImages`; ask the owner before needing
  any other information.
- **Claude Code is the sole application-code writer for this round.** VS Code
  Codex must not write concurrently to the same repository/worktrees.
- GPU window `HOSPITAL_M1_QA_SERVER_20261023` on dr-train GPU0 may be opened and
  demoImages sent through the owned SSH tunnel, at most 9 of the 24 remaining
  requests, no automatic retry, **only after MS-01–MS-04 pass**, with a report to
  the owner before opening.
- Labels: TEST_ONLY reviewer for now; physician-label items stay PARTIAL.
- Claude may merge to main and push when the AGENTS.md gate passes; stop and ask
  for frozen-contract or schema conflicts.
- Real images are copied byte-identically into the approved private directory
  (`M1PrivateConfig\hospital-roots\UWF` and `\CFP`) because the Desktop folders
  fail the private-root ACL check; ACLs are never changed.
- WorkspaceAuthority directory: `M1PrivateConfig\workspace-authority`.

### Done (branch `feat/m1-hospital-integration`, pushed; NOT in main)

Worktree: `C:\Users\User\Documents\Codex\2026-10-21\task\m1-hospital-integration-worktree`.

| Commit | Content | Evidence |
| --- | --- | --- |
| `83b3cd8` | Merge of combined candidate `8329c31` (clean, no conflict resolution) | Full backend 1771 passed / 67 skipped, Ruff clean |
| `949cc5e` | Merge of remote PRISM provider `6c0de66` | Independent review APPROVE (68/68 at 6c0de66); focused 274 passed / 1 skipped |
| `2d69e0d` | Preserved WIP `_factory.py` committed as explicitly unqualified WIP on `feat/m1-app-workspace-runtime` (local only) | Content unchanged from section 5 |
| `a648b3d` | MS-02 composition: `owned_connection` (name-only change; URL/token swap refused before probe/state change), preview bound to authority, plan registration before routes, one-use `reader.bind`, USPEC/RETFound remote grading kept beside owned PRISM; context reader accepts exact `WorkspaceRemotePRISM` with the same opaque checkpoint-name bound | Full backend 1851 passed / 67 skipped, Ruff clean |
| `4ddb6a3` | Fixes from independent review (REQUEST_CHANGES on a648b3d): read-only status probe reports `UNVERIFIED`/not reachable instead of live CONNECTED and never enters a writer scope; existing workspace profile required (no implicit insert); one authenticated startup discovery against the owned endpoint/token, refusing unless USPEC UWF and RETFound CFP are ready (no PRISM-only session); constant-time token comparison | Focused 245 passed, Ruff clean; full suite after this commit NOT_RUN |

Real images: 21 files (UWF 11, CFP 10) copied, 0 hash mismatches, both roots
pass `private_hospital_root`. Desktop originals untouched.

### Not done / blocked

- **Merge into main: BLOCKED by the session's automatic permission check**
  ("modify shared resources") when fast-forwarding main. Not worked around. The
  owner must grant that action or merge themselves.
- MS-02 positive composition against actual PostgreSQL: NOT_RUN (only fail-closed
  ordering is unit-tested; no mocked full-store composition exists).
- MS-03 (model host): no host app serves `/v1/predict/*` and `/v1/prism-bound/*`
  on one owned port today. Needed: new `scripts/model-server/m1_session.py`
  (parent: ledger/window/budget/lease, owned child, `M1AdmissionConsumer`,
  watchdog; child: combined global models + `workspace_child_application` behind
  one gateway), child admission middleware, parent ACK/response adapter, and a
  Windows readback adapter. Bounded child lifetime is about 45 minutes inside the
  single 10800 s lease; `supervisor.finish(success=False)` drains the child.
- MS-04: the 24-operation proposal must name each image (`source_sha256`), model,
  pins and parameters; its approval file hash must come from the owner. Upstream
  anchors `demo_requests/activation/complete/ready` are on dr-train (SSH needed).
- MS-07 analysis (no code yet): export 409 after restore is the frozen policy, not
  a restore defect (v2 recovery accepts only WORKSPACE cases, which are always
  `BLOCKED_WORKSPACE_NOT_AUTHORIZED`). Guard-aware recovery needs a separate owner-
  approved recovery contract and owner/admin DB credentials; design notes: backup
  must carry/refuse a non-NULL fence binding, restore applies `EntryFencePlan.render()`
  and grants as owner after `pg_restore`. **Policy conflict for the owner:**
  `services/dataset.py` allows local `HOSPITAL_AUTHORIZED` export when identity
  checks pass, while `source_policy.py` and GOAL §6 say hospital export is not
  authorized.
- MS-05/06/08/09: NOT_RUN.

### Next actions (superseded by the update below)

1. Owner: permit main merge/push (or merge), and decide the export policy conflict.
2. Run full suite on `4ddb6a3`, then actual MS-02 composition against the approved
   test PostgreSQL with no model inference.
3. Implement MS-03 host session code on a new bounded branch; draft the exact
   24-operation proposal for owner approval (MS-04); report before any GPU use.

### Update: merge, owner approvals and accounting anchor (same day)

- Owner granted the main merge. Full suite on `4ddb6a3`: 1855 passed / 67 skipped,
  Ruff clean. **`main` fast-forwarded to `4ddb6a3` and pushed**; main regression
  after merge: 1855 passed / 67 skipped. No frontend change, so no dist rebuild.
- Owner approvals in chat: (1) local export of `HOSPITAL_AUTHORIZED` records is
  allowed under the existing `services/dataset.py` identity checks (no code
  change; physician/TEST_ONLY separation and export-eligibility rules still
  apply); (2) SSH to dr-train with the existing key for read-only inspection and
  launcher installation; (3) the 24-operation list and hashes go to the owner
  before any GPU use.
- Read-only dr-train check: host `dr-train`, user `siripon`; project directory
  is not a git repo; GPU0 (approved UUID) and GPU1 idle; Ollama untouched; no
  owned model listener on 7860–7864/17860. A Codex app-server process is
  connected, but no project file was written after the 23 Oct 05:59 pause.
- **Accounting anchor conflict found and resolved with owner approval:** all
  seven upstream anchors pass the continuation verifier except the retained
  `demo_complete` (`9847e4da…`), which predates `listener_closed`/
  `cleanup_components`. The executed producer (`demo_session.py` `e0721fe1…`)
  only published it after all four cleanups returned. Owner approved accepting
  exactly those pinned bytes. Implemented on branch `feat/m1-model-host-session`
  (worktree `m1-model-host-session-worktree`) in `batch_ledger.py`, its tests
  (63 passed) and `M1_ACCOUNTING_CONTINUATION.md`. **The commit was refused by
  the session's automatic permission check; the change is uncommitted** and
  awaits owner permission.
- Constraint for MS-03/05 planning: the Server window allows exactly one 10800 s
  lease and closing it closes the window; the owned child lives at most about
  45 minutes and a failed request drains it. All nine Server requests, the app
  restart check and readbacks must fit one session, with failure tests last.

## 24. MS-03/MS-04 checkpoint, 23 October 2026 (evening)

Branch `feat/m1-model-host-session` (pushed; NOT in main), worktree
`C:\Users\User\Documents\Codex\2026-10-21\task\m1-model-host-session-worktree`.

| Commit | Content |
| --- | --- |
| `5ec2570` | Owner-approved pinned legacy `demo_complete` anchor (committed after owner granted permission) |
| `eac5d29` | `scripts/model-server/m1_session.py` (bounded QA_SERVER acceptance runner: owned parent with ledger/window/one lease, child serving RETFound/USPEC via new additive `grading` provider set and PRISM via the workspace bound transport on one authenticated loopback port; admission before dispatch; no retry/renewal) and `m1_operations.py` (shared operation facts) |
| `2c37171` | `m1_proposal.py` (24-operation drafting, approval only for an exact owner-approved hash) and `scripts/qa/m1_server_app.py` (TEST_ONLY workspace, owned tunnel + composed app, trusted PostgreSQL readback) |
| `8d809e4` | Fixes from independent review 1 (all preflights before any lease; ledger always closed; uncertain PRISM outcome; replay/owner check before charge; separate readback dir) |
| `d260d6f` | Fixes from independent review 2 (readback bound to this request: PRISM plan hash, global result digest, single entry saved after admission, APPLIED only, physician fields; STATUS identifiers validated; tunnel listener PID ownership; proposal disjointness) **plus owner-accepted Codex handoff** (diagnose, `--allow-remote-token-read` opt-in, tests, `docs/operations/M1_LAUNCHER_FIX_HANDOFF_20261023.md`) |

Validation: full backend on `8d809e4` 1898 passed / 67 skipped; focused
session/launcher 61 passed and Ruff clean on `d260d6f`. A final focused review of
`d260d6f` is running.

**Concurrent writer event:** at about 19:04 local, Codex ("Pepo") edited this
worktree while Claude was sole writer. Claude stopped writing; the owner
confirmed Codex was stopped and directed the changes be kept. They are in
`d260d6f` with explicit attribution.

**Owner approvals (chat):** commit permission; the exact action of reading the
existing host token from `/home/siripon/projects/dr-model-api-qa/config/private/model-api.env`
over SSH into Windows launcher memory only (`serve --allow-remote-token-read`);
copying the six post-fix source images.

**Done on hosts (no GPU, no ledger/window/lease):**
- Six post-fix images copied byte-identically into the private roots (UWF 14,
  CFP 13 files total; 0 hash mismatches).
- Deployment `deployments/m1-session-20261023-s01` on dr-train from `d260d6f`
  (154 files; `git archive` from Windows wrote CRLF line endings — the reviewed
  RETFound/USPEC provider-file pins still match exactly).
- CPU-only identity (exit 0, GPU0/GPU1 idle before and after):
  installation `5db459c3…`, RETFound/USPEC pins match the reviewed file
  `ac399bfb…` exactly; PRISM workspace pins match checkpoints/revision with
  workspace `config_sha256` `2d54380b…` (differs from the batch-bound config,
  as expected).
- Upstream anchors uploaded to `m1-upstream-20261023/`; proposal inputs in
  `m1-continuation-20261023/`.
- **Draft proposal `1faa91e792331b426f6a6c2323c159f287b9c288bfa5415a74efb9c8c6e82c45`**
  passed the real `_verify_m1` dry run on dr-train with a temporary unsigned
  approval (deleted; accounting directory not created). It awaits owner approval.

**Superseded the same evening:** the final focused review of `d260d6f` found the
host and readback global-result digests could differ (missing or integer
probabilities). Fixed in `2756751` (digest normalised as the contract persists;
round-trip test through `GlobalResult`; PRISM readback selects the entry of its
plan; netstat listener check locale-independent). Focused 64 passed, Ruff clean.
Redeployed as `deployments/m1-session-20261023-s02` (installation
`93acfb89f254a03b6969993a9b3717af2364b4aa85db013dcd222c9d65d247b2`); CPU identity
exit 0, RETFound/USPEC match the reviewed pins, PRISM workspace config
`2d54380b…`, GPUs idle. **Proposal v2
`5a06f23cd93aaf018ff6ac0e65567004abd798d93e882cba19e210b275da535d`** (files in
`m1-continuation-20261023-v2/` on dr-train and
`m1-continuation-proposal-20261023-v2/` on Windows) passed the real
`_verify_m1` dry run; operations manifest `ccd31223…` is unchanged from v1. The
`s01` deployment and v1 proposal `1faa91e7…` are superseded and must not be
approved or activated.

**Owner approval and preparation (same evening):**
- Owner approved proposal v2 `5a06f23c…535d` in chat; `APPROVAL.json`
  `fc1f32ed61c868592568e60022aa172d0a7ebd596274199a90700f7e15acf901` written only
  for that hash and uploaded read-only to `m1-continuation-20261023-v2/`.
- Branch merged: full suite on `a99cd68` 1925 passed / 67 skipped, Ruff clean;
  **main fast-forwarded to `a99cd68` and pushed** (adds `prepare` command and
  `docs/operations/M1_QA_SERVER_SESSION_RUNBOOK.md`). No frontend change.
- TEST_ONLY workspace `ws_m1_63ed86c7d44f46d59479` created in the approved test
  database (private folders under `M1PrivateConfig\workspaces\`).
- Manual-mode `prepare` app (no model, token or GPU): 27 private-root images
  admitted as `HOSPITAL_AUTHORIZED`; the six Server acceptance images
  confirmed through the Confirm Image endpoint (reviewer `TEST_ONLY_ENGINEERING`,
  patient unlinked, UWF eye LEFT, CFP eye UNKNOWN). UWF `analysis_preparation`
  is `NEEDS_REVIEW` (context only, not an inference gate).
- Note: the CFP acceptance images are IDRiD public-dataset files placed in the
  owner's consented folder; the app records origin from the private root, so
  they are labelled `HOSPITAL_AUTHORIZED` in this TEST_ONLY workspace.
- Pre-GPU checklist: GPU0/GPU1 idle with no compute processes, model ports free,
  accounting and run directories absent.

**Not done:** owner go-ahead for the GPU window; the Server window, lease and any
GPU inference; actual composition against PostgreSQL with the model session;
E2E. (Superseded by section 25.)

## 25. QA_SERVER live session, 23 October 2026 (CLOSED)

Owner instruction (chat): start the QA Server GPU session per the runbook —
window `HOSPITAL_M1_QA_SERVER_20261023`, GPU0 only, at most 9 server requests
plus suitable post-fix, no retry.

**Session:** run `runs/m1-server-20261023-01` on dr-train, deployment `s02`,
lease `m1_server_50ca42000c8048c6`, started 12:35:21 UTC, owner-closed after
1737 s observed (cap 2640). `COMPLETE.json`: `cleanup_confirmed: true`,
`window_stop: CONFIRMED`, `ledger_close: CONFIRMED`, `automatic_retries: 0`,
`supervisor_reason: OWNER_CLOSE`. GPU0 back to 1 MiB; GPU1/Ollama untouched.
**The Server window is closed permanently.** Ledger `global_used` 525 → **531**
of cap 549 (`usage_status: EXACT`).

| Operation | Model / modality | Request | Result |
| --- | --- | --- | --- |
| srv-fresh-uspec | USPEC / UWF | `m1_0001_e54b08e885c8c803` | MODEL_COMPLETE, readback PASS |
| srv-fresh-retfound | RETFound / CFP | `m1_0002_5b21d0e8110b80d5` | MODEL_COMPLETE, readback PASS |
| srv-fresh-prism-uwf | PRISM / UWF | — | NOT SENT (preview gate, below) |
| srv-restart-uspec | USPEC / UWF | `m1_0003_94124b799382bde4` | MODEL_COMPLETE, readback PASS |
| srv-restart-retfound | RETFound / CFP | `m1_0004_263a9d05f49b4e69` | MODEL_COMPLETE, readback PASS |
| srv-restart-prism-cfp | PRISM / CFP | — | NOT SENT (same gate) |
| srv-recovery-uspec | USPEC / UWF | `m1_0005_2d267f49623e1a41` | MODEL_COMPLETE, readback PASS |
| srv-recovery-retfound | RETFound / CFP | `m1_0006_8a423da498c37555` | MODEL_COMPLETE, readback PASS |
| srv-recovery-prism-uwf | PRISM / UWF | — | NOT SENT (same gate) |
| post-fix (9) | — | — | NOT RUN (no PRISM route; failure paths not genuinely exercised) |

All six requests went through the ordinary review UI ("Analyze grading only")
in the TEST_ONLY workspace `ws_m1_63ed86c7d44f46d59479`; each trusted
PostgreSQL readback (`m1_server_app readback`, read-only transaction) matched
the host-observed result digest before the next admission. Restart: `serve`
stopped/started, both fresh results still shown after two restarts, new
invocations on the restart images. Recovery: only the tunnel (ssh child) was
dropped between requests; the case/image and "Continue to clinician review"
stayed usable, host showed no new request/charge; `serve` restarted, then the
recovery requests ran.

**Live launcher/app defects found and fixed** (branch `fix/m1-token-reader-path`,
merged into main `d7ca474`, pushed; full suite 1926 passed / 67 skipped on the
branch and on main, Ruff clean, root Node smoke PASS on main; no frontend change):

| Commit | Defect |
| --- | --- |
| `fefdbb0` | Host token reader needs a `pathlib.Path` argument |
| `2df476b` | `/v1/model-connection` 500: cached probe did not summarise the owned PRISM descriptor |
| `42bf5e4` | Discovery summaries dropped `authorized_source_origins`, so the UI disabled Analyze for `HOSPITAL_AUTHORIZED` images (additive optional field on `ModelConnectionModel`, filtered to known origins) |
| `d12a62b` | Client-side transmission opt-in (`MODEL_HOSPITAL_SCOPE`/`MODEL_ALLOW_AUTHORIZED_HOSPITAL`) set only inside `serve` (refused before send; no charge) |
| `093e281` | Readback looked for top-level `source_sha256`/`image_sha256` the case store never writes; now matches `case_id` or an `inference_history` entry with that source (verification itself unchanged) |

Also: the WorkspaceAuthority directory created by an earlier run had an
OWNER RIGHTS ACE and failed the privacy check; the empty folder (created by
this work) was removed and recreated to inherit the parent ACL — no ACL edited.

**STOP item — PRISM protected preview cannot run on workspace-admitted cases.**
`POST /v1/cases/{id}/prism-input-preview` returns 503 "Recorded source
attestation is unavailable" (`services/prism_preview_runtime.py`): the gate
needs a recorded `case.source_sha256`/`case.image_sha256` (and
`case.image_sha256` or `admission.source_metadata.source_sha256`), and forbids
deriving them from loaded bytes. Ordinary workspace admission never records
those projections on the case (only `case16_acquire.py` does), so every M1
workspace case is refused before any model work. Fixing it changes admission
semantics and the PRISM source-attestation contract (protected areas), so it
was not patched. Proposed smallest amendment for owner decision: admission
records the admission-time hash as `source_sha256`/`image_sha256` on new cases
(additive JSON default), plus an owner-approved one-time projection for
existing workspace cases from the recorded admission hash (never re-hashed
bytes). AC-06 cannot pass on either profile until this is decided.

**Other findings:** while the tunnel was down the Analysis panel still showed
the cached "AI READY" (no fake result, Analyze not clicked to avoid an
uncertain admission) — AC-11 wording/status freshness gap. STATUS `outcome.persistence`
stays `PENDING` while `readback.persistence` is `PASS` (the parent records
readback separately; COMPLETE confirms PASS).

**Remaining capacity:** 18 of cap 549 (QA_LOCAL 6, post-fix 9, plus 3 unsent
Server PRISM operations that have no open window). Any further Server work
needs a new owner-approved window.

**Cleanup state:** fix worktree
`C:\Users\User\Documents\Codex\2026-10-21\task\m1-model-host-session-worktree`
(branch `fix/m1-token-reader-path`, merged and pushed) is retained until the
owner agrees to remove it and the other merged worktrees/branches.

## 26. Recorded source identity amendment, 24 October 2026 (DONE for TEST_ONLY)

Resolves the section 25 PRISM STOP item at the preview-attestation step. Spec:
[M1_RECORDED_SOURCE_IDENTITY_AMENDMENT.md](docs/milestone/m1/M1_RECORDED_SOURCE_IDENTITY_AMENDMENT.md),
owner-approved in chat (Part A and Part B, Part B for `ws_m1_63ed86c7d44f46d59479` only).

- **Code:** branch `fix/m1-recorded-source-identity` (`36e8961`, `a04cc19`,
  `b0c68da`), independent review REQUEST_CHANGES → fixed → APPROVE; merged to
  **main `f4e943d`** and pushed. Full suite 1979 passed / 67 skipped on branch and
  main, Ruff clean, root Node smoke PASS; no frontend change.
- **Part A:** a new case records `source_sha256`/`image_sha256` from its
  AUTOMATIC/MANUAL admission record, write-once; existing cases never filled.
- **Part B run (owner approved plan `fa089a4c317c4ef9d14feb61f402c2320ecd9d16860e54ed79106205dba0ea7c`):**
  database-only backup first (`pg_dump` custom format of
  `dr_support_m1_interactive_test_20261023`, 27,680 bytes, SHA-256
  `2ea14c52…37a5`, TOC verified; receipt `bbb961be…d97a`); apply wrote 27 cases
  (revision +1, one audit event each), readback PASS, receipt
  `1ba7b663…6c04`; a fresh plan shows 27 `ALREADY_RECORDED`. All evidence in
  `M1PrivateConfig\evidence\recorded-source-projection-20261024\` (outside Git).
- **Environment note:** after the overnight restart Windows had reserved TCP
  54774–54873 (blocking PG port 54805). The owner reset WinNAT/WSL/Docker; the
  DR PostgreSQL container was started as-is (normal WAL recovery). Docker also
  auto-starts `sabai-db`/`sabai-web`.
- **Still open:** an actual protected PRISM run (AC-06) needs a new
  owner-approved GPU window; the 2026-10-23 Server window is closed.

## 27. PRISM GPU window preparation, 24 October 2026 (awaiting hash confirmation)

Owner approved the plan
[HOSPITAL_M1_PRISM_GPU_WINDOW_PLAN_20261024.md](docs/planning/HOSPITAL_M1_PRISM_GPU_WINDOW_PLAN_20261024.md)
(max 3 PRISM requests, GPU0, lease ≤ 3600 s, one case first). Spec:
[M1_PRISM_WINDOW_CONTINUATION.md](docs/milestone/m1/M1_PRISM_WINDOW_CONTINUATION.md).

- **Code:** `fix/m1-prism-window` (`92318a9`, `ff711da`), review APPROVE (lows
  fixed); merged to **main `b4cf903`**, pushed; full suite 2007 passed /
  67 skipped, Ruff clean, Node smoke PASS.
- **Host (no GPU):** deployment `deployments/m1-session-20261024-s03` (154 files
  from `b4cf903` + s02's `base/` and `EXPECTED_BATCH_MODELS.json`), installation
  `2d85d2eb…8975`; CPU identity: PRISM and global pins identical to s02.
- **Source fenced (irreversible, by design):** `m1-accounting-20261023` now has
  `HANDOVER.lock`; export `ada7707e…19cb`, global_used 531, 18 unsent operations
  recorded (3 PRISM moved on; Local 6 and post-fix 9 need a future decision).
- **Proposal v3:** `m1-continuation-prism-20261024/PROPOSAL.json`, SHA-256
  `38536f119991bd30de94d513055f3918c13f215da8ebb261a1472e88c78748da`; real
  verifier dry run PASS (531 → cap 534, window
  `HOSPITAL_M1_QA_SERVER_PRISM_20261024`, 3600 GPU s / 7200 wall s, prior
  27802.874 s); accounting directory `m1-accounting-prism-20261024` not created.
- **Local check:** manual-mode app, PRISM preview on CFP `092d05e8…` now passes
  recorded attestation and stops only at "no PRISM provider" (no model contact).
- **Next:** owner confirms the v3 hash → write APPROVAL → run the session per the
  plan (phase 1 CFP `092d05e8…`, then UWF `8568e67e…`, `a48d90b1…`).

## 28. PRISM GPU window run, 24 October 2026 (DONE, window closed)

Owner confirmed proposal v3 `38536f11…48da`; APPROVAL `86529dc8…47fc`. Run
`runs/m1-prism-20261024-01` (deployment s03), window
`HOSPITAL_M1_QA_SERVER_PRISM_20261024`, ~1157 s observed. `COMPLETE.json`:
cleanup/window_stop/ledger_close CONFIRMED, 0 retries, **534/534 used**. GPU0
released; GPU1/Ollama untouched.

| Phase | Operation | Image | Result |
| --- | --- | --- | --- |
| 1 | srv-restart-prism-cfp | CFP `092d05e8…` | PASS_READBACK; 380 raw suggestions; still shown after app restart |
| 2 | srv-fresh-prism-uwf | UWF `8568e67e…` | PASS_READBACK; 21 raw suggestions |
| 2 | srv-recovery-prism-uwf | UWF `a48d90b1…` | PASS_READBACK after tunnel drop (manual review usable, no charge) and app restart; 24 raw suggestions |

All went through the review UI (Preview PRISM input → prepare → acknowledge →
submit) and the one-use plan-bound trusted PostgreSQL readback.

**Live findings:**
- First two submits on the CFP case were refused by the host BEFORE admission
  (ledger 0 rows, no charge): the host's frozen-plan gate requires admission
  quality `GRADABLE`, while the app lets a `NOT_EVALUATED` image prepare a
  preview. Each of the 3 images was given `QUALITY_ACCEPTABLE` by reviewer
  `TEST_ONLY_ENGINEERING` (engineering, not clinical). **Open UI defect:** the
  app should say "image quality confirmation required" before PRISM preparation.
- Fixed and merged (`fix/m1-prism-execute-diagnostics`, main `d5a3102`, full
  suite 2012 passed): the app now logs the refusal class/code (it was hidden by a
  catch-all), and readback accepts `m1-prism-*` run names. Also noted: the host
  child's 409 body uses `code`, the client reads `error`, so it reports the
  generic `REMOTE_REJECTED`.

**Remaining accounting:** 534 used. The 2026-10-23 export still records Local 6
and post-fix 9 unsent; using them needs a new owner decision continuing from
this decision's closure. GPU new-reservation total 14,400 of 21,600 s.

## 29. Clinician UX revision Phase A, 24 October 2026 (DONE, merged)

Owner approved `docs/planning/HOSPITAL_M1_UX_REVISION_PLAN_20261024.md` with the
section 3 defaults, then gave full visual freedom. The owner kept the existing
illustrated style with the "precision" palette, English workflow terms, and no
middle dot or long dash in UI text. Merged to main `e52863d` (branch
`fix/m1-ux-phase-a` removed). Main validation: backend 2016 passed / 67
skipped, frontend 299 passed, typecheck, build, ruff, Node smoke and docs QA
all pass. `frontend/dist` rebuilt on main, and the browser check on real
TEST_ONLY data passed.

Delivered:
- Shell: dark green sidebar through `sidebarScope`, a Red Soil band, the
  "Faculty of Medicine, Khon Kaen University" wordmark, and Clinical review /
  Administration groups.
- Review: technical details hidden. The PRISM quality gate (fixes the section 28
  defect) offers "Image quality acceptable" in place. Host 409 `code` is read.
- Grade: one-click 0-4 / Ungradable buttons, still confirmed explicitly.
  Reviewer name remembered by default.
- Confirm Image: the image, plus optional Usable / Not usable. A failed quality
  save keeps the dialog open to retry.
- Finish: names the unaccepted AI suggestion count, still `REVIEWED_NONE_FOUND`.
- Worklist:
  - quick filter Not started / In progress / Done with counts;
  - Done narrows by the clinician's final grade;
  - Result shows only "AI ready" before a grade is recorded;
  - read-only quick look (image, ROI toggles, record).
- Amendment: `docs/milestone/m1/M1_CLINICIAN_UX_REVISION_AMENDMENT.md`.

Deferred by the owner: drag-to-reorder, refer report, image download (needs
login and roles first). Phase B (TH/EN toggle) is not started. Worklist status
and table terms stay English in both languages.

Follow-up (main `ca5e3bd`, branch `fix/m1-sidebar-hide` removed):
- The university and faculty name is removed from the UI (owner: sensitive).
  The Red Soil band stays.
- The sidebar can be expanded, collapsed or hidden from the top bar. Image
  pages keep their own remembered mode, collapsed by default. While hidden,
  the header shows the workspace name.
- Image pages use a fixed 340px side panel (320px in the editor) and a 1920px
  content cap, so the retinal image is larger.
- Validation: frontend 301 passed, typecheck, build, and an independent review
  with its findings fixed.
- `check_docs.py` on the main checkout flags PDFs in untracked local folders
  (`docs/presentation/dr-screening-demo/archive`, `local-state`). These are
  not part of any commit.

## 30. Local TEST_ONLY acceptance evidence, 24 October 2026

Workspace `windows-demo-test-only` (TEST_ONLY), app on main via
`START_DR_SCREENING`, dr-train not connected. Evidence (outside Git):
`M1PrivateConfig\evidence\m1-local-acceptance-20261024\`. Tool:
`scripts/qa/m1_local_acceptance.py` (main `984a920`; read-only SQL snapshot / compare /
guarded failure-checks; identity keys never hashed).

- **AC-11 fix:** Review re-reads `/v1/models` every 30 s while visible, on
  focus, and after a failed analysis. Only the newest reply is kept (main
  `061193a`). In the app it showed AI UNAVAILABLE with dr-train down.
- **AC-07 PASS (TEST_ONLY):** case `07bc59b8…` (hospital-case-0002).
  - GUI: grade 3 to 2, one HEMORRHAGE box, then Finish.
  - Read-only SQL matched: revision 9 to 13, geometry in original pixels,
    reviewer TEST_ONLY_ENGINEERING, recomputed annotation set hash equal,
    inference history unchanged.
  - The box was drawn by scripted pointer events; the embedded browser drag
    tool does not reach the canvas.
- **AC-08 PASS for app restart:** three app-only restarts (PID stop, then
  `release-start.ps1`), health back in about 13 s, PostgreSQL container
  untouched.
  - Every clinician field and the revision were identical after each restart.
  - The GUI reopened showing the same grade and finding.
  - An edit after reopen (grade back to 3, revision 14) survived the next
    restart.
  - Machine reboot NOT_RUN (owner action).
- **Finding (owner decision, protected admission semantics):** each app start
  rewrites `admission.created_at/updated_at` for authorized-root images without
  a revision bump. Clinician data is unaffected, but the original admission
  time is lost. Not changed.
- **AC-12 PARTIAL:** the case did not change for any of these (before/after
  SQL):
  - stale revision: 409;
  - malformed body: 422;
  - unknown case: 404;
  - analysis while the Model API is unreachable: 503 "AI analysis is not
    available; manual review remains available." in about 5.7 s, no
    inference entry.
  - Gap: the review API has no app-level request body limit.
  - Queue, watchdog and OOM need the model host.
- **AC-10 NOT_RUN here:** the artifact ROI post-filter is DISABLED on every
  case. It needs per-image provider or replay decisions (MS-06). A removed AI
  ROI is final by design (409). Restore is covered only by automated control
  tests.
- **Admission timestamp fix (owner-approved, main `75d41f9`):**
  `preserve_admission_timestamps` in `apply_scan` keeps `created_at` at the
  first admission time and moves `updated_at` only when the admission content
  changes. No other admission field, decision or rule changed.
  - Verified: two restarts on the fixed code gave an identical case payload.
  - Full backend suite: 2027 passed / 67 skipped. Independent review: no
    blockers.
  - Notes from the review:
    - Records written before the fix keep the `created_at` from the last old
      start. The true first time is in the first `AUTOMATIC_ADMISSION`
      history entry.
    - The Worklist "Recently updated" sort now reflects real changes.
  - **Separate older issue (not changed, needs owner OK):** after Confirm
    Image on an automatically admitted image, the next rescan clears
    `reviewed_by`, `reviewed_at` and `review_note` in the admission record.
- **Confirm Image reviewer fix (owner-approved, main `9cde657`):** `apply_scan`
  carries `reviewed_by/reviewed_at/review_note` across rescans for automatic
  admissions. Before, every start cleared them.
  - Side effects: export (`dataset._image_confirmation`) treated confirmed
    automatic images as DRAFT again after each start, and `updated_at` moved
    every start for confirmed cases. Both are now fixed.
  - Full backend suite: 2031 passed / 67 skipped. Independent review: no
    significant findings.
  - Live check: hospital-case-0001 after Confirm Image kept the reviewer and
    timestamps across two restarts.
  - Note: a scripted click went to case-0001's menu instead of case-0016's.
    It re-confirmed the same values (UWF, left eye, patient link, AI results
    and grade 4 unchanged); retinal_modality_method is now MANUAL.
  - Out of scope, API-only: a `LEAVE_UNRESOLVED` admission review also sets
    `reviewed_by`, which export counts as confirmed.

## 31. Owner-approved batch, 25 October 2026

Owner approvals (chat, 2026-10-24):
- AC-09 local-only export rule;
- AC-13 backup plus restore into a new test DB and folder;
- AC-08 reboot later, by the owner;
- MS-03 continuous Model API on GPU0 with an isolated watchdog/OOM test.

Done:
- **AC-09:** one export rule, `source_policy.EXPORT_AUTHORIZATION`. It is used
  by manifest, grouped and snapshot exports and by grading folders.
  - Hospital records go only to a local Workspace output folder. Network
    shares, `\\?\UNC`, mapped network drives and sync folders (OneDrive,
    Dropbox, Google Drive, Shared drives, Box Sync) are refused before anything
    is written.
  - AI and physician data stay in separate fields.
  - Tests include real export paths into a refused folder. The
    hospital-fixture variant skips without the native-permission opt-in.
  - Independent review findings fixed. Main full suite: 2044 passed.
- **AC-12:** the review API caps request bodies at 8 MiB (`api/body_limit.py`),
  returning 413 before any route reads the body.
- **AC-02 (local workstation):** the launcher brings Docker and PostgreSQL up
  by itself (healthy in 47 s); CHECK_SYSTEM passes with an explicit
  MANUAL_MODE.
- **AC-16 (partial):** private config is git-ignored and kept outside the
  repo.
  - **Finding:** the app connects to the project-owned PostgreSQL as the
    container superuser, which fails DT-02 least privilege. Not changed;
    needs owner approval for a runtime role.
- Evidence: `M1PrivateConfig\evidence\m1-local-acceptance-20261024\ac02-ac16-local-workstation.json`.

Blocked / stopped (owner decision needed):
- **AC-13:** the local DB has no entry guard. It holds two TEST_ONLY hospital
  workspaces (`windows-demo-test-only` and `ws_9a51…`, 21 cases each), while
  frozen recovery v3 supports one catalogued hospital workspace.
  - The plan wrote nothing.
  - A plan-only source map exists under `M1PrivateConfig\recovery-authority\`
    (sha `0a9636a1…`, digests null).
  - `.env` writes reader-SID paths with `/` while the roots use `\`; recovery
    compares them as exact text, so the process environment was normalized
    for the plan. `.env` was not edited.
- **DT-06:** TEST_ONLY reviewer labels cannot be told apart from physician
  labels in export. Grading folders also hash the reviewer.
- **MS-03 STOP:** a continuous service conflicts with the frozen accounting
  rules:
  - an exact owner-confirmed decision and proposal hash before any charged
    request;
  - a source_sha256-bound operation list;
  - child ceilings of 2700/2730 s;
  - 7,200 GPU-seconds left, and model preload counts as GPU time;
  - the legacy `start.sh`/systemd unit bypasses the ledger and listens on
    0.0.0.0.
  - Research summary: OOM handling is indirect only; there are no cgroup
    limits; the GPU monitor reads the whole device.
- Offline mask gallery: not rebuilt. The historical measurement stands; a
  refresh needs physician adjudication to be useful.

## 32. Owner-approved follow-ups, 25 October 2026

Owner approved: AC-13 rehearsal schema; DT-06 TEST_ONLY tagging; AC-16 runtime
role; MS-03 as a bounded session with a plan and proposal hash.

- **DT-06 (merged):**
  - `label_class` (TEST_ONLY / CLINICIAN) comes from the workspace marker or
    the current reviewers: grade, annotation set, image confirmation, shapes and
    the latest AI-box decisions.
  - TEST_ONLY rows get `TEST_ONLY_LABEL`, are never training-ready, are left
    out of training label files and counts, and show "Test data (not for
    training)". Grouped export files them under `test_only/`; grading folders
    under `TEST_ONLY`.
  - Versions: export schema v3, snapshot v5, policies bumped. Two review rounds
    fixed.
- **AC-16 (merged, applied):** `scripts/qa/configure_local_runtime_role.py
  --apply` created `dr_support_runtime`.
  - The role has no superuser, CREATEDB, CREATEROLE or BYPASSRLS. It gets
    SELECT/INSERT/UPDATE on workspaces/review_cases, SELECT on
    schema_migrations, and default privileges; DDL is denied.
  - The runtime connection is in git-ignored `local-state/release/postgres-runtime.env`.
  - `release-start` migrates with the owner connection, then runs the app as
    the runtime role in verify mode and strips the owner credential.
  - Verified: launcher message, app healthy, and `pg_stat_activity` shows the
    app as `dr_support_runtime`.
  - First apply attempt failed (role not committed before the login test) and
    rolled back cleanly; fixed.
- **Small fixes:** Datasets shows the plain local-folder export refusal;
  CLAUDE.md now describes the owner-confirmed `M1_DR_GRADE_4_REFERRAL` rule
  correctly; the release-start test stubs the new step.
- **AC-13 (in progress):** schema `dr_recovery_rehearsal`, workspace
  `ws_test_only_recovery_rehearsal`, 21 cases from the approved roots, 2
  TEST_ONLY grades. It was made by a separate app on port 8010, now stopped.
  - The backup plan passed: 1 workspace, 21 images, 11 MB; nothing written.
  - Activating source map: `M1PrivateConfig\recovery-authority\source-map-rehearsal.json`,
    sha `54dff5b99e88a5abee8e92ed52b61a470e90894d0e1d7799128e94b4de23e03c`.
  - Waiting for the owner to confirm it. The restore map follows after the
    backup manifest pin.
- **MS-03:** plan `docs/planning/HOSPITAL_M1_MS03_BOUNDED_SESSION_PLAN_20261025.md`
  is awaiting owner approval.
  - Phase A: synthetic watchdog/OOM, 0 requests, lease up to 900 s.
  - Phase B: bounded session, up to 6 post-fix requests, lease up to 3600 s.
  - No GPU used.

## 33. AC-13 PASS and MS-03 ready for hash confirmation, 25 October 2026

- **AC-13 (PASS, local rehearsal, TEST_ONLY):**
  - Owner confirmed source map `54dff5b9…e03c` and restore map `aa84f370…a143`.
  - Backup `recovery-v3-20261025-002` BACKUP_VERIFIED; bundle verify
    MATCHED_INDEPENDENT_PIN (`76d6776a…ba61`).
  - Restore into `dr_review_restore_test`, schema `dr_recovery_rehearsal`, new
    folders `restore-tests/*-v3-001`: RESTORE_DATA_VERIFIED, 21 cases, 21 images.
  - Isolated acceptance process: ENVIRONMENT_VERIFIED, APP_SELECTION_VERIFIED,
    21 cases reopened, Original bytes match the restored roots 21/21, the 2
    TEST_ONLY grades stay "Test data (not for training)", export refused for the
    identity-only workspace as the runbook requires.
  - Note: with no reader SIDs the reader-binding variable must be unset (an
    empty JSON object denies). The real database was never touched.
  - Receipt `M1PrivateConfig\evidence\m1-local-acceptance-20261024\ac13-restore-reopen-20261025.json`
    (sha `241de2ce…7d25`).
- **MS-03 code (merged, main `f2af986`, pushed; branch removed):**
  - Spec `docs/milestone/m1/M1_SERVICE_SESSION_CONTINUATION.md`.
  - Decision `HOSPITAL_M1_ACCOUNTING_SERVICE_20261025`: base 534, cap 540.
    Watchdog window `HOSPITAL_M1_QA_SERVER_WATCHDOG_20261025` (900 s, 0
    operations) must close before service window
    `HOSPITAL_M1_QA_SERVER_SERVICE_20261025` (3600 s).
  - Six 2026-10-23 post-fix operations: RETFound `pf-retfound-d5e8689c2d3c`
    (CFP `05bf31a0`), USPEC `pf-uspec-4f81b1385489` (UWF `10da3b42`) and
    `pf-uspec-b55fcbf67128` (UWF `157f3532`), PRISM `pf-prism-cca990e31bc5`
    (UWF `00a03b50`), `pf-prism-f62327e97fc9` (CFP `02958b03`),
    `pf-prism-b4ae1fec4374` (CFP `1024a3a1`). The plan said RETFound 2, but the
    register has only one RETFound post-fix operation, so the mix is 2/1/3.
    Images are in `M1PrivateConfig\hospital-roots`.
  - `scripts/model-server/m1_watchdog.py`: synthetic cases oom-contained,
    vram-limit, rss-limit, request-timeout, hard-alarm. Torch fraction 1 GiB,
    supervisor VRAM 2 GiB / RAM 4 GiB / request 10 s, prlimit + nice, OOM score
    1000 on children, 12 GiB RAM headroom, GPU1/Ollama processes must persist.
  - Independent review REQUEST_CHANGES (prior-seconds derivation, watchdog
    charge in later windows, host OOM risk, CUDA context headroom, tests) fixed;
    re-review APPROVE. Full suite 2108 passed / 68 skipped on main; Ruff clean;
    root Node smoke PASS. No frontend change.
- **Host preparation (no GPU, GPU0/GPU1 idle before and after):**
  - Deployment `deployments/m1-session-20261025-s04` (156 files from
    `f2af986` + s03 `base/` and `EXPECTED_BATCH_MODELS.json`), installation
    `b6ebb6f9f8107f207ba0ed112b2b0e337fe8039f64be7a7ab0966e00891723bf`. CPU
    identity: PRISM and global pins identical to s03.
  - PRISM ledger `m1-accounting-prism-20261024` fenced (irreversible, by
    design): export `c10d9790…b0b1`, global_used 534, remaining 0.
  - **Proposal `2ac0b6fa36ecb0931b7a56a851003c8eab09390c303d729487d74edee682666d`**
    in `m1-continuation-service-20261025/` (copy in
    `M1PrivateConfig\m1-continuation-service-20261025\`). Real verifier dry
    run PASS (534 → cap 540, prior 31402.874 s); accounting directory
    `m1-accounting-service-20261025` not created. Watchdog `verify` lists the
    five cases.
- **Next:** owner confirms the proposal hash → write APPROVAL → phase A
  (`m1_watchdog.py start`, run `runs/m1-watchdog-…`) → only if PASS, phase B
  (`m1_session.py start`, run `runs/m1-service-…`, PRISM images need
  `QUALITY_ACCEPTABLE` by `TEST_ONLY_ENGINEERING` first). New GPU reservation
  would reach 18,900 of 21,600 s; requests ≤ 540 of 549.

## 34. MS-03 bounded session run, 25 October 2026 (DONE, both windows closed)

Owner confirmed proposal `2ac0b6fa…666d`; APPROVAL `e0331c7a…b7d3`.

- **Phase A, watchdog** (run `runs/m1-watchdog-20261025-01`, window
  `HOSPITAL_M1_QA_SERVER_WATCHDOG_20261025`, lease `m1_watchdog_9d36859d78b14fef`,
  55 s observed, 0 inference requests):
  - vram-limit (VRAM_LIMIT, forced stop -9), rss-limit (RSS_LIMIT, -15),
    request-timeout (REQUEST_TIMEOUT, -15), hard-alarm (WORKER_EXITED, -14):
    as expected.
  - oom-contained: the child hit torch OOM at exactly 1024 MiB, freed memory and
    exited 0, but the supervisor recorded `UNVERIFIED` /
    `CHILD_OBSERVATION_UNAVAILABLE` (most likely the resource sample raced the
    child's own exit; the adapter detail was not recorded). Status FAIL by the
    pre-declared expectation; fail-closed, not unsafe.
  - Cleanup confirmed, window_stop and ledger_close CONFIRMED, GPU0 idle after,
    GPU1/Ollama processes unchanged, cgroup v2 memory delegated (not used).
  - **Owner accepted phase A as safe in chat** and approved phase B.
  - Follow-up (open): record supervisor/adapter `observation_failure` in the
    watchdog observation, and treat a self-exit race as a terminal observation.
- **Phase B, service session** (run `runs/m1-service-20261025-01`, window
  `HOSPITAL_M1_QA_SERVER_SERVICE_20261025`, 705 s observed, owner close):
  - Before GPU: the six images confirmed in `ws_m1_63ed86c7d44f46d59479` by
    `TEST_ONLY_ENGINEERING` (manual prepare app); PRISM images also
    `QUALITY_ACCEPTABLE` (engineering, not clinical).
  - All through the review UI with trusted PostgreSQL readback after each:
    RETFound `pf-retfound-d5e8689c2d3c`, USPEC `pf-uspec-4f81b1385489`,
    `pf-uspec-b55fcbf67128`, PRISM `pf-prism-f62327e97fc9` (CFP),
    `pf-prism-b4ae1fec4374` (CFP), `pf-prism-cca990e31bc5` (UWF):
    **6/6 PASS_READBACK**.
  - `COMPLETE.json`: cleanup/window_stop/ledger_close CONFIRMED, 0 retries,
    global_used **540/540** (EXACT). GPU0 back to 1 MiB; GPU1/Ollama untouched.
  - Evidence in `M1PrivateConfig\evidence\ms03-watchdog-20261025-01\` and
    `ms03-service-20261025-01\` (COMPLETE sha `78273064…ba57`).
- **Live findings (open, not fixed):**
  - (Fixed in section 35.) The first "Prepare / refresh API input" after a completed PRISM job timed out
    (app HTTP 500 from an httpx ReadTimeout in `prism_remote_bound.py`); an
    immediate retry worked. Control call only, nothing charged. The app should
    show a plain retry message instead of HTTP 500, and the prepare timeout
    should be reviewed.
  - Operator note: run `m1_server_app readback` from PowerShell or with
    `MSYS_NO_PATHCONV=1` in Git Bash, otherwise the remote run path is rewritten
    and refused (`APPROVED_REMOTE_RUN_REQUIRED`).
  - Some UWF images carry burned-in identity text; no screenshot was kept.
- **Accounting now:** requests 540 of 549 (QA_LOCAL 6 and post-fix 3 remain in
  the 2026-10-23 export, unsent); new GPU reservation 18,900 of 21,600 s. Any
  further GPU work needs a new owner decision continuing from the service
  decision's closure (its fence export will anchor both windows).

## 35. PRISM Prepare timeout fix, 25 October 2026 (DONE, merged)

Owner asked for a plain retry message instead of HTTP 500 and a review of the
prepare timeout, without GPU use.

- Cause: `ExplicitHttpChannel` used a 2 s httpx timeout for every route; the
  host's `/v1/prism-bound/prepare` (control call: wire upload plus frozen CPU
  plan, never charged) took longer right after a PRISM job, and the unhandled
  `httpx.ReadTimeout` became HTTP 500.
- Fix (branch `fix/m1-prism-prepare-timeout`, merged main `b96268c`, pushed,
  branch removed):
  - Prepare only: `httpx.Timeout(10, connect=2)`. Execute, status, grant,
    cancel and capabilities keep 2 s. 10 s, not more, because the review
    runtime holds the case store lock during prepare.
  - A transport failure at prepare becomes `PREPARE_UNAVAILABLE` (503): "The
    model server did not answer in time. No model work was started; press
    Prepare again." Other server failures: "PRISM is not available right now.
    No model work was started." Host refusals (409): "could not prepare this
    input". Fixed codes are logged only.
  - The submit-time refresh path is unchanged (still the 502 "cannot be reused"
    refusal).
  - Screen: a prepare failure shows the message alone; submit failures keep the
    "Prepare a new receipt" hint.
- Independent review REQUEST_CHANGES (submit path, lock-holding timeout,
  wording, tests) fixed; re-review APPROVE.
- Validation on main: backend 2115 passed / 68 skipped, Ruff clean, frontend
  305 passed, typecheck clean, `frontend/dist` rebuilt (served by the running
  app), root Node smoke PASS. No GPU, model or network use.
- Known limit (accepted): a client timeout can leave an unused host ticket for
  up to 300 s; it cannot be executed or charged. Not yet tested live against
  the host (needs a future session).
