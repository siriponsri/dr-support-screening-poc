# Validation and evidence matrix

Requirements are in [the spec](REGULAR_SERVICE_SPEC.md); follow [the plan](IMPLEMENTATION_PLAN.md). Unless explicitly marked historical, all rows below are **NOT_RUN for the new implementation**. Synthetic/proposed-contract tests do not constitute product acceptance. Record PASS/FAIL/NOT_RUN/BLOCKED, exact revision/target/data origin, evidence/hash/count/timing, limitation and next actor for every applicable row.

## Historical baseline to preserve

| Evidence | Recorded result | Limit |
|---|---|---|
| Audit overlay full backend |2139 PASS,68 SKIP,4 strict XFAIL,1 setup ERROR | Exit1; not integration PASS; WinError5 atomic journal replacement unexplained |
| Fresh service module diagnostic |27 PASS | Separate run; does not erase full-run error |
| Focused watchdog/checker/AC-11 |50 PASS,4 strict XFAIL | Known defects remain; checker counterexamples falsely PASS |
| Ruff,2 lightweight root Node checks, docs checker | PASS | Not full React/root UI/actual browser validation |
| Actual SSH/current service metadata | PASS for account/path/hash-chain/head/closed budget metadata | No live listener/model readiness/inference proof |
| Midnight audit |2 existing-code characterization+9 proposed-contract simulation PASS | Product daily quota NOT_IMPLEMENTED at snapshot |

See [baseline validation](../owner-audit-20261031/VALIDATION.json), [safe tests](../owner-audit-20261031/SAFE_TESTS.json) and [remote metadata](../owner-audit-20261031/SSH_DR_METADATA.json).

## Offline/source/contract controls

| ID | Requirement | Required proof |
|---|---|---|
| V01 | Branch/ownership/WIP | Fresh root/worktree/branch/HEAD/status/diff; no main implementation write or unexpected-work loss |
| V02 | Existing branch review fixes | Watchdog detail cannot break cleanup; complete checker/path/CSV tests; seeded AC-11 baseline; truthful GOAL/HANDOFF§36 and hash-allowlisted screenshots |
| V03 | Error classification | Disconnect/timeout/HTTP401/403/500/non-JSON/malformed/schema errors; plain wording; uncertain distinct; no secret/raw exception/setting leak; new failures not hidden with xfail |
| V04 | Existing full-suite error | Reproduce/investigate atomic replacement setup error; preserve durability; fresh full validation result, no ACL/reset workaround |
| V05 | Per-user app/store isolation |3–5 app contexts; workspace swap/open/scan/annotation/export ofA never changes or exposesB |
| V06 | Authenticated identity | Spoofed reviewer/user/workspace/principal denied; operator functions scoped; no key sharing; credentials only backend |
| V07 |100-image import | One batch/user; durable manifest accepted once; reconnect/reimport idempotent; duplicate/source-missing semantics preserved |
| V08 | Batch restart | Restart resumes unsent stages from durable state; saved/sent/uncertain stages never redispatch |
| V09 |500-image backlog |5×100 records,1000 expected stages; no100-job GPU fanout; actual source/alias counts reported |
| V10 | Active queue | At most1 running+4 waiting and1 outstanding/user, including concurrent enqueue/cancel/promote races |
| V11 | Fairness | Saturated five-user backlogs, no monopolization/starvation; deterministic order/queue metrics; grader/PRISM dependencies do not bypass fairness |
| V12 | Async boundaries | Submit/status/cancel stable owner-scoped IDs; polling/reconnect never execute; queue wait separate from native30s timeout |
| V13 | Paired capacity | One slot left cannot start a new two-stage image as fully admitted; used/held/available atomic; held slots not falsely called executed |
| V14 | Shared1500 ceiling | Concurrent workers/processes/users/models compete for final slots on one authoritative DB; no per-process1500 duplication |
| V15 | Durable intent | Intent/charge fsynced/committed before dispatch; crash at every boundary leaves known state or fail-closed uncertainty |
| V16 | Idempotency | Duplicate same request concurrent/across restart/day returns original job/charge; altered payload conflicts; new safe explicit attempt counts once |
| V17 | Before/after acceptance | Health/prepare/import/pre-admission rejection0; accepted failed/persist-error/uncertain consumed; no refund after possible send |
| V18 | Thai midnight | UTC16:59:59 ->17:00:00, month/year boundary, old rows retained; daily cap and cumulative history both correct |
| V19 | In-flight rollover | Old intent completes/readbacks next day under original day; new-day request does not erase unknown/fence/poison |
| V20 | Paired hold rollover | Proven-unused hold re-reservation/migration atomic, no used-count movement/borrowing or free second-stage execution |
| V21 | Restart/clock | Daily counts persist; rollback, forward jump, incompatible boot origin, damaged journal/head fail closed; no OS clock change |
| V22 | Service hours |05:59:59/06:00 and21:59/22:00 fake clocks; bounded closing margin; no new outside-hours model load/forward; manual/readback continue |
| V23 | GPU43200 cap | Atomic funded time before load; capped globally; reopen/poll cannot mint/double-charge; no old2700 or57600 allowance |
| V24 | Exclusive residency | Three models loaded on one DR worker share one reservation duration; observed elapsed not charged again; overlaps refused; overrun counted once/quarantined |
| V25 | Idle/healthy retirement | Finite idle unload and limit-based clean recycling only owned child; no [other team]/team signal; new service funding never reopens old lease |
| V26 | Unknown cleanup/crash | Reservation and quarantine remain; native authentication/process birth/owned terminal proof before another child; no TTL/PID-guess unlock |
| V27 | GPU cross-day | Fund split intervals or refuse safely; no double day allowance; requested-model day separate from residency day |
| V28 | Resource pins | RTX UUID exact; V100 excluded; CPU2/VRAM10240MiB/RSS24GiB/project40GiB and child42/2700/request30 limits; no-forward load, isolated environment pins |
| V29 | Readiness | M1 dropped/restored route updates truthful availability without secret reload/return, writer race, model identity swap or inference charge |
| V30 | Frozen admission/context | Missing/unknown modality, denied source, changed source/revision, wrong model/pins, unsupported capability fail before dispatch |
| V31 | PRISM binding | Expiry/queue delay/source/pin/epoch mutation, writer races, grant uncertainty, native-entry proof; no raw-route/implicit-reprepare fallback |
| V32 | Human-state preservation | Established grade/ROI geometry/reviewer/completeness/history unchanged through failure/cancel/restart and later AI; original coordinates/source hashes stable |
| V33 | Persistence outcomes | Model result, retained response, validated history, trusted readback and accounting independent; duplicate/stale results preserve current human projection |
| V34 | Plain UI/accessibility | No clipped grade label/raw readiness enums; responsive widths/keyboard; queue/quota/hours/remaining compute/next eligibility plain and truthful |
| V35 | Secrets/privacy | No token-entry/storage/response/log in owned UI; no PHI/raw local paths/case payload in remote job inventory or package; approved public screenshot hashes |
| V36 | Full branch checks | Required backend/Ruff/root npm/frontend tests/typecheck/build/docs/diff checks; actual DB/platform skips explicitly qualified separately |

