# Hospital M1 amendment: PRISM window continuation

Status: owner-approved plan (2026-10-24, chat;
[plan](../../planning/HOSPITAL_M1_PRISM_GPU_WINDOW_PLAN_20261024.md)). Activation
still needs the owner's approval of the exact proposal SHA-256. Extends
[M1_ACCOUNTING_CONTINUATION.md](M1_ACCOUNTING_CONTINUATION.md); every rule there
still applies unless replaced below.

## Why

The 2026-10-23 continuation (`HOSPITAL_M1_ACCOUNTING_20261023`) closed its only
Server window at 531 used of cap 549. Its three PRISM operations were never sent
(the preview gate refused them before admission, HANDOFF §25). That decision
accepts exactly two named windows, the Server window is permanently closed, and
Local adoption is deliberately unavailable, so those operations cannot run under
it.

## Decision

| Item | Value |
| --- | --- |
| Decision | `HOSPITAL_M1_ACCOUNTING_PRISM_20261024`, schema `hospital-m1-prism-continuation.v1` |
| Base / cap | `base_used` = the fenced source's `global_used` (531); `cap` = base + 3 (534), never above 549 |
| Window | one, `HOSPITAL_M1_QA_SERVER_PRISM_20261024`: QA_SERVER, GPU0 only, `gpu_seconds_cap` 3600, `wall_seconds_cap` 7200, no refund, no renewal |
| Operations | exactly the source's unsent `server_acceptance` PRISM operations (3); every field identical except `window_id` and therefore `job_id` |
| Allocations | `server_acceptance` 3 · `new_admissions_max` 3 |
| GPU budget | prior preserved = 17002.874 + the source window's charge; source charge + 3600 must stay within the approved 21600 new seconds |

The wall cap exceeds the GPU cap only because the existing reservation rule
needs the whole lease plus a 45-second cleanup margin inside the window. The
charged reservation is the GPU cap (3600 s); the actual session stays at most
2640 s.

## Linear lineage: fence first, then continue

1. The source ledger is permanently fenced with the existing
   `fence_handover(destination_installation_sha256=…)`. The destination is the
   newly deployed, CPU-identity-checked host installation. The source keeps its
   owner lock and all data; it can never admit again.
2. The new proposal pins seven upstream files: `handover_export`,
   `source_proposal`, `source_approval`, `source_journal`, `source_journal_head`,
   `source_server_budget`, `source_server_complete`.
3. The verifier independently:
   - checks the export schema/status, Local unavailable, and that every hash in it
     matches the pinned files and the destination installation;
   - checks the source proposal/approval are the 2026-10-23 decision;
   - replays the source journal (chain, transitions, manifest, no uncertain
     state) and derives `global_used` = 525 + intents, which must equal the export
     and the new `base_used`;
   - checks the journal head, the remaining job IDs, and that the source Server
     window budget is closed (no active lease, not quarantined);
   - checks each new operation against its source operation.
4. The source must still carry its `HANDOVER.lock` (identical to the export),
   and all seven anchors must come from that one source directory.
5. A new, separate accounting directory is used; the source directory is never
   reused.

Nothing is written back into the fenced source, so the software cannot stop a
second PRISM decision over the same export; only one such proposal may ever be
approved. This is the owner's approval control, as for 2026-10-23.

The remaining Local (6) and post-fix (9) operations stay recorded in the export
as unsent. Using them later needs another owner decision that continues from
this decision's closure, never from the 2026-10-23 export again.

## Runtime

The ledger, window budget, admission consumer and host session read the window
name, caps, base, cap and preserved GPU seconds from the verified decision
instead of fixed constants. The 2026-10-23 decision keeps its exact values and
receipts. Everything else is unchanged: durable admission before dispatch, one
lease, no retry or renewal, confirmed stop closes the window, uncertain outcomes
are retained, and Local stays fail-closed.

## Acceptance

Synthetic tests: the 2026-10-23 behaviour is unchanged; a fenced source
continues only with exact anchors, usage, remaining operations and closed
window; altered or partial anchors, an unfenced source, extra or changed
operations, a cap above base + 3 or 549, or a different destination installation
are refused; the new window reserves 3600 s once, admits only its operations, and
closes on confirmed stop.
