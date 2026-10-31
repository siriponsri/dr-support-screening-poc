# DR-screening audit before a Claude continuation goal

Audit date: 2026-10-31 UTC. Read-only engineering audit, not an authorization to run models, expand quota, deploy, merge, change access or issue a final release. User intent: finish a Windows local web app connected to actual Model API inference. This report is input to the next owner decision and Claude goal; it is not that goal.

## 1. Conclusion

The repository contains an actual-model integration and retained successful readbacks. It is not merely a mock UI. However, its qualified integration still depends on a finite, operator-assisted QA runner. The normal workstation launcher does not construct the same workspace authority / protected PRISM composition. Buying more requests alone does not complete the requested outcome.

The next task must close three separate gaps: finish/review/integrate the three current branches; make the approved real API path usable from the normal local application with owned lifecycle and truthful status; then run a new, explicitly bounded real API acceptance window. Installation packaging alone cannot replace the last two outcomes.

No inference, GPU allocation, quota mutation, service restart, deployment, push or merge was performed in this audit. No private image/clinical payload or secret value was read. SSH metadata and selected non-secret retained accounting receipts were read.

## 2. Snapshot and ownership

Repository/worktree: `C:/Users/User/Desktop/myProject/dr-support-screening-poc`.

Main: `9c52853db8dd2b879f1151cb1308c860cb78b5af`. Live `git ls-remote` also returned this SHA for `origin/main`. No refs were returned for the three feature branch names below. No fetch, checkout or Git config mutation was made.

Main has no tracked/index diff. Existing untracked owner artifacts remain: `.vscode/`, `DR_M1_LOCAL_CODEX_HANDOFF.md`, `docs/benchmarks/`, `docs/deployment-preparation/`, three presentation Claude handoff/review documents, and `docs/presentation/dr-screening-demo/`. Do not clean, absorb or package these automatically.

| Worktree below `C:/Users/User/Documents/Codex/2026-10-21/task/` | Exact branch | HEAD | State captured 01:25 UTC |
|---|---|---|---|
| `m1-watchdog-detail-worktree` | `fix/m1-watchdog-error-detail` | `72c6ff641ddd7019475040cc11db190894a76147` | clean; two commits beyond main |
| `m1-offline-checks-worktree` | `feat/m1-offline-acceptance-checks` | `193503585ce00c66a6bc3028ec4f27c2221b9b1e` | dirty only `scripts/qa/check_export_folder.py`; two commits beyond main |
| `m1-install-manual-worktree` | `docs/m1-install-candidate-manual` | `7bfce34d65f909c644a5e0fdd8e2e20ed0e787ca` | clean; two commits beyond main |

The offline checker WIP SHA-256 is `0ae837631ef607f9a552685aa55a715df14bfb76df5c1698ee08c1ea3475e587`. The three committed file sets do not overlap. They were exported into an isolated audit snapshot, then this single WIP file was overlaid. This is an overlay snapshot, not a merge commit, validated integration branch or accepted release. `SNAPSHOT.json` records every selected file hash and exact refs.

Git initially refused worktree status because the owner is `User` and the sandbox user differs. Subsequent read-only commands used `git -c safe.directory=<exact-known-worktree>` for each known path; global configuration, ownership and ACLs were not changed. `.agents/skills/` is absent at the authoritative checkout. README, DESIGN, operations/manual sources and applicable M1 acceptance/accounting/authority contracts were inspected. Claude remains the existing application implementation writer; this audit did not edit those files.

## 3. Findings and concrete evidence

Severity: P0 blocks a new live run or acceptance; P1 must close before claiming the requested handoff; P2 is a bounded documentation/packaging issue. This is engineering severity, not a medical risk rating.