## Actual target, main build and candidate evidence

| ID | Requirement | Required proof |
|---|---|---|
| L01 | Fresh target readiness | SSH strict host/account/project, current source/model/environment pins, correct token/principal/DB/route, no port conflict, approved RTX ownership/headroom |
| L02 | Historical lineage/new authority | Replay exact closed source/approval/heads/budgets; old counters/windows unchanged; new daily authority config and approved source evidence recorded |
| L03 | Live no-forward startup | Actual owned load with0 forwards, correct device/resource reservation, plain service status and no other-team/GPU disturbance |
| L04 | CFP grader | Browser -> HTTP job -> RETFound -> validated result/DB history/trusted readback; exact identity and single quota charge |
| L05 | UWF grader | Same with USPEC and preserved UWF provenance/domain/release notices |
| L06 | PRISM CFP | Current protected prepare/ack/entry/terminal/result -> original-coordinate ROI persistence/readback; one charge |
| L07 | PRISM UWF | Same with current experimental UWF evidence; no accuracy/empty-negative claim |
| L08 |3–5 actual contexts | Authenticated independent local app contexts, fair shared queue and correct per-user/project mapping; distinguish fixtures from actual identities |
| L09 | Commissioning budget | Target10 eligible images(5CFP+5UWF)×2=20; ledger counters before/after; all inside1500/day and43200s/day; actual total used reported if necessary extra checks |
| L10 | Review/export | Test-only physician grade/ROI edits/save/read-only SQL proof/reopen/restart/export; no gold/TEST_ONLY contamination or original mutation |
| L11 | Disconnect/restart | Safe between-completed-job tunnel/app restart, durable no-replay/readback and truthful UI; actual sent/uncertain interruptions only under specified safe plan |
| L12 | Main source/build | Accepted merged main, regression tests, frontend rebuilt on main exact commit/digest, served/browser identity, pushed synchronized refs and temporary worktree cleanup |
| L13 | Performance | Measured per-stage/queue/readback/cold load/residency/fairness and completion samples;500-image target not inferred from6-request session or20-call smoke |
| L14 | Hours/budget behavior | Scoped safe check of closing/outside-hours/idle/exhaustion using new service test controls or approved staged limits, without changing real clock or resetting ledgers |
| L15 | Candidate extraction/launch | Clean accepted source, allowlisted software archive, manifest/checksums/build identity, isolated synthetic extraction/launch and start/status/stop instructions |
| L16 | Rollback/operator handoff | Compatible previous app selection preserving data; no old-job replay/old-window restore; exact owned stop/no team impact; permission-sensitive steps named |

Do not consume1500 actual calls merely to demonstrate the cap. Concurrent synthetic/isolated DB tests prove boundary controls; real commissioning verifies the actual path. Larger representative throughput tests may use approved remainder with explicit purpose/source/count and safeguards. Never fabricate500 distinct images from aliases or call repeated warm tests clinical throughput.

Required final result categories:implemented; tested offline; tested actual API/model/DB/browser; not run; blocked with exact action/target/reason/outcome/next actor. Full Hospital M1, QA_LOCAL/hospital hardware, clinician UAT and guarded recovery retain their separate acceptance statuses.
