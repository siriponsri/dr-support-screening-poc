# Hospital M1: bounded accounting continuation

Status: owner-directed control implementation; live activation NOT_RUN.
This contract extends the existing `BatchLedger` and `BatchBudget`. It does not
start services, grant access, qualify a GPU, change model contracts or register a
new inference route. The runtime admission consumer remains a separate gate.

## Immutable scope

- Legacy `BASE_USED=49`, `CAP=529`, original480-job transitions and the exact
 175-job session restriction remain unchanged.
- The verified M1 continuation starts at525 and has a cumulative cap549:
 24 new admissions, comprising the previously unused4 plus the approved20.
- Exact allocations: `server_acceptance=9`, `local_acceptance=6`,
 `post_fix_verification=9`. Every operation chooses its named window before
 activation. Post-fix operations are newly approved verifications, never an
 automatic replay of an old terminal job.
- Named windows are `HOSPITAL_M1_QA_SERVER_20261023` and
 `HOSPITAL_M1_QA_LOCAL_20261023`. Each permits GPU0 only, at most10800 GPU
 seconds and14400 wall seconds, no renewal and no refund.
- Old charges4772.230 and9800.644 seconds and the closed finite-demo reservation
 2430 seconds remain intact. The preserved aggregate is17002.874 seconds.
 Reservations are conservative accounting, not measured kernel occupancy.

## Externally pinned authorization

`BatchLedger.for_continuation` accepts proposal/approval file paths, their two
expected SHA-256 values, explicit upstream file paths and an independently
identified source-installation digest. The expected hashes must come from the
owner approval channel; an adjacent file declaring its own hash is not approval.
No live proposal, approval or activation is shipped in Git by this change.

The proposal has exactly these fields:

```text
schema = hospital-m1-continuation.v1
decision_id = HOSPITAL_M1_ACCOUNTING_20261023
base_used = 525
cap = 549
new_admissions_max = 24
allocations = the exact9/6/9 mapping above
windows = both exact IDs, each with:
  profile = QA_SERVER or QA_LOCAL
  gpu_index = 0
  gpu_seconds_cap = 10800
  wall_seconds_cap = 14400
  refund_unused = false
  renew = false
accounting_directory = one absolute, private source authority directory
installation_sha256 = approved source installation identity digest
upstream = SHA-256 map for the seven anchors below
operations = exact24 immutable operation objects
```

The separate approval has exactly `schema= hospital-m1-owner-approval.v1`,
the same `decision_id`, the exact `proposal_sha256`, and
`status=EXPLICIT_OWNER_APPROVED_NOT_ACTIVATED`.

The verifier reads the actual upstream bytes and checks their pinned hashes:

1. `batch_ledger`: exact repository-pinned closed ledger hash; independently
   replay its hash chain/transitions,476 intents and480 terminal jobs
   (467 readback passes,9 failures and4 premodel blocks).
2. `original_budget` and `second_budget`: internal body hash, original manifest,
   finite original clocks, exact preserved charges and closed/unquarantined state.
3. `demo_requests`: one valid hash-chained ANCHOR row only, base525/cap529 and
   the same original ledger hash. Any inference intent rejects continuation.
4. `demo_activation`: retained original activation identity and allowance.
5. `demo_complete`: confirmed listener/owned cleanup and full2430 reservation.
6. `demo_ready`: exact GPU0 identity and three load records with zero forwards.

A declaration of525, a newly invented closure or an altered old file is never
substituted for this replay. The source files are read-only; immutable copies
are retained in the continuation's `upstream/` directory.

Each operation contains exactly `job_id`, `operation_id`, `purpose`, `window_id`,
`source_sha256`, `model_id`, `modality`, `model_pins_sha256`, `parameters_sha256`
and `preprocessing_id`. `job_id` hashes the canonical remaining fields. IDs are
unique and disjoint from all old terminal IDs. USPEC is UWF-only, RETFound is
CFP-only, and PRISM is a lesion provider for its explicitly approved modality.
The accounting layer does not itself verify weights or clinical performance.

