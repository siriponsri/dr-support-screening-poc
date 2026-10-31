# AC-11 and MS-07: gap analysis and offline fault injection

Status: analysis and offline tests only / 26 October 2026 / Claude Code. No
service was stopped, no GPU or model call was made, and no recovery or entry
guard behaviour was changed. TEST_ONLY engineering evidence, not a clinical or
hospital acceptance.

## AC-11: network, API or authentication failure ends correctly

What holds today (verified by code reading and by
`tests/test_m1_fault_injection.py`, MockTransport only):

- A failed grading request never saves a result and never changes the
  clinician's grade, annotations, review or inference history.
- Each request makes exactly one predict call; nothing retries automatically.
  PRISM execute never resubmits; a lost grant quarantines the fence.
- In the plain review profile every request re-checks `/health` and
  `/v1/models` first. An unreachable server or a rejected token answers 503
  "manual review remains available" before any predict, and the next request
  works once the link is back.
- The token never appears in a reply.

| ID | Gap | Today | Proposed change (needs owner approval) | Test |
| --- | --- | --- | --- | --- |
| G1 | A dropped connection during grading shows raw transport text | 502 "Remote model error: Remote model transport error: ..." | Plain reply "The model server connection was lost. Nothing was saved; manual review remains available." Raw class stays in the log only | strict xfail `test_gap_g1_*` |
| G2 | A grading timeout names an operator setting | 504 "... inspect REMOTE_MODEL_URL ..." | "The model server did not answer in time. Nothing was saved; manual review remains available." | strict xfail `test_gap_g2_*` |
| G3 | In an M1 workspace session the "AI READY" label is never refreshed after a link drop (cached probe) | First request then fails 502/504, nothing saved | Re-probe the authenticated connection on the existing 30 s / focus refresh, without re-reading the token | none yet (needs the M1 factory rig) |
| G4 | PRISM "uncertain" (sent, outcome unknown) and "failed" show the same text | 502 "failed verification; cannot be reused" | A separate plain line for uncertain: "The result could not be confirmed. Do not resend; ask the operator to check the session." | none yet |
| G5 | A non-JSON error body (for example a tunnel HTML 502) on the PRISM channel raises a parse error instead of a transport refusal | 409 at prepare, non-uncertain 502 at execute | Treat a non-JSON error body as `TransportError` (execute: uncertain) | strict xfail `test_gap_g5_*` |
| G6 | No test of a review-app restart during a global grading request | Nothing is written before the result, so nothing to recover; the result is lost | Add a test only | none |

G1, G2, G4 and G5 change clinician-facing wording or error classes, and G3
changes how the M1 session re-checks the link. None changes recovery scope,
quota, timeouts or the entry guard. When approved, each fix flips its strict
xfail to a pass.

## MS-07: guard-aware backup/restore and the export authority gap

- **RC-03 (guard-aware recovery) is not met.** App-schema dumps do not include
  the cross-schema entry guard. The recovery tool deliberately refuses a source
  or target that carries the guard (`test_entry_guard_source_is_not_qualified_and_never_starts_dump`,
  `test_entry_guard_target_is_not_qualified_before_any_restore_write`,
  `test_entry_guard_found_after_restore_cannot_receive_success_receipt`).
- The AC-13 PASS (2026-10-25) was a rehearsal schema without the guard. It does
  not qualify a guarded database.
- RC-04 export: the restored identity-only workspace refuses export (expected).
  Export after restore with an active export profile is not yet shown.

Options for RC-03 (plan only; changes the recovery contract, so owner and
DB/IT approval are needed before any code):

| Option | What it means | For | Against |
| --- | --- | --- | --- |
| A. Dump and restore the guard schema too | Extend the bundle with the guard schema, roles and triggers, pinned by its own hash | One restore brings back the exact protection | Larger contract; roles must exist on the target; new rehearsal |
| B. Restore without guard, then re-install it | Keep app-schema dumps; after restore, re-run the existing guard installer and its qualification before the app opens | Reuses tested pieces; smaller change | A window where the target has no guard; must stay closed until re-qualified |
| C. Keep NOT_QUALIFIED and document a manual procedure | No code; a written operator procedure | No engineering risk now | Not a release-grade recovery; RK-04 stays a release blocker |

Recommendation: B, with the target kept closed (no app start) until the guard
qualification passes, because it reuses the existing installer and adds no new
dump format. Offline fault-injection for B can be written first against a
synthetic schema (guard missing, guard partially installed, wrong role, app
started before qualification); the existing rejection tests stay.

## What is not run

Live interruption against the GPU host, an M1 session link drop, a real
guarded restore and any hospital target. No service was stopped and no new GPU
session or quota was used.