| ID | Severity | Finding / source | Evidence and smallest next action |
|---|---|---|---|
| F01 | P0 | Current service allowance is exhausted and all retained windows are closed. `M1_SERVICE_SESSION_CONTINUATION.md`, `batch_ledger.py:24,48,408-430,525-543` | The actual retained service COMPLETE has `global_used=540`, `cap=540`, `usage_status=EXACT`, no active admission and zero retries. The broader historical approved maximum 549 is not the active service ledger cap. Create a new approved lineage; never reopen/reset the old source. |
| F02 | P0 | New quota/window IDs cannot be enabled by editing only a JSON file. `scripts/qa/batch_runtime/batch_ledger.py:48-68,408-430,525-567` | Verifier pins the 2026-10-25 decision, exact six operations, two window IDs, cap <=549 and total-new GPU reservation <=21600. A later continuation requires a versioned additive amendment/verifier, preservation tests and exact owner approval. Do not raise an old global constant to relabel historical approvals. |
| F03 | P1 | Ordinary launcher and qualified QA composition differ. `dr_support/app.py:144-151`, `scripts/qa/m1_server_app.py:280-305,325-342`; `m1_session.py:1-18` | Normal app factory supplies no `workspace_authority` or `workspace_prism_provider`. The QA runner builds DB fence, durable authority, status reader, provider negotiation, tunnel and trusted readback, and explicitly says it is not the installed service. Implement a bounded owned composition usable through the canonical launcher; do not restore raw PRISM routes. |
| F04 | P1 | M1 status remains cached after connection loss. `_factory.py:225-230,631-660,684-686`; `ReviewPage.tsx:431-445` | Frontend refreshes every 30 s/focus, but M1 backend returns startup descriptors with `connection_verified=True`, `capabilities_ready=True` and no live probe. Code explicitly returns `UNVERIFIED` for reachability. This is a backend composition gap despite the frontend refresh fix already on main. Recheck authenticated control-plane reachability safely; preserve token/endpoint identity and writer fencing. |
| F05 | P1 | Technical errors reach clinician UI; PRISM non-JSON failures are misclassified. `_factory.py:1014-1022`, `providers/remote.py:141-154`, `prism_remote_bound.py:48-60,212-237`, `frontend/src/lib/api.ts:944-957` | Four strict xfails reproduced: ConnectError, ReadError, timeout naming `REMOTE_MODEL_URL`, and HTML/non-JSON PRISM error not becoming TransportError. Parse JSON failure can escape the transport-uncertain classification. Plain wording must distinguish definite refusal from sent/unknown outcome; never say the remote did no work after an uncertain dispatch. Preserve quarantine and no resend. |
| F06 | P1 | AC-11 preservation test has weak initial state. Branch 2 `tests/test_m1_fault_injection.py:32-46,67-76` | `analyze()` snapshots a fresh fixture before adding an established grade, human annotations or confirmed review. Equality proves fresh/empty state preservation, not preservation of existing clinician work. Seed non-empty confirmed grade + ROI geometry/provenance/revisions and history before fault injection; compare persisted values afterward. This does not disprove production preservation; it limits the test's claim. |
| F07 | P1 | WIP AC-09 checker still falsely passes path leaks / malformed rows. Branch 2 `scripts/qa/check_export_folder.py:26-33,50-54,106-108` | On a valid synthetic fixture, manifest strings `/etc`, `/ผู้ป่วย/image.png`, `/患者/image.png` all return PASS. An extra CSV cell containing `C:/sample/image.png`, with the manifest CSV checksum updated, also returns PASS: DictReader puts surplus cells in a list under `None`, and the scan ignores non-string cells. Existing ASCII Windows/POSIX tests pass. Reject malformed row widths and complete decoded-value path detection; add counterexample tests. This is a checker defect, not proof the application exported such data. |
| F08 | P1 | Screenshot script trusts ten JPEGs without public hash verification. Branch 3 `scripts/docs/capture_manual_screenshots.py:65-76,174`; `dr_support/fetch_samples.py:22-31` | `--samples` accepts any directory containing exactly ten `*.jpg`, then copies them. Description says pinned HRF, but no filename/hash allowlist is enforced at capture. Reuse repository-pinned public sample identities, reject symlink/reparse/non-regular or changed files before copy/server launch, and keep all captures public/synthetic. Existing pictures are not proven private by this finding; their capture-time allowlist is unverified. |
| F09 | P2 | Branch 3 overstates integration and has a missing referenced checkpoint. Branch 3 `GOAL.md:287,484`; branch file list | AC-12 says watchdog detail is already in main, although its branch is unmerged. Update row mentions installation candidate without a corresponding new deliverable. GOAL references HANDOFF §36, but tracked HANDOFF ends at §35 and the branch does not modify it. Correct claims at the final integrated SHA; do not promote the OOM expected FAIL/UNVERIFIED to PASS. |
| F10 | P1 for full M1 | Guard-aware restore is still unqualified. `dr_support/persistence/recovery.py:137-160,961`; branch 2 gap analysis | Guarded source/target is deliberately refused. A rehearsal of a schema without the cross-schema entry guard is not production recovery evidence. Option B (restore isolated target, reinstall/qualify guard before opening app) is a proposal requiring a concrete recovery-contract decision; it must not be silently implemented or bypassed. It need not block a narrowly labelled API engineering candidate. |
| F11 | P2 | Candidate build identity does not match current HEAD. `frontend/dist/build-identity.json`; `build_release.py:260-274` | Bundle records `b96268c75a3af8e5342113bc7ee2634b4b138f81`; main is `9c52853`. There is no frontend diff between those commits (documentation successors), so this alone does not prove changed/stale UI behavior. The package builder nevertheless requires exact release commit identity. Rebuild on accepted main before packaging, and again after future UI fixes. |
| F12 | P2 | Grade controls and DR-ready labels need final UI proof. `GradeChoice.tsx:40-76`, `ClinicianReviewPage.tsx:243,304`, `DatasetsPage.tsx:85-88` | Six columns in a fixed 340 px panel plus narrow padding and a one-line `Ungradable` label give a concrete clipping risk. This audit did not reproduce it in browser. Dataset labels replace underscores instead of mapping clinical wording, so raw rule text remains. Use existing label helpers/tokens and browser checks at supported widths. Do not change grade or eligibility semantics. |
| F13 | P1 | Existing generic token-entry UI conflicts with the supplied server-only secret rule. `frontend/src/components/settings/ModelConnectionSettings.tsx:59,72,114` | A manually entered token is held in React `useState` and sent in a JSON request. The backend correctly omits the configured token from responses; this is not evidence that an existing server token was disclosed or persisted in browser storage. For the intended owned M1 deployment, configure/reuse credentials only in the backend and show operator-managed connection status. Explicitly reconcile the existing generic input with AGENTS' instruction before changing that security-facing contract; do not tell the user to paste a real token into React. |

