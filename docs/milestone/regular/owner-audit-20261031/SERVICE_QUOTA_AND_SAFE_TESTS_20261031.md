# Regular-service proposal and requested safe checks

Updated 2026-10-31 UTC. Audit/proposal only. No application implementation, quota activation, model work, deployment or access change.

## Current owner intent and approval boundary

The desired outcome is now regular use: open the local application and use the real private Model API, rather than an operator-led finite acceptance session. The owner first mentioned300 requests/day, then explicitly asked Pepo to propose the quota again. Therefore **300/day is a comparison option, not the final setting**. The owner subsequently confirmed that both SSH connectivity and Thai-midnight rollover should be tested safely.

This addendum supersedes AUDIT.md section7 as the primary forward plan, and resolves the old SSH-access blocker for the explicitly tested existing DR identity. The previous12/20-admission plan remains historical functional-test planning, not the operating authorization for the new regular-service goal. No new numeric quota/device/service-period approval is assumed.

## 1. SSH test: actual result

**PASS for SSH authentication and DR metadata access**, not Model API availability or inference.

Repository source: `scripts/qa/m1_server_app.py:44-51,226,471-472`.

| Item | Verified metadata |
|---|---|
| Configured user/host | `siripon@[DR host]` |
| Key path | `C:/Users/User/.ssh/id_ed25519_dr_train`; used by SSH without reading/printing key bytes |
| SSH options | `BatchMode=yes`, `IdentitiesOnly=yes`, `StrictHostKeyChecking=yes`, `ConnectTimeout=10` |
| Effective SSH configuration | user siripon, hostname[DR host], port22, strict verification true; identity paths resolve to the existing DR key |
| Remote identity at01:41:42Z | hostname `dr-train`, user `siripon` |
| Project | `/home/siripon/projects/dr-model-api-qa`, readable/traversable |
| Existing deployment | `deployments/m1-session-20261025-s04`, present |
| Existing service ledger | `m1-accounting-service-20261025`, readable |
| Model listeners7860/7862/7864 | none observed; no HTTP request was sent |

The earlier [other account] path denial was respected. The separate DR identity was tested only after explicit owner clarification authorizing that test. No sudo, account guessing, permission/config/known_hosts change, credential creation or secret-file read occurred. The owner does not need to repair SSH access for this path.

At01:42:19Z, selected current remote metadata was read without modifying files:

- Service proposal base534/cap540/exactly6 post-fix operations, hash `2ac0b6fa36ecb0931b7a56a851003c8eab09390c303d729487d74edee682666d`.
- Current service journal:18 rows,6 ATTEMPT_INTENT,6 final PASS_READBACK, valid sequence/previous/body hashes, SHA256 `8e3cc89cc22821d06363ff94854a54ee5f8088692fa2372869dd58e14c291ae7`.
- JOURNAL_HEAD matches those bytes/sequence/tail; SHA256 `6519aaf402f73f48231fd9e1e5c4a1e380b16e065c1c318f319d0a4918d1b962`, matching the retained Windows copy.
- Service COMPLETE matches the retained Windows copy:540/540 exact, no active admission, no poison,0 retries, cleanup/listener/window/ledger close confirmed, observed705.486s.
- Both current BUDGET bodies validate their hashes, have active=null, quarantined=false, lease_count1 and window_closed=true. Charges:watchdog900s, service3600s.
- A repeat read at the equivalent01:48:23Z confirmed origin `prior_gpu_seconds_preserved=31402.874`. Adding900+3600 gives35902.874 aggregate; subtracting preserved pre-M117002.874 gives18900 M1 reservation seconds. The metadata timestamp is offset-aware (`08:48:23+07:00`), the same instant; no host timezone/clock change was made by the audit.
- No SESSION.lock/HANDOVER.lock/M1_WINDOW_ACTIVATION.lock was observed. In particular the current service ledger has not already been fenced for a new decision; this audit did not fence it.
- The deployed `m1_session.py` and `batch_ledger.py` SHA256 values match the same files on local main. This does not establish identity for every deployed file or model asset.

