# Hospital M1 amendment: MS-03 service session continuation

Status: owner-approved plan (2026-10-25, chat;
[plan](../../planning/HOSPITAL_M1_MS03_BOUNDED_SESSION_PLAN_20261025.md)). Activation
still needs the owner's approval of the exact proposal SHA-256. Extends
[M1_ACCOUNTING_CONTINUATION.md](M1_ACCOUNTING_CONTINUATION.md) and
[M1_PRISM_WINDOW_CONTINUATION.md](M1_PRISM_WINDOW_CONTINUATION.md); every rule
there still applies unless replaced below.

## Why

The PRISM decision (`HOSPITAL_M1_ACCOUNTING_PRISM_20261024`) closed its only
window at 534 used. The 2026-10-23 export still records nine unsent post-fix
operations, and that export may not be continued again directly. MS-03 needs
one synthetic watchdog/OOM window (no requests) and one bounded service session
that uses six of those post-fix operations.

## Decision

| Item | Value |
| --- | --- |
| Decision | `HOSPITAL_M1_ACCOUNTING_SERVICE_20261025`, schema `hospital-m1-service-continuation.v1` |
| Base / cap | `base_used` = the fenced PRISM source's `global_used` (534); `cap` = base + 6 (540), never above 549 |
| Window A | `HOSPITAL_M1_QA_SERVER_WATCHDOG_20261025`: QA_SERVER, GPU0, `gpu_seconds_cap` 900, `wall_seconds_cap` 1800, no refund, no renewal, **no operations** |
| Window B | `HOSPITAL_M1_QA_SERVER_SERVICE_20261025`: QA_SERVER, GPU0, `gpu_seconds_cap` 3600, `wall_seconds_cap` 7200, no refund, no renewal |
| Operations | exactly 6 of the 2026-10-23 export's unsent `post_fix_verification` operations; every field identical except `window_id` (window B) and therefore `job_id` |
| Allocations | `post_fix_verification` 6, `new_admissions_max` 6 |
| GPU budget | prior preserved = the PRISM origin's preserved seconds + the PRISM window charge; (prior − 17002.874) + 900 + 3600 must stay within the approved 21600 new seconds |

The six operations are the three non-PRISM post-fix operations (USPEC 2 UWF,
RETFound 1 CFP; the register has only one RETFound operation) and the first
three PRISM post-fix operations in register order (1 UWF, 2 CFP). The owner
approves the exact list through the proposal hash.

## Lineage

1. The PRISM ledger is permanently fenced with the existing `fence_handover`
   toward the newly deployed, CPU-identity-checked installation.
2. The proposal pins eleven files (the last one is named in step 3): the seven PRISM-source anchors with the same
   names as the PRISM decision (`handover_export`, `source_proposal`,
   `source_approval`, `source_journal`, `source_journal_head`,
   `source_server_budget`, `source_server_complete`), plus
   `source_accounting` (the PRISM `ACCOUNTING.json`), `origin_export` and
   `origin_proposal` (the 2026-10-23 `HANDOVER_EXPORT.json` and `PROPOSAL.json`).
3. The verifier checks the PRISM source exactly as the PRISM decision checked
   the 2026-10-23 source (export hashes, fence lock, journal replay, journal head,
   closed window with a charge of at least 3600 s), and also that:
   - the PRISM proposal's own `upstream` pins equal the hashes of
     `origin_export` and `origin_proposal`, and the PRISM `base_used` equals the
     origin export's `global_used`;
   - the origin directory still carries `HANDOVER.lock` identical to its export;
   - `source_accounting` is the PRISM origin record (same proposal/approval,
     base/cap and upstream); its preserved GPU seconds must equal 17002.874 plus
     the closed 2026-10-23 Server window charge (at least 10800 s), re-derived
     from the eleventh pin `origin_server_budget` (that window's `BUDGET.json`,
     whose hash the origin export records);
   - no PRISM-decision operation is a post-fix operation;
   - each new operation equals an unsent origin `post_fix_verification`
     operation except its window.
4. A new, separate accounting directory is used; neither source is reused.

## Window order

Windows activate in the decision's order. Window A must be activated, run and
confirmed closed before window B can be activated; once B exists, A can never
be activated. Window A has no operations, so no request can be admitted in it;
the admission consumer accepts only window B. The ledger closes or fences only
when every activated window is closed. Window B's summary counts window A's
charge as prior use, and a fence export of this decision anchors every activated
window's budget, activation and charge (single-window decisions keep their
export shape). Fencing still requires window B: if the owner stops after phase
A, a later handover needs its own amendment. Starting window B after a failed phase A
is an operator rule (plan section 3): the accounting order alone does not judge
the watchdog result.

## Phase A runtime

`scripts/model-server/m1_watchdog.py` holds the ledger, activates window A,
reserves its one 900 s lease and runs synthetic cases, each in a fresh owned
child with low supervisor ceilings (VRAM 2 GiB, RAM 4 GiB, request 10 s). CUDA
children use a torch memory fraction of 1 GiB (within the plan's 1.5 GiB, so the
CUDA context also fits under the 2 GiB ceiling). No model weights, images,
credentials or listener are used, and no operation is admitted. Each child runs
under `prlimit` (no core file, bounded file size and descriptors; address space
only for the non-CUDA RAM case) and `nice`, and raises its own OOM score so the
kernel would pick it before any team process. The run refuses to start with
less than 12 GiB of available host RAM. A read-only cgroup check is recorded,
nothing is configured. GPU1 compute processes and the Ollama processes are
recorded before and after; every one seen before must still be running (new team
processes are only reported). Confirmed cleanup closes window A; an unconfirmed
cleanup keeps the charge, quarantines the window and keeps the ledger owned.

## Acceptance

Synthetic tests: earlier decisions behave unchanged; the service decision
continues only from a fenced PRISM source with exact anchors, usage and closed
window, and from the matching 2026-10-23 export; altered anchors, an unfenced
source, extra, changed or non-post-fix operations, a cap above base + 6 or 549,
or a budget above 21600 new seconds are refused; window B cannot activate before
window A is closed, window A cannot activate after B, and only window B admits
operations. Watchdog evaluation and orchestration are tested with fake children.