### Other integration properties checked

- Browser requests are relative `/v1/...` calls to the same FastAPI origin. The browser does not call the GPU host directly. No new CORS allowance is needed for the packaged `/app/` path; do not expose a Model API bearer token in browser storage or a Vite variable.
- Intended normal review origin is `http://127.0.0.1:8000/app/`. The existing QA runner defaults to local app 8010, local tunnel 47860 -> remote loopback 7860, SSH identity `siripon@[DR host]` with the existing dedicated key. Keep those QA defaults distinct from normal workstation behavior.
- Ordinary global path: confirmed/admitted image -> deterministic analysis derivative -> capability/modality gate -> `/v1/infer/global` -> remote `/v1/predict/dr` -> schema/hash validation -> save result + append-only inference history -> clinician grade/annotation/completeness -> datasets/export. RETFound is CFP; USPEC is UWF. PRISM is lesion assistance (CFP and explicitly experimental UWF), never DR grading.
- Protected PRISM path: preview -> one-use receipt/frozen wire/mask/transform/source/model pins -> DB/source mutation fence -> execute -> authenticated grant/native-entry/terminal proof -> original-coordinate result validation/persistence. Legacy `/v1/infer/lesion-roi` is not a substitute for protected PRISM submission.
- Existing bounded host: one request in flight, upload 15 s, parent ACK 10 s, native request 30 s, PRISM job 24 s + grace, session 2640 s, hard child 2730 s. Existing PRISM channel uses prepare 10 s/connect 2 s and other calls 2 s. Timeouts have different purposes; do not increase all of them globally.
- Global remote inference timeout is 30 s, metadata 5 s; redirects are disabled. Explicit PRISM channel disables redirects and environment proxies. QA_LOCAL additionally rejects external endpoint/redirect and must never fall back to dr-train.
- PrivateGatewayAuth wraps the bounded child before requests reach admission. Generic legacy model metadata endpoints are not, by themselves, bearer authentication proof. A health 200 is not proof of loaded weights, real inference or persisted results. Metadata methods are control paths, not new inference authorization.
- The ledger fsyncs intent before dispatch, checks single-owner/head/hash-chain/window/budget identity, treats sent/uncertain work as consumed, and has no automatic inference retry. Worker lifetime reservations include load/idle, are charged in full and are not refunded on early stop. Unknown cleanup retains quarantine/ownership. Software custody does not claim protection against malicious whole-directory rollback.
- Existing inference-history idempotency is not a generic frontend retry guarantee. A new UI click can generate a new invocation/admission; duplicate/uncertain handling must be tested at the actual admission boundary, never by replaying terminal work.