Evidence:`SSH_DR_METADATA.json`. This check validates current service journal/head and budget metadata; it is not full upstream authorization replay, model-asset verification, current process readiness or a new continuation grant. No environment/token/image/case payload was read.

## 2. Thai-midnight test: what passed and what is missing

**Daily quota is NOT IMPLEMENTED in the current application.** The existing M1 source is a cumulative fixed-operation/fixed-window accounting system. It has no day-bucket policy, daily allowance, rollover service or daily service authority. Existing WorkerSupervisor also limits a child to <=42 jobs and <=2700s, and forbids automatic restart; old M1 budgets allow one lease/no renewal. Do not enable regular service by wrapping these old sessions in an unapproved restart loop.

An isolated audit harness ran11 tests in2.96s, all passing. They are deliberately separated:

| Kind | Tests | Meaning |
|---|---:|---|
| Existing-code characterization using captured production accounting source + synthetic repository fixtures | 2 | Old cumulative behavior was measured across Thai midnight and persisted reopen. This is not a daily-quota PASS. |
| Proposed-contract simulation using a temporary independent SQLite ledger and mock UTC timestamps | 9 | Expected rollover/idempotency/transaction rules are internally demonstrated. This is not product integration or PostgreSQL/multiprocess qualification. |

Existing-source result: a synthetic M1 ledger admitted one operation before midnight and one after. `global_used` changed525 ->526 ->527, cap remained549, charged worker lifetime remained10800; reopen retained527. An admission sent before midnight and finished after remained one cumulative charge. No old row was reset or rewritten as a new day.

Simulation cases:

1. `2026-10-31T16:59:59Z` -> Bangkok2026-10-31 23:59:59; `17:00:00Z` -> Bangkok2026-11-01 00:00:00. Old day full, new day admits, both days' rows retained.
2. The same rule at year boundary:2026-12-31 ->2027-01-01 in Bangkok.
3. In-flight completion after midnight remains charged to its original admission day; restart retains that assignment; a duplicate key retrieves the old receipt without a second charge.
4. Eight concurrent candidates via separate SQLite connections contest one remaining slot:one admitted,seven cap rejections.
5. Concurrent identical idempotency key:one admission,one existing receipt.
6. Different model/user-labelled requests share one cap; pre-accept denial creates no charge.
7. Sent/uncertain remains consumed; an explicit new attempt has a new charge; same key/different request digest conflicts.
8. UTC rollback causes durable quarantine, including across reopen; no extra allowance appears.
9. Corrupt event journal fails closed.

No OS clock changed, no real ledger/day file was reset, no live window was opened and no model/network/GPU call was made by the harness. Small synthetic caps1/2 are fixture values, not user quota settings. The simulation is outside `dr_support` and is never imported by the app. It does not claim complete journal/admission tamper protection or prove the future distributed service.

Workspace reproduction sources are `daily_quota_contract_simulation.py` and `test_daily_quota_audit.py` beside the captured `snapshot/`. Raw receipt:`midnight-tests.xml`; sanitized summary:`SAFE_TESTS.json`.

## 3. Recommended quota for owner consideration

Recommend an initial **7-day engineering pilot,100 admitted Model API invocations/day,7200 GPU reservation seconds/day**. Compare300/day as a larger option requiring its own GPU budget. These are proposed limits, not accepted performance or configuration.

| Proposed tier | Daily top-level model admissions | GPU reservation/day | Finite7-day maximum | Rationale/limit |
|---|---:|---:|---|---|
| Recommended initial pilot | 100 | 7200s (2h) | 700 admissions +50400 GPU s | Upper native-request deadline30s yields3000s request time; remaining4200s is engineering allowance for upload, loading and idle, not measured throughput. |
| Larger comparison option | 300 | 21600s (6h) | 2100 admissions +151200 GPU s | 300*30s =9000s request-time bound alone. Extra12600s covers upload/loading/idle uncertainty. Not evidence that300 successes/day will fit. |

