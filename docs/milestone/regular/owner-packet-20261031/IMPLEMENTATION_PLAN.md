# Claude implementation and integration plan

Follow [the spec](REGULAR_SERVICE_SPEC.md), [authorization](AUTHORIZATION_AND_QUOTAS.md) and [validation](VALIDATION_MATRIX.md). This plan does not report implementation or new live tests as done.

## 1. Re-enter the existing task safely

Use this as a normal continuation with the new scope, not 'resume' on a closed finite session. Read current AGENTS/README/DESIGN/manuals/GOAL/HANDOFF and the complete packet. Check repository root/worktree/branch/HEAD/status/diff, worktree ownership, remote main, existing writers, pending jobs/locks and checkpoint hashes. Claude remains sole application writer in this task. Do not run implementation writes from main, reset/stash/clean owner work, or reconstruct a missing authoritative repo.

Preparation snapshot was main `9c52853db8dd2b879f1151cb1308c860cb78b5af`, no tracked/index diff, pre-existing owner untracked artifacts plus Pepo's requested audit folder. The packet is a new documentation-only delivery under main, initially untracked; promote only these exact requested documents through the bounded branch workflow and preserve unrelated untracked archives. If Git adoption/merge collides with unexpected files, inspect/report that precise action; never delete artifacts to obtain a clean state.

The three existing worktrees below are under `C:/Users/User/Documents/Codex/2026-10-21/task/`:

| Worktree | Branch | Captured HEAD | Captured status |
|---|---|---|---|
| `m1-watchdog-detail-worktree` | `fix/m1-watchdog-error-detail` | `72c6ff641ddd7019475040cc11db190894a76147` | clean;2 unmerged commits |
| `m1-offline-checks-worktree` | `feat/m1-offline-acceptance-checks` | `193503585ce00c66a6bc3028ec4f27c2221b9b1e` | only `scripts/qa/check_export_folder.py` dirty |
| `m1-install-manual-worktree` | `docs/m1-install-candidate-manual` | `7bfce34d65f909c644a5e0fdd8e2e20ed0e787ca` | clean;2 unmerged commits |

Dirty checker SHA256 was `0ae837631ef607f9a552685aa55a715df14bfb76df5c1698ee08c1ea3475e587`. These are snapshot facts, not permission to overwrite later Claude work. The audit used a separate overlay snapshot, not a validated merge commit. At the original remote check the three branches had not been pushed. Refresh actual refs before acting.

## 2. Finish the existing review fixes first

1. Watchdog:keep allowlisted scalar cause only; detail capture must never prevent reap/cleanup/accounting. Existing32 focused controls passed in the audit scope; no new GPU rerun is implied.
2. Export checker:finish WIP and reject Unicode/one-component POSIX absolute paths, decoded embedded values and malformed CSV row widths/extra cells. Use [the reproducible counterexamples](../owner-audit-20261031/CHECKER_PROBES.json). Verify read-only behavior and count/check-name-only output. A checker PASS is not data-owner authorization.
3. AC-11 tests:seed confirmed nonempty grade, human annotation geometry/provenance, review/completeness/revision and history before fault injection. Prove exact preservation and no duplicate send. Address raw ConnectError/ReadError text, timeout setting-name leak, PRISM non-JSON transport/uncertainty classification, failed-vs-unknown wording and M1 cached availability. Remove/convert the corresponding known strict xfails only after their actual fixes; never mark a new failure xfail to hide it.
4. UI:fix grade-choice clipping at supported widths and map dataset readiness reasons to plain labels. Keep grade/readiness semantics, viewer behavior and theme tokens unchanged. Resolve owned-service token entry against the backend-only secret rule.
5. Docs/manuals:enforce exact hash-verified approved public sample membership before screenshot copy/server start; reject changed/symlink/reparse/unapproved inputs. Correct GOAL integration claims, add the existing maintained HANDOFF§36 that GOAL references, and keep watchdog OOM FAIL/UNVERIFIED separate from historical owner safety acceptance. Do not claim a package or main merge that has not happened.
6. Diagnose the audit's full-suite setup error:synthetic `JOURNAL_HEAD.pending -> JOURNAL_HEAD.json` atomic replacement raised Windows WinError5 in `test_an_operation_keeping_its_old_window_is_refused`. Fresh-module diagnostic later passed27. Preserve evidence; establish or bound the cause, fix if appropriate, and rerun final validation. Do not change production durability, chmod/ACL policy or assertions merely to make it disappear.