## 4. Retained real evidence and accounting reconciliation

Read only selected accounting/status/result-summary fields under the private root, never `.env` files, credentials, images or clinical row bodies:

`C:/Users/User/AppData/Local/DRScreening/M1PrivateConfig/evidence/`.

| Evidence | Directly verified values |
|---|---|
| `ms03-service-20261025-01/COMPLETE.json` | SHA-256 `782730642d77cdd0bdec5b4f46ee1200720fe8ef8aab38b07864592127f7ba57`; six PASS_READBACK: RETFound 1, USPEC 2, PRISM 3; each readback says MODEL_COMPLETE, persistence PASS, accounting PASS; 0 retries; observed session 705.486 s; cleanup/listener/window/ledger close confirmed |
| Same service accounting | global used 540, lower bound 540, exact usage, cap 540, active admission false, poisoned false. The stop-state supervisor label is DRAINING; closure facts above are recorded independently. |
| `ms03-service-20261025-01/JOURNAL_HEAD.json` | SHA-256 `6519aaf402f73f48231fd9e1e5c4a1e380b16e065c1c318f319d0a4918d1b962`. Local receipt copy, not a fresh remote ledger replay. |
| `ms03-watchdog-20261025-01/WATCHDOG.json` | SHA-256 `8af98ab96f9b0d49f406f106e0b9c6b368183c3f927e9093769d6cc03be797a5`; 0 inference, observed 55.453 s, status FAIL, cleanup/window/ledger close confirmed, team unchanged. The original four cases passed; oom-contained expected result failed closed. Owner's historical safety acceptance does not change the test result. |
| Service `PROPOSAL.json` | SHA-256 `2ac0b6fa36ecb0931b7a56a851003c8eab09390c303d729487d74edee682666d`; base 534/cap 540/exactly six post-fix operations; watchdog 900 GPU/1800 wall seconds, service 3600 GPU/7200 wall seconds; no renewal/refund |

Reconciliation: historical overall request authorization 549 minus used 540 leaves nine **unspent operation slots**, reported as Local 6 + post-fix 3 in the original export. They are not a generic pool, active window or transferable Local allowance. The current service decision is 540/540. The accounting code explicitly says Local adoption is not qualified (`batch_ledger.py:893` and M1 accounting contract). A local browser/workstation using remote dr-train is **QA_SERVER**, not QA_LOCAL.

The original closed batch ledger was independently hash-pinned and replayed read-only with the repository verifier: 1423 rows, 476 intents, 480 terminal jobs (467 PASS_READBACK, 9 FAILED_NO_RETRY, 4 BLOCKED_PREMODEL), SHA-256 `ebc4f23ac5b9d89f136ada7a36b08350ddacf186e338a50c0ea5ba6f5ba14d98`. This validates that retained legacy anchor, not the inaccessible current remote service lineage. See `LEGACY_LEDGER_CHECK.json`.