The100/day recommendation is a staged starting allowance, not a measured user-volume need. A CFP/UWF image using its appropriate grader plus PRISM commonly requires2 top-level calls, so100 calls corresponds arithmetically to at most50 such two-call image analyses before tests/rechecks. It is not100 images, and clinical review workload has not been measured.

Measured evidence, separate from those engineering allowances:

- Prior service:6 completed requests took705.486s observed including the session's non-inference work; total reservation3600s. No per-request latency distribution is present in that COMPLETE summary.
- READY receipt:RETFound load16.154s, USPEC load11.812s; forward attempts during load0. PRISM is marked LOADED, but its load duration is not in that receipt. Do not invent a combined cold-start number.
- Existing source comment records historical native PRISM p50=11.9s/max=19.0s. The actual runtime still enforces PRISM job24s and overall native-request30s. These are historical measurements and configured deadlines, not new service benchmarks.
- Upload deadline15s exists separately and consumes resident time if the model is already loaded. One accepted admission may invoke multiple PRISM internal forwards;100/300 are top-level admitted invocations, not native-forward counts.

These GPU budgets count full reserved owned-worker lifetimes, including load and idle, not just busy kernels. Availability of the CPU control service for24h does not authorize keeping models loaded on GPU for24h (86400s/day). The first of daily request cap, funded GPU lifetime, authority expiry or safety failure stops AI admission; manual review remains available.

Start with on-demand verified loads and bounded owned workers, keeping existing request30s / child<=2700s / max42 jobs / VRAM<=10240MiB / RSS<=24GiB / project<=40GiB / model CPU threads2 ceilings unless a separately reviewed amendment changes them. Multiple safely owned workers over a day would be a new regular-service authority, not renewal of any old window. Exact idle timeout/worker lease sizing must be qualified against cold start and observed review cadence; no guarantee of100 successful requests follows from a7200s budget, especially with sparse sessions and conservative no-refund reservations.

No free hidden startup smoke/forward: proposed commissioning verification is at most20 admissions **inside** that day's quota, leaving at most80 ordinary admissions on a100-call day. Later explicit diagnostic verification allowance at most4/day is also inside the cap and used only on an approved engineering verification surface/public or synthetic inputs, not arbitrary automatic patient calls. Loading/readiness with0 forwards consumes GPU lifetime but0 model admissions. A future real watchdog rerun can be separately reserved900s/0 admissions inside an approved day's compute cap; no such rerun was performed now.

Default proposed dispatch policy:global concurrency1, no waiting model queue, bounded busy response, no automatic inference retries. Optionally add an engineering burst cap6 admitted invocations/minute; this is a proposed protective value, not measured clinical demand. Health/discovery/status do not consume model quota and must never trigger model loading or forwarding. Request budget is service-global across users/workspaces/models and includes accepted tests and any separately authorized explicit new attempt.

GPU device approval remains pending. Historical DR uses RTX2080Ti UUID `GPU-044a8b11-4729-458b-a07b-297e45439419`; no new DR allocation was activated. V100 UUID `GPU-277ccc57-c3e5-0731-cd49-f4f8695f7089` belongs to the separate [other team] allocation and is excluded. Do not treat a free GPU as permission.

## 4. Proposed daily-service authority requirements, not an implementation

