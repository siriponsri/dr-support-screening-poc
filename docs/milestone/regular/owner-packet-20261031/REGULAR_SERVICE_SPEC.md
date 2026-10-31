# Regular local-app/Model API service specification

Normative requirements for this new owner-approved engineering scope. Read [authorization](AUTHORIZATION_AND_QUOTAS.md) and [the implementation plan](IMPLEMENTATION_PLAN.md). Current implementation does not yet satisfy this specification. Final daily GPU reservation cap is43200s within the06:00–22:00 Thai opportunity window; there is no57600s allowance.

## RS-01. Compatibility and scope

Keep existing clinician review, image admission, patient/eye resolver, modality, model/provider/checkpoint identity, PRISM frozen-input/native-entry, original coordinates, annotation provenance, final-grade/completeness and dataset/export rules. No new referral rule, threshold/model change, fabricated XAI, calibrated-probability claim or empty-ROI negative interpretation. A scheduling feature must never create a physician label or confirmation.

Use the existing review/remote profile and QA_SERVER topology. Do not quietly switch to QA_LOCAL, shared process-global workspace, mock providers or raw PRISM prediction to pass acceptance. Add a compatible service/accounting/orchestration adapter and additive job surfaces; old finite decisions/routes remain unchanged and closed. These approved new regular-service requirements replace finite-session orchestration only for the new authority, not historical approvals or protected clinical contracts. Report an exact uncovered frozen-contract conflict before implementing a conflicting path; continue independent work.

## RS-02. Actors, isolation and secrets

Support3–5 separately owned local app contexts/workstations sharing one private Model API. The normal local launcher serves `/app/` on loopback with the active workspace owned by that app/user context. A shared app instance's process-global store/workspace selection is not user isolation. Prove that userA's batch/open/workspace/review actions cannot change userB's active store or expose B's files, results, quota-administration controls or annotations.

An authenticated clinician/workstation/service identity, authorized project/workspace scope and request identity must be bound server-side to jobs and audit events. Client JSON `reviewer`, user ID or bearer-presence boolean is not authentication. Map the existing approved backend identity through a reviewed trusted-user mechanism; new principals/credentials/role grants require concrete action-time permission. Code against the chosen boundary and provide offline fixtures while provisioning is pending; do not claim live multiuser acceptance from fabricated actor strings.

Keep model credentials in backend memory/private configuration only. The clinician UI shows connection name/state and token-configured boolean, never token bytes or a token-entry form in the owned regular-service flow. Do not distribute the DR SSH private key to clinicians. Model API stays behind the approved private route/authentication boundary; no new public listener or permissive CORS is implied. Operator-only controls must not be available through an untrusted clinician request.

## RS-03. One daily batch per user is durable backlog

Accept/import approximately100 images per user in one daily action using existing approved local folder/file boundaries. The local workstation owns originals, case state, annotations, export and a durable batch manifest. Preserve immutable originals; no destructive move/rename/recompression. An import does not authorize transmitting new private hospital data. Transmit an image only after existing admission/source authorization and model gates pass.

Manifest logical requirements:stable batch ID and idempotent import identity; authenticated owner/project/workspace; admitted case/source SHA256 references; per-image expected grader/modality and PRISM stages; source/admission/context/revision evidence; creation/updated timestamps; stage/job IDs; result/history/readback references; explicit progress, blocked/partial/cancelled/uncertain states. Reuse repository contracts and identifiers; do not invent competing patient/eye types. Do not send local paths or unnecessary clinical identifiers to the remote scheduler or export them in primary UI.

Hash duplicates follow existing admission/alias semantics. A repeated browser import/reconnect must find the same batch or report the actual duplicate policy, not create repeated model work. Rescan, missing-source or changed-case events must preserve clinician decisions and clearly invalidate stale not-yet-executed plans. Persist manifest/progress before acknowledging acceptance. Reopening the app resumes unsent eligible stages, never already sent or uncertain work.

The100 records live in durable backlog. They are not100 ready/active GPU jobs. Backlog size/import admission is distinct from active model-stage queue limits and daily model allowance. Surface a per-user summary of imported, needs context, ready, queued, running, both models saved, partial/blocked, cancelled and clinician-review progress.

## RS-04. Per-image stages and clinical gates

An eligible CFP image uses RETFound plus PRISM; an eligible UWF image uses USPEC plus PRISM with existing experimental/domain/release notices. PRISM remains lesion assistance, not a DR grader. Unknown/unsupported modality remains manual-only. Grader stage precedes PRISM stage for a case, and the next stage cannot hide a failed/uncertain predecessor.