GPU reservation accounting is consistent with 10800 (original Server) + 3600 (PRISM) + 900 (watchdog) + 3600 (service) = 18900 of the approved 21600 new seconds, leaving 2700 unreserved seconds. This is conservative lifetime reservation, not measured utilization. Preserved pre-M1 seconds are 17002.874, so the corresponding historical total is 35902.874. A fresh replay of the authoritative remote journal/BUDGET lineage is still required before any new decision can activate. No calendar expiry was found in the inspected service proposal; relative wall/monotonic limits and permanent closure still apply. Do not infer that an old window remains usable because no expiry date is listed.

## 5. Current host audit and access boundary

Read-only SSH as `[other account]@[DR host]` succeeded with strict existing known-host validation. At 2026-10-31T01:24:02Z:

| Index | UUID | Device | Observed use |
|---|---|---|---|
| 0 | `GPU-044a8b11-4729-458b-a07b-297e45439419` | RTX 2080 Ti 11 GiB | 1 MiB, 0%, no listed compute app |
| 1 | `GPU-277ccc57-c3e5-0731-cd49-f4f8695f7089` | Tesla V100 32 GiB | 0 MiB, 0%, no listed compute app |

This is a point-in-time observation, not permission or reservation. The V100 has a separately approved Patent-to-Pilot/[other team] allocation; DR may not reuse it. Historical DR work uses the RTX UUID, but no new DR authorization was assumed. Do not rely on numeric GPU index without matching UUID.

At 01:29:11Z, `ss` showed no listener on 7860, 7862 or 7864. No HTTP health/predict request was sent. Existing unrelated processes/listeners were neither contacted nor changed.

The `[other account]` account cannot traverse `/home/siripon/projects`; the repository's actual DR runner binds `/home/siripon/projects/dr-model-api-qa` and SSH user `siripon`, not `[other account]`. Consequently current remote DR deployment/version, asset pins, ledger chain/locks, BUDGET closure and service readiness were **not** inspected. No sudo, permission mutation, alternate-identity retry or key/secret read was attempted. The owner/implementation operator must confirm the intended existing DR SSH identity/access for that directory. Do not reconstruct a second DR deployment under [other account] merely to avoid this boundary.

## 6. Validation performed and limits

All new tests use the isolated overlay snapshot. The source repository and Claude worktrees are not test output destinations. Existing Python environment was reused; nothing installed. DB integration/entry-fence/permission-mutation opt-ins were disabled. Snapshot contains no local-state, `.env`, weights or dependency trees.

- Focused watchdog + export checker + AC-11: **50 passed, 4 strict xfailed**, 20.27 s. Xfails are ConnectError wording, ReadError wording, timeout admin setting, PRISM non-JSON transport classification. They are known defects, not four ordinary failed tests and not passes.
- Synthetic checker counterexamples: valid baseline PASS; single-component and Unicode absolute paths and a surplus CSV path cell incorrectly PASS; ordinary ASCII Windows/embedded POSIX path controls FAIL as expected. `CHECKER_PROBES.json` contains the exact reproducible results.
- Ruff for `dr_support tests`: PASS. Both lightweight root Node checks (overlay, API error parsing): PASS. They are not the full root npm suite.
- Documentation checker: PASS for154 Markdown/Quarto sources. This checker does not establish that the GOAL reference to HANDOFF§36 exists or that the prose claims are accurate; manual audit found F09 despite this pass.
- First full backend attempt stopped at collection because sandbox could not read existing `cv2/config.py`. No dependency was changed. The reviewed-access full run completed **2139 passed,68 skipped,4 xfailed,1 setup error**,533 warnings,364.69s, exit1. Error: `tests/test_m1_service_session.py::test_an_operation_keeping_its_old_window_is_refused`, in a synthetic fixture's `batch_ledger.py:677 os.replace(JOURNAL_HEAD.pending, JOURNAL_HEAD.json)`, Windows `PermissionError [WinError5]`. Do not call the full suite PASS. The failing fixture was retained. A separate fresh-fixture service-module diagnostic is recorded in `VALIDATION.json`; a diagnostic pass does not erase the original full-run error or establish its cause.
- Fresh-fixture diagnostic of the whole `tests/test_m1_service_session.py` module: **27 passed**,94.38s, exit0. No source edits, fixture cleanup or ACL changes between the full run and this diagnostic. The initial atomic-replace error remains unexplained; investigate during final branch validation if it recurs.
- Frontend Vitest/typecheck/build, root `ui.test.cjs`, actual browser, PostgreSQL readback, restart/reboot, installation extraction/launch, model setup/health/inference, guarded restore and hospital target: not newly run in this audit. Historical claims remain tied to their original receipts.