1. One new versioned authority derives from the verified closed historical lineage. Preserve old cumulative540 and closed windows, old9 scoped request slots and old2700 unreserved GPU allowance. New recurring allowance is an independent dated scope; do not zero/replace old rows, increase an old decision constant or reuse an accounting directory to create daily allowance.
2. Propose `Asia/Bangkok` local calendar days,00:00 inclusive to next00:00 exclusive; store UTC event timestamps plus timezone/day. The owner has authorized testing this behavior; final operational policy still needs confirmation. No host clock or OS timezone change is required.
3. Atomically reserve/consume one global daily admission before any new model dispatch. Transaction must cover remaining capacity, request digest/idempotency, authority scope and durable intent. A per-process counter/Python lock is insufficient across workers/restarts. Preserve source/model/revision/admission/PRISM evidence checks.
4. Count at admission, even if the later model result fails, persistence fails, transport is lost or the outcome is unknown. Pre-admission rejection and control-plane requests consume0. Same operation/idempotency key with identical immutable request returns its existing state without redispatch/charge; changed payload conflicts. A new explicit attempt consumes another slot only when safe/newly admitted; uncertain jobs remain blocked until authenticated reconciliation, including across midnight.
5. An in-flight request crossing midnight remains assigned to the day on which its durable intent was admitted. Completion/readback after midnight does not move/refund it. A new day creates a new derived bucket, never erases yesterday's journal, poison, fences or unknown outcomes. No carry-over/borrowing by default.
6. Durable UTC high-water/monotonic-duration checks must refuse rollback or incompatible boot/clock origin; large unexplained forward jumps must not mint allowance. Use trusted UTC for day identity and monotonic time for deadlines. Define drift/clock-reconciliation policy before deployment; simulation does not qualify clock trust.
7. GPU lifetime is separately funded before child start. For a lease crossing a calendar boundary, pre-reserve each day's portion against that day's approved GPU scope, or refuse such a lease with a bounded cleanup margin. Do not debit the entire cross-midnight lifetime only to yesterday and give today a second unbounded budget. The request-day tests here do not implement/test GPU cross-day funding; that remains a required future test.
8. Keep durable per-worker UUID/process-birth/owner identity, deadlines, queue/concurrency, current model readiness and cleanup proof. CPU gateway may be continuously available; GPU load/residency is finite. On shutdown/restart/crash, reconcile old owned work before new GPU admission; no attach-by-PID guess, TTL unlock or unknown-work replay.
9. Scope regular-service authorization to approved start/end dates, daily maxima and finite total maxima (proposed7days). Expiry prevents new AI work and drains/stops the owned child safely. Do not grant indefinite automatic daily renewal from this proposal.
10. Logs/UI expose plain status and non-secret counters. Tokens remain backend-only. Reuse the confirmed existing SSH route/account and server-held token after existing authorization is established; never enter raw tokens into the React form to make installation easier.

The fixed M1 ledger/one-lease system cannot implement these requirements with a new JSON cap alone. A new normative service/accounting amendment and compatibility/security review are necessary before implementation. Daily authority must be verified on the actual PostgreSQL/control service with race, midnight, crash, duplicate, uncertainty, cleanup, expiry and failure tests before any claim of operational support.

## 5. Historical arithmetic correction

If preserving all old permission, the old GPU allowance is18900 charged +2700 unreserved =21600. The prior12-call phase would add3600, giving cap25200 and projected charges22500; the prior20-call phase would add7200, giving cap28800 and projected charges26100. The earlier cap labels22500/26100 implicitly reused the old2700 and must not be presented as preserving it. Neither phase is the new primary daily-service proposal.

For a future7-day100/day pilot, request allowance is independently at most700 and compute allowance50400s. Daily caps cannot be pooled into one day; unused daily allowance expires. Existing historical request/GPU scopes remain unchanged and do not become commissioning allowance. No future cumulative usage is recorded before actual admitted work.

## 6. Remaining decisions and gaps

Approved intent:regular local app + real API. Approved safe actions:both SSH and Thai-midnight checks, now completed within audit scope. Still proposals/pending:final daily quota/count scope, timezone/day definition, pilot dates/expiry, GPU UUID/allocation/daily seconds, idle/lease policy, retry/dispatch rules, source scope, server-held token handling and new service-authority contract.

SSH authentication/path access now need no user intervention. Daily quota remains NOT_IMPLEMENTED; tests here do not change that status. Existing normal-launcher versus qualified-authority composition, cached M1 readiness, error/unknown-outcome wording, screenshot allowlisting, frontend defects, branch integration, candidate/main build and guarded recovery findings remain as in AUDIT.md. Frontend tests/typecheck/build and actual browser/main/API acceptance were not newly run by these safe checks.

No implementation, permissions/credentials/config, source images, real ledgers/windows, service state, GPU allocation or host clock was changed. No new model request was made. The app must not be labelled ready for routine use until the selected daily contract is implemented, integrated and validated on the intended main build and actual private API.