Do not bypass Confirm Image, required context/QC, source provenance/privacy, ready capability, model pins or the current PRISM preview/one-use receipt/required input acknowledgement to fulfil the two-call target. Stage blocked by those gates is explicitly partial/needs action; it is not a successful two-model case or evidence of absent lesions. Preserve existing clinical decisions about ungradable/quality handling.

Use the existing immutable source/wire/mask/transform/pins/epoch binding and DB-enforced writer fence at PRISM native entry. Do not acquire a long case/source write fence for an entire100-image batch or hold a thread lock across ASGI awaits. Revalidate queued source, admission, case revision, workspace/provider identity and receipt immediately before dispatch. Prepare/acknowledge at a point that does not permit queue delay to silently expire or regenerate an acknowledged receipt. Stale/expired plans need the existing explicit user/review flow, not implicit replacement or legacy fallback.

After each result, verify provenance/schema/accepted input, persist the raw model result/history independently of human state and establish trusted readback before advancing that stage to saved. Store/model/accounting outcomes remain separate. Later AI cannot reset confirmed human grade, geometry, reviewer, completeness or audit history. A stale returned result remains recorded using current stale-result semantics without overwriting the current projection.

An image has two separate completion concepts:analysis complete(both required model stages durably saved/read back) and clinician review complete(existing human grade/findings/completeness contract). Never mark the latter merely because model jobs finish.

Required logical stage transitions (serialized names may reuse compatible existing contracts; primary UI uses plain labels):

| Logical state | Allowed next state / condition | Quota/result implication |
|---|---|---|
| Durable backlog | Needs action or eligible/ready after current gates | No model intent; not an active GPU job |
| Needs action | Ready only after existing explicit context/quality/preview actions | No fabricated confirmation/result |
| Ready | Fair queued promotion with owner scope and capacity hold | Pair hold reduces available, does not claim execution |
| Queued | Cancel-before-intent, back to needs action if stale, or admitted | Current source/revision/pins/receipt rechecked before admission |
| Admitted | Dispatch or known failure before dispatch with durable certainty | Intent consumed once; never use a cancellation race as refund proof |
| Dispatched / possibly sent | Result retained, definitive failure or sent/uncertain | No automatic inference retry |
| Result retained | Validated persisted/history then trusted readback, or explicit persistence/accounting failure | Model success is not overwritten by later logging failure |
| Saved/readback verified | Next required case stage or analysis complete | Human review/completeness remains independent |
| Sent/uncertain | Authenticated reconciliation/terminal proof only | Keep charge/fence/quarantine across restart/day; never return to queued automatically |
| Cancelled before intent | Terminal unsent state; explicit future user action only | Release only proven-unused hold; no automatic resume of user-cancelled work |

If stage2 cannot proceed after a successful grader, keep the grader saved and show partial/needs action; do not erase it to make the two-stage state look atomic. Batch summary derives from durable per-stage states and keeps source/model/persistence/accounting facts distinct.

## RS-05. Fair bounded asynchronous dispatch

One shared dispatcher admits at most5 active model-stage jobs:1 executing+4 waiting, and at most1 outstanding stage/user. Durable batch backlog is outside this count. Use fair round-robin or equivalently demonstrated per-user scheduling so one100-image upload cannot occupy all active slots or starve other users. Returning capacity promotes the next eligible user's stage; grader/PRISM sequencing is per-image, not permission to monopolize the GPU for a whole batch.

At server capacity, preserve the durable backlog/ticket and report plain waiting status or bounded rejection without duplicate submission. Queue/backlog identity and cancellation must be durable. Accepted model dispatch counts/quota semantics are RS-06; import/backlog acknowledgement alone is not an inference charge.

Provide additive asynchronous submit/status/cancel behavior with typed stable IDs, owner scoping and explicit states. Choose concrete routes/types after auditing existing APIs, document them before sharing/parallel implementation, and keep current provider contracts. Do not let a synchronous HTTP client wait through an unbounded queue or globally increase the existing30s model timeout. Queue wait, upload, prepare, execution, persistence/readback and overall client wait have separate bounded timing and telemetry. Refresh/poll/reconnect must not redispatch. No busy polling or automatic inference retry storm.

Cancellation before any model intent can remove unsent work and release only proven-unused reservations. After intent/possible dispatch, cancellation is not proof of no inference, refund, unlock or replay. Preserve authenticated terminal/native-entry proof and durable quarantine. State must distinguish queued, executing, result retained, saved/readback, definitive refusal/failure, cancelled-before-send, sent/uncertain and blocked/manual action. UI labels are plain language, not internal enum/error strings.