The user's earlier combined result (2138 passed, 68 skipped, four intentional failures) cannot be relabelled as current integration PASS. This audit verified that the four are strict xfails and tested an explicit captured WIP snapshot. Full required branch + integrated-main validation must be repeated after fixes; never add counts across runs or revisions.

## 7. Proposed bounded NEW decision (unapproved)

These are planning quantities, not approval or an exact operation manifest. Reconcile the live authoritative lineage first. Keep the nine old slots reserved under their original scopes; do not silently spend them on new UI tests. No paid external API is needed: real API here is the existing private HTTP Model API on the approved DR GPU.

### Minimum functional acceptance phase

Propose **12 new admissions**: four supported paths (RETFound CFP, USPEC UWF, PRISM CFP, PRISM UWF experimental) across three conditions: fresh, local review-app restart/reopen, and controlled tunnel reconnect **between** completed requests. Each waits for independent durable PostgreSQL readback before the next. Reconnect does not restart/reload the remote model child. Grade/ROI edit/save/reopen/export add no model calls. Test refusal/auth/timeout/HTML/uncertainty/duplicate behavior offline first.

One new window: **3600 GPU reservation seconds**, **7200 wall seconds**, one child/one lease/no renewal/no refund; retain the existing 2640 s runtime and 30 s request limits. Proposed increment to the old total request authorization: +12, making **561**. Because nine old slots remain reserved and used=540, a narrowly scoped new decision would authorize only **540 -> 552**, not all 21 unused overall slots. The verifier must express these distinct scopes explicitly.

GPU: 18900 + 3600 = **22500 new-reservation seconds**, requiring **+900** over the old approved cap21600. Including preserved17002.874, the aggregate would be **39502.874**. This is the minimum budget shape assuming an offline-qualified watchdog detail change is not rerun on GPU.

Rationale: the directly verified prior six-request service session took 705.486 s observed while reserving3600. Doubling that observed session is about1411 s, leaving headroom under2640 for load/interaction; this is a coarse planning check, not a model latency estimate or guarantee. The inspected summary lacks per-call timing fields. Prepare/confirm all public/synthetic cases and operation hashes before activating the GPU window.

### Recommended contingency, separately bounded

Optionally authorize a second fixed window (another3600 GPU/7200 wall seconds) with **8 new, predeclared verification admissions** for identified post-fix checks / final main candidate smoke, never blind retries of sent/uncertain jobs. Each operation, source hash, model pins and purpose must be fixed in the approved manifest. Stop unused operations if phase1 passes; no requirement to spend the allowance.

Combined recommendation: **+20 requests**, historical authorization cap **569**, new task decision at most **540 -> 560**, leaving the old nine scopes untouched; **7200** new GPU reservation, resulting total-new cap **26100** (**+4500** over21600), aggregate including historical preserved seconds **43102.874**. Maximum two windows, each no-renewal/no-refund. A failed/uncertain request still stops its window and preserves evidence; any later verification needs an explicitly different approved operation after reconciliation.

If a new real synthetic watchdog rerun is required, add a separate **900 GPU/1800 wall seconds**, **0 model admissions** before functional windows. That changes the recommended total-new cap to **27000** (+5400 over21600), aggregate **44002.874**. It must be part of the same concrete owner decision, not a hidden warmup.

These finite windows establish engineering acceptance and an explicitly timed local API session. They do **not** authorize an indefinite always-on service, idle GPU residency beyond the window, arbitrary future users/images, or QA_LOCAL GPU installation. If the desired deliverable is daily persistent service, the owner must specify the usable service period / stop behavior and ongoing quota policy; the current frozen one-lease/no-renewal design cannot honestly be called persistent by adding a launch button.