Audit evidence was2139 passed/68 skipped/4 strict xfailed/1 setup error, exit1; it is not a full PASS. Backend fixture successes, frontend tests, real DB and actual inference remain separate.

## 3. Audit and freeze the new shared orchestration boundary

Map actual local launcher -> app factory -> workspace authority -> protected PRISM/global provider -> private authenticated transport -> model API -> durable result/history/readback -> clinician review/export. Ordinary `dr_support.app.create_app()` does not construct the same owned authority as `m1_server_app.compose()`. The old finite runner and contract-only model package helpers are not the installed regular service.

Keep source/provider contracts and existing PRISM entry protocol. Define additive batch/stage/job interfaces, actor/workspace scope, state transitions, queue/cancel/idempotency, quota holds/intents, daily GPU funding and normal healthy-child retirement before implementation depends on them. Reuse existing shared types where compatible. Record selected concrete routes/schema/state/error mappings and compatibility tests in the spec/change notes; do not let parallel writers invent competing contracts. No parallel agents are required by this packet.

Separately identify security-sensitive provisioning required for real3–5 identities. Prepare concrete least-privilege changes/rollback and request permission only for that action when necessary. Continue code/offline isolation tests meanwhile. A new actor string in a request or reused SSH private key is not the solution.

## 4. Implement durable regular-service controls offline first

Suggested dependency order:

1. New versioned regular-service authority and transactional daily accounting, preserving historical origins/closures/cumulative totals. Daily1500 and GPU43200 are immutable approved configuration, not client inputs. No resetting old clocks/rows or changing old constants.
2. Durable local batch manifest/import idempotency/source/context gates and stage persistence. Keep100-image backlog separate from active model jobs; preserve original hashes and per-user workspace state.
3. Fair1+4 dispatcher and per-user outstanding bound, paired quota holds and per-stage durable intent/idempotency. Include concurrent workers and crash points, not only sequential mocks.
4. Authenticated private job submit/status/cancel and protected actual stage adapters, with queue wait separate from native30s timeouts and no implicit retries/receipt regeneration.
5. Owned GPU lifecycle, idle release and non-overlapping daily residency reservations. Preserve existing per-child resource ceilings,0-forward loading, safe retire/reload and unknown-cleanup quarantine. Prove shared model residency is counted once, not per-model plus elapsed time. Select interval sizes/idle timeout against measured capacity and cleanup margins; never assume a full2700s charge for every42-job child meets the daily workload target.
6. Canonical launcher/status/stop, daily-hours/budget/queue UI and truthful live readiness. Keep manual use outside AI hours and at budget exhaustion. An operator should not SSH or run readback manually for every image.
7. Human-state/result/readback/export recovery and compatible operator packaging.

Use focused tests while iterating, then full branch validation. Test CPU/process/server clock failure paths without real host-clock changes. Use isolated synthetic Postgres scopes with existing opt-ins and explicitly approved principals; permission-mutation fixtures remain opt-in. Reuse qualified isolated environments; don't install over system Python/model environments to fix a test.

## 5. Integrate and validate main using the existing owner workflow

Bound changes into clear `fix/...`/`feat/...`/`docs/...` worktrees. Resolve latest main into feature branches if origin advances; review semantics, not commit recency. Complete focused and required full tests, scope/contracts/privacy acceptance, clean branch, commit+push, integration review and merge according to AGENTS. Existing owner authorization permits the normal workflow; it does not fabricate a PR approval, waive required reviews or allow force push/protection bypass. No implementation patch directly on main.