## RS-06. Daily quota, paired capacity and idempotency

The new service has one authoritative global daily cap1500 across users/workspaces/models/commissioning/rechecks. Count top-level newly admitted grader/PRISM execution intents once, durably before dispatch. Native PRISM tiles/folds/forwards remain bounded by existing model safeguards but are not additional top-level quota units. No automatic inference retry. A safe separately requested new attempt has a fresh auditable identity and consumes another slot if admitted.

Use transactional authority shared by all processes, durable across restart and tied to the authenticated new service configuration/lineage. A Python/process-local counter, mutable daily JSON reset, separate per-worker allowance, browser clock or caller-supplied date is insufficient. Preserve history/cumulative totals and derive day usage from immutable admissions or equivalently verifiable durable projections.

Prevent a falsely fully admitted two-model image when only one slot remains. Before starting a new image's first stage, atomically hold capacity for2 model intents in the appropriate day, with explicit used/reserved/available counters. Holds limit available capacity; they are not both falsely reported as executed model calls. Convert each hold to consumed intent exactly once at that stage's admission. Existing source/revision/QC/PRISM gates still apply.

Release an unconsumed hold only with durable proof that its stage was never dispatched and cannot race dispatch. A consumed/sent/uncertain intent is never refunded. If grader succeeds and PRISM is blocked/failed/not sent, preserve a partial result, accurate used/reserved state and the valid human workflow; never fabricate completeness or silently retry. Schedule pair holds fairly at promotion, rather than reserving all1500 slots for the first uploaded backlog.

At midnight, a consumed intent stays on its admission day. An unconsumed hold for a later stage must either remain valid only for that day with a new-day re-reservation before dispatch, or be atomically moved with proof that no intent exists, without moving consumed counts or exceeding either day. Define/test the chosen compatible policy; no borrowing yesterday's unspent slots to exceed today's1500. Same accepted operation/idempotency key+immutable request returns existing state across midnight/restart; different payload conflicts. An expired ticket or new worker epoch cannot manufacture a fresh safe attempt for old uncertain work.

Health/discovery/status/prepare/grant/readback/import/reopen and definitive pre-admission rejection use0 model slots. No hidden warmup/smoke/forward outside accounting. Commissioning20 calls are inside1500, not an additional allowance. Any additional necessary specified live checks also count within the same approved ceiling and must have a planned scope/count in evidence.

## RS-07. Calendar, clocks and service hours

Daily buckets use `Asia/Bangkok`,00:00 inclusive to next00:00 exclusive, with UTC event timestamps and explicit timezone/day identity. Thai midnight is17:00 UTC on the preceding UTC date. Store both high-water clock evidence and durable day assignment. Use trusted UTC for day identity and monotonic clocks for durations/deadlines; no OS clock/timezone change is needed.

An in-flight intent before midnight finishes/readbacks under its original day; no recount/refund/reset on completion after midnight. New-day availability does not clear unknown work, source fences, poison, reservations or unreconciled owned children. Clock rollback, incompatible boot/monotonic origin, unexplained forward jump or corrupt journal fails closed for new AI admission until safe reconciliation. Do not mint multiple day allowances by changing the system clock.

Allow new AI work only inside06:00–22:00 Thai and while request/compute/source/authority budgets permit. Enforce a bounded last-admission/cleanup margin so no new work knowingly overruns the funded schedule. Show closing/outside-hours state plainly. Outside hours, manual review/history/export/readback/status may continue without loading/forwarding models or creating a GPU lease. Existing in-flight/unknown work still must be reconciled safely; a calendar boundary is not a kill/replay shortcut.

## RS-08. Owned GPU lifecycle and residency accounting

Use only approved RTX UUID, after a fresh check that the intended ownership/allocation/headroom is available. Never select by GPU index alone or use the [other team] V100, [other team]/other workers, a GPU reset, process-group kill or team-service restart. Resource availability is not allocation permission.

Record and enforce43200s/day from [authorization](AUTHORIZATION_AND_QUOTAS.md). Full reserved lifetime includes loading, idle model residency, execution, draining and cleanup; report observed durations separately.24h CPU service availability does not grant86400s of daily GPU residency, and the16h AI opportunity window does not guarantee continuous warm models.

Charge each exclusive DR-worker reservation interval once. Models resident together share that wall-duration reservation; do not add per-model residency or measured elapsed/busy time again. Record charge/reserved/observed units explicitly. Funding records are idempotent and non-overlapping; do not double-debit a reopened handle, poll or normal model-stage switch. If observed overrun exceeds funded duration, record the overrun once and quarantine; never refund or erase unknown use to look within cap.