## One continuation owner and durable admission

The approval binds one canonical directory and source installation. Another
directory is not a fresh allowance. Existing exclusive `SESSION.lock`, symlink/
reparse checks, hash chaining and poisoned-owner behavior remain in use.

M1 origin creation retains proposal/approval/closure copies and a high-water
`JOURNAL_HEAD.json`. Every append fsyncs the journal and atomically replaces the
head before returning. A torn append, missing/old head or partial origin/window
activation fails closed and preserves ownership gates. No routine resets these
files or adopts an unmarked journal.

`ledger.admit(job_id, request_sha256=..., budget=...)` is the only M1 path to an
`ATTEMPT_INTENT`. It requires the exact owned window budget, funded live worker
lease, remaining time, matching operation/window and no uncertain prior intent.
The request digest binds the actual prepared request. The intent is fsynced
before the caller receives an admission ID and before any execute/predict send.

The qualified runtime must bind that ID to exactly one native execution and
cover all inference surfaces with this same gate. Nested UI/backend/model stages
must share one admission, not increment separate counters. This change alone
does not integrate or qualify that runtime consumer.

Preparation can record `BLOCKED_PREMODEL` without consuming an inference intent.
A sent or uncertain attempt is consumed, terminal jobs never become pending,
and no automatic inference retry exists. A terminal logging failure poisons
further admissions; it must not relabel an already returned inference result as
model failure. Model, persistence and accounting outcomes stay distinct.

## Lifetime reservation and closure

`activate_continuation_window` creates one Server window under the ledger owner.
Activation does not start its worker. `BatchBudget(..., session_id=...,
clock_origin=...)` requires the immutable activation and matching host/boot clock
origin. Clocks are not reset on handle reopen; different-machine monotonic clocks
are never compared or accepted as continuation of an old window.

`reserve_worker` reserves the full10800-second owned lifetime before load/start,
including load, idle residency and inference. The runtime must additionally
enforce native deadlines and cleanup; accounting is not a process supervisor.
There is one lease only, no renewal and no early-stop refund. Confirmed stop
closes the window. Unknown/late stop retains its reservation and quarantine;
observed overrun is charged and reported rather than refunded. A second lease,
expired window, clock rollback or incompatible clock origin cannot start work.

The old budget files are never written. Their original clocks, reservations and
charges remain visible independently from the new window's charge.

## One-way handover and explicit Local boundary

After the Server window is closed and no uncertain intent remains,
`ledger.fence_handover(destination_installation_sha256=...)` can durably create a
permanent source `HANDOVER.lock`, then an immutable export receipt containing
the authority/approval identity, journal head, usage and remaining operation IDs.
The destination digest must represent an actually approved installation, not an
invented hospital host. The source retains its old owner lock and all data.
Partial export still leaves the source fenced. There is no automatic undo.

**Local adoption and activation are deliberately unavailable in this version:**
`M1_LOCAL_ADOPTION_NOT_QUALIFIED`. No Local budget/window clock is invented and
no independent Local counter is created. Copied files or an export receipt are
not an activation grant. Future adoption must qualify the destination, exact
source-fenced lineage and one-use owner transition before enabling Local.

Software files alone do not establish cryptographic protection against malicious
offline cloning or whole-directory rollback. One designated installation and
exclusive operator custody remain required; no stronger protection is claimed.

## Required evidence

Synthetic tests cover pinned upstream replay, exact allocations/cap, old-byte
preservation, concurrent owner refusal, durable-before-dispatch admission,
duplicates/uncertainty, partial writes/high-water checks, lifetime reservation,
clock/deadline/no-renewal behavior, source fencing and explicit Local denial.
They do not execute a model, contact a service, use a GPU or qualify hospital
hardware. Actual Server/Local activation and native admission integration remain
NOT_RUN until separately executed within the approved scope.