## 8. Minimum decisions before the final Claude goal

1. Confirm intended deliverable: normal Windows launcher with real **QA_SERVER** API over the existing private SSH route, including a finite service period; explicitly distinguish this from full Hospital M1 and offline QA_LOCAL acceptance.
2. Select minimum12 / recommended20 new admissions and whether the0-request watchdog rerun is included, with exact cumulative caps/windows above. Approve the new additive accounting contract and exact proposal hash after the live lineage is reconciled; a drafted proposal is not approval.
3. Authorize the exact RTX UUID for this new DR window, concurrency1 and owned resource limits, scheduled around the separate [other team] V100 allocation. Existing limits/providers/checkpoints stay pinned. No use of other people's GPU/process/ports, system Python, driver, Docker volumes or firewall changes.
4. Confirm correct existing DR SSH account/path and existing backend-only token usage. No credential creation/rotation or token printing. A helper opt-in flag is not proof of owner authorization. Reuse prior explicit authorization if the full conversation establishes it; do not ask it again unnecessarily.
5. Include bounded AC-11 readiness/error-classification and two presentation fixes in the intended implementation scope while keeping API/model/admission/clinical semantics intact. Guard-aware recovery/mask/hospital-data decisions remain separately named if the owner also wants full M1 closure.

No new permission is needed merely to finish existing branch review fixes, strengthen offline tests, correct branch-status documentation, or prepare an isolated synthetic installation candidate within the already authorized scope. The audit itself grants no implementation instruction.

## 9. Claude work that can progress offline while awaiting live decisions

Finish checker path/row tests and AC-11 seeded clinical-state tests; fix/review snapshot allowlisting and GOAL claims/HANDOFF§36; add M1 readiness/fault/unknown-outcome regression coverage; design the smallest canonical-launcher composition against frozen contracts without launching a GPU; draft exact new continuation/amendment and operation matrix; complete second review and branch/main validation lifecycle when authorized; rebuild main frontend and create secret-free candidate manifest/checksums/rollback instructions. Preserve each dirty worktree and existing owner artifacts. Do not merge on the strength of unit tests alone.

Candidate contents must bind source/release SHA, frontend source/output identity, dependency inventory, software checksums, provider/source/preprocessing identities, safe templates, known limits and exact start/status/stop steps. Weights, real images, runtime DB/catalog, ledgers and secrets remain outside the software archive. Model package helpers currently return BLOCKED/NOT_RUN by design; ordinary extraction smoke does not prove real inference. Rollback selects a compatible application build while preserving clinician data; overwriting/restoring an old database is a different destructive action.

Final acceptance evidence must follow an actual browser click through HTTP admission, real model invocation and durable DB readback, clinician edit/save, reopen/restart and export on the **main build**. Record implemented / tested offline / tested actual API / not run / blocked separately, with exact SHAs and per-model/modality proof. TEST_ONLY engineering labels never become physician gold/training-ready data. No clinical accuracy, calibration or medical release claim follows from these checks.

## 10. Remaining action blockers

| Action / target | Reason | Outcome / next actor |
|---|---|---|
| Read current remote DR deployment/ledger under `/home/siripon/projects/dr-model-api-qa` as [other account] | Parent directory not traversable by this account | **Not executed** beyond metadata check; correct existing DR operator identity/access must be confirmed. No bypass attempted. |
| Start new DR service/window or inference | Audit-only scope; no new numeric/device/window approval; old service ledger exhausted | **Not attempted**; owner decision + verified lineage/new contract required. |
| Claim current full integration / installation / full M1 complete | Unmerged WIP, known xfails/gaps, no current live acceptance or guarded recovery | **Not claimed**; Claude finishes bounded implementation and required lifecycle, with narrower honest status where full target evidence is absent. |

No automatic approval-review rejection occurred. The sandbox read limitation for existing cv2 was addressed by a reviewed-access offline test run; no ACL or dependency workaround was used.