Idle unloading must release only owned DR resources under a finite recorded timeout. Claude chooses/qualifies bounded interval/lease sizing and cleanup margin against capacity and existing ceilings. A new authority may fund non-overlapping bounded residency intervals before use; it may not keep a worker alive past its funded/native deadline or charge a full parent lifetime plus the same child interval again. Preserve historical no-renewal decisions; new interval funding belongs only to the approved regular-service adapter. Stop new inference admission once compute is exhausted and keep manual functions usable.

Reuse existing qualified ceilings unless explicitly amended:one owned inference child, GPU concurrency1, VRAM<=10240MiB, RSS<=24GiB, project footprint<=40GiB, model CPU threads2, per-child <=42 jobs and <=2700s, native request<=30s with current PRISM sub-deadlines. Verify source/checkpoint/environment pins and no-forward load. Do not install general model dependencies over the qualified isolated USPEC/PRISM environments.

The new regular-service controller may retire a healthy bounded child after its limit, prove cleanup, and fund another owned child under the **new daily authority**. This is not renewal/reopening of any historical single-lease window. Reserve lifetime before starting; preserve conservative charges/unknown-stop treatment. Normal safe recycling is distinct from replaying a failed/uncertain job. On crash or lost cleanup proof, retain reservations/quarantine, reconcile exact owned identity and old authenticated work before starting another child. Never attach/kill by PID guess or remove a lock to continue.

For a funded lifetime crossing a day boundary, reserve the appropriate portions against each authorized day's compute bucket before start or decline it with cleanup margin. Request admission-day counting and GPU lifetime-day funding are separate. Do not charge a full cross-midnight lifetime only to yesterday and silently grant today's full overlapping residency. Admission hours currently prevent normal overnight work, but restart/drain/clock tests must still cover the boundary.

Keep service authority durable and revocable with approved configuration digest, model/device/principal/source scope and change/review record. There is no invented7-day expiry. Owner revocation stops new admissions and safely drains/stops only owned work. No synthetic signature or per-image owner re-approval is required for routine work already inside the approved service scope; new security/data/model/device permissions remain concrete separate actions.

## RS-09. Truthful readiness and clinician-facing behavior

Distinguish CPU app/database availability, private route/authentication, assets verified, actual model load, qualified bound protocol, request/quota capacity, hours/GPU funding, queue state and last successful real inference/readback. Health200, cached startup identity or a successful SSH login is not AI readiness.

Fix the M1 cached-status path so polling/focus refresh can truthfully mark dropped/restored connectivity without re-reading/returning secrets, changing the owned provider/endpoint identity, racing entry fencing or counting/loading inference. Keep local review usable while AI is unavailable. Expose useful per-user batch progress and a global capacity summary that does not disclose another user's clinical data.

Use plain clinical wording for timeout/disconnect/refusal, certainty/uncertainty and next action. Never tell a user 'no model work started' after a possibly sent call. Unknown result:do not resend; preserve the job/reference for operator reconciliation. Fix grade-label clipping and dataset raw-enum display using existing tokens/label helpers, with no grade/eligibility semantics change.

## RS-10. Persistence, export, observability and recovery

Clinical data stays with the approved local app/PostgreSQL/workspace. Model service job bookkeeping must not become a second authoritative patient/annotation store or accumulate raw images/paths/secrets. Retain only needed scoped audit/job/result evidence through the approved private storage policy. New storage/schema changes must be additive/checksummed and reviewed; never edit old migrations or dump guards out of existence.

Prove model response -> validated provenance -> durable raw history -> trusted readback -> human edit/save -> reopen/restart -> correct export. Keep physician/TEST_ONLY/raw AI separated; original source hashes/coordinates/pins remain stable. Guard-aware restore remains a separately explicit limitation until qualified; an unguarded rehearsal is not that pass. Do not silently weaken recovery refusal to finish this task.

Measure queue wait, stage latency, execution, readback, cold load/residency, per-user fairness, batch completion, failed/uncertain outcomes and daily used/held/remaining counters with pinned revision/time units. Per-call/model metrics and whole-session time remain distinct. The six-request705.486s historical session and loading16.154s/11.812s cannot establish a500-image/day throughput or clinical-performance claim.

Follow [validation](VALIDATION_MATRIX.md) and [operations/rollback](OPERATIONS_AND_ROLLBACK.md). Scope blocked actions precisely. A branch, mock/prototype, documentation checker, healthy metadata, extracted package or test count alone does not establish a ready regular service.