On authoritative main verify expected merge and tracked/index-clean state, then run backend/Ruff/root Node/docs checks and frontend tests/typecheck/build where applicable. Rebuild `frontend/dist` **on main after the final relevant source/commit**, bind exact build/source identity, restart only the owned app if needed and browser-smoke that main build. Feature-worktree dist does not update main. Report pre-existing owner untracked artifacts separately; don't pretend the whole directory is empty or remove them.

Useful existing commands (use installed locked dependencies; install only what is actually needed in approved isolated project environments):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check dr_support tests
npm.cmd test
.\.venv\Scripts\python.exe scripts\docs\check_docs.py
git diff --check
Set-Location frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

DB/native/platform skips must retain reasons and be covered by the appropriate actual environment before their acceptance is claimed. Do not sum counts across snapshots or relabel skipped/xfail as PASS.

## 6. Prepare the real target and commission within approved daily budgets

Refresh SSH/known-host/project/deployment/ledger/model-pin/DB/principal/port/device/ownership checks. Successful prior SSH and closed journals are not current API readiness. Preserve [other team]/[other team]/team processes and reserved V100. Verify RTX allocation is still available before reserving any new DR time; wait/declare that action blocked if another owner has it.

Verify historical closure/lineage and construct the new regular-service authority without using old windows. Bind the approved config/permissions/model/device/environment identity and record source evidence; do not fabricate a self-signed owner approval. Deploy only tested source and scoped private configuration under existing permissions. New credentials/security/privileged autostart changes remain concrete action-time gates; prepare them for review instead of asking the owner to approve an empty plan.

Commissioning target:10 public/hash-verified or synthetic images,5CFP+5UWF where feasible, distributed across3–5 authenticated app contexts, each grader+PRISM =20 admitted calls. Include simultaneous fairness, app reopen/restart and tunnel reconnect **between completed jobs**, result readback, human edit/save/reopen/export. Use0-call offline faults for dangerous unknown-outcome cases before live tests. A deliberate live interruption requires an explicit safe test plan and preserves consumed/unknown state; never replay to manufacture PASS.

20 is a planning bound, not an additional allowance or a blocker when more specified validation is necessary:all accepted commissioning/rechecks count inside1500 and all GPU reservation inside43200 for that Thai day. Before any larger run record source/principal/model/count purpose and stop conditions. Use approved remaining daily capacity when necessary within the owner scope, not an opaque reset or a hidden extra budget. No new private patient data is approved for commissioning.

Measure representative500-image/day capacity separately. Offline500-record/1000-stage scheduling tests prove controls only.20 real calls establish a smoke, not500-image throughput. Record cold/warm per-stage timings, queues, fairness, residency and incomplete/failed states; expand actual sampling only within the approved daily/resource/data scope. Do not count aliased duplicate images or repeated warm calls as500 distinct cases. If measured capacity falls short, report the actual bottleneck and compatible remedy, not a larger GPU/model or false performance claim.

## 7. Candidate and final report

Follow [operations/rollback](OPERATIONS_AND_ROLLBACK.md). Produce an installation candidate from a clean accepted source, exact source/frontend identity, manifest, checksums, safe templates, dependency/model inventory and known limits. Keep runtime/weights/images/secrets outside software archives. Test extraction and synthetic launch before distribution; label the package installation candidate, not final medical release.

Final report must separate implemented, tested offline, tested actual API/model/DB/browser, not run and blocked. Include exact commits/remote sync, branch cleanup, source/build/package hashes, daily counters before/after, source privacy, per-model evidence,5-user isolation/fairness evidence, operator start/status/stop/restart, and outstanding full-M1/hospital/guarded-recovery limitations. Do not stop at scripts, fixture tests or a feature branch when the actual local-app/API outcome remains authorized and reachable.
