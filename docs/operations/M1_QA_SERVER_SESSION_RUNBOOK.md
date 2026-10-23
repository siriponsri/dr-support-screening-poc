# Hospital M1 QA_SERVER bounded acceptance session — runbook

Status: prepared 23 October 2026; **not executed**. This is the bounded
acceptance runner, not the installed persistent hospital service.

## Fixed identities

| Item | Value |
| --- | --- |
| Approved proposal | `5a06f23cd93aaf018ff6ac0e65567004abd798d93e882cba19e210b275da535d` (owner approved in chat) |
| Approval file | `fc1f32ed61c868592568e60022aa172d0a7ebd596274199a90700f7e15acf901` |
| Host deployment | `deployments/m1-session-20261023-s02` (installation `93acfb89…d247b2`, source `2756751`) |
| Host inputs | `m1-continuation-20261023-v2/` (PROPOSAL, APPROVAL, PRISM_WORKSPACE_PINS, EXPECTED_BATCH_MODELS, UPSTREAM_PATHS) |
| Accounting directory | `/home/siripon/projects/dr-model-api-qa/m1-accounting-20261023` (created by the parent; never reused) |
| Window | `HOSPITAL_M1_QA_SERVER_20261023`, GPU0 only, one 10800 s lease, closing it closes the window |
| Workspace | `ws_m1_63ed86c7d44f46d59479` (TEST_ONLY) in the approved test database |

## Limits that shape the plan

- Child lifetime about 44 minutes (`SESSION_SECONDS=2640`); readiness must
  appear within 240 s.
- One charged request at a time; the next waits for the trusted readback.
- A failed or uncertain request stops admission for the rest of the window, so
  deliberate failure scenarios must not reach an admitted request, and they run
  last.
- Each request: about 30 s supervisor deadline; PRISM job 24 s.

## Before the GPU (no lease, no model)

1. From the main checkout run
   `python -m scripts.qa.m1_server_app prepare --workspace-id ws_m1_63ed86c7d44f46d59479`.
2. In the browser, open the Worklist, scan if needed, and **Confirm Image** for
   the six Server acceptance images and, if time allows later, the post-fix
   images. Reviewer: `TEST_ONLY_ENGINEERING`.
3. Stop the prepare app.
4. Report readiness to the owner and wait for the go-ahead.

## GPU window

5. On dr-train, start the parent in the background with the fixed arguments
   (`m1_session.py start …`, run directory `runs/m1-server-20261023-01`) and wait
   for `READY` and `STATUS.json`.
6. On Windows, from the main checkout:
   `python -m scripts.qa.m1_server_app serve --allow-remote-token-read --workspace-id ws_m1_63ed86c7d44f46d59479 --prism-pins <v2 PRISM pins>`.
7. **Fresh** (3 requests): USPEC on the fresh UWF image, RETFound on the fresh
   CFP image, PRISM protected preview on the fresh UWF image. After each:
   `m1_server_app readback --run <run> --workspace-id … --models … --prism-pins …`.
8. **Restart** (3): stop and start `serve`, reopen the fresh cases and confirm
   persisted results, then USPEC/RETFound/PRISM-CFP on the restart images, with
   readback after each.
9. **Recovery** (3): stop the tunnel/app between requests (never during an
   admitted request), confirm manual review remains usable and no charge was
   made, restart `serve`, then run the recovery trio with readback.
10. Post-fix verifications only if time remains and each historical failure
    path is genuinely exercised by the new route.
11. Stop: `m1_session.py stop --run <run>`; confirm `COMPLETE.json` reports
    `cleanup_confirmed`, `window_stop` and `ledger_close` as confirmed.

## Evidence to keep

STATUS/COMPLETE receipts, ledger journal head, readback receipts, screenshots of
each step, PostgreSQL readback output, timings, and any refusal codes. No
token, DSN or patient identifier is copied into evidence.
