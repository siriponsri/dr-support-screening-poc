The full engineering history (old sections 1 to 41, receipts, plans) is in Git tag `archive/docs-before-cut-20261101`.

# HANDOFF: current engineering checkpoint

Checkpoint: 1 November 2026. All work so far is TEST_ONLY and single-user commissioning. Not a clinical
service, not a final release, not accepted by a hospital.

## 1. Current main

- `main` at `08074bb` (merge of `feat/easy-setup`), synchronized with `origin/main` before the documentation
  cut. Recent merges:
  - `110b47e` phase 1 finish (referrals, personal tokens, Thai on every page, security audit fixes,
    `docs/ARCHITECTURE.md`);
  - `c732b57` owner confirmed consent for audit items 18 and 35;
  - `69ec036` easy setup: the demo launcher asks once on first start (type YES that the workspace holds
    only public or consented images; recorded as the server-mode confirmation, shown and reversible on the
    Admin page) and `SETUP_WEB_APP.bat` sets up package 1 on Docker Desktop in one double-click.
- Documentation cut (branch `docs/cut-down`): docs reduced to `README.md`, `docs/README.md`,
  `docs/ARCHITECTURE.md`, `docs/developer/*.md`, this file and `GOAL.md`. Three Thai PDFs (deployment
  guide, test report, user manual) come in a later step. A new presentation is built separately in a root
  `presentation/` folder.
- Last full validation before the cut (phase 1 finish branch tip, same tree as `110b47e`): backend 2,335
  passed, 69 skipped, 0 failed; frontend 44 files, 340 tests passed on main; typecheck 0; Ruff clean.
  Frontend full runs have timing-flaky slow tests (they pass alone); recorded, not loosened.
- Documentation cut validation (branch `docs/cut-down`): backend 2,338 passed, 69 skipped, 0 failed;
  Ruff clean; root smoke PASS (11 cases); docs QA passed. No frontend source changed.

## 2. What phase 1 delivered (all merged on main)

| Area | What |
| --- | --- |
| Regular shared Model API | CPU gateway on dr-train with a daily authority (calls, GPU-seconds, AI hours, tickets, audit chain) that starts the GPU child on demand; two-stage AI batch in the Worklist |
| Sign-in and admin | two-panel sign-in, Today start page, Admin page (accounts, sign-in policy, read-only database view, AI-server choice with consent gate, Test connection) |
| Roles and language | physician, nurse, expert, researcher, admin; EN/TH switch; Thai body text on every page (headings and technical terms stay English) |
| PRISM UWF mask | mask A2 `uwf_rubber_rim_colour_a2_v1` (bright and dim rubber rim) in `imaging/uwf_rubber_rim_mask.py`; owner approved after private visual sheets |
| Screening report | grader chooses Refer or Not refer, nurse prepares, physician signs, print saves PDF |
| Referrals | signed Refer or ungradable reports only, FHIR R4 and CSV export, connector off by default (file drop or HTTPS webhook set by the administrator), one recorded attempt per Send |
| Gold-100 and export | expert grades blind, AI revealed afterwards; AI-predicted archive folders kept apart from confirmed grade folders |
| Packages | one-click desktop demo "DR Screening Demo"; Docker package 1 `deployment/webapp` (built and exercised on Docker Desktop); package 2 `deployment/hospital-server` (compose validated only) |
| Personal access | per-person tokens on the gateway, restricted SSH account script, launcher reads `DR_HOST`, `DR_KEY`, `DR_TOKEN_FILE` |
| Security audit | 31 October 2026 audit, fixes merged; open items in `docs/developer/SECURITY.md` |

## 3. dr-train state

- Gateway runs from deployment `regular-20261031-r05`, CPU only, on the same daily authority `regular/r01`
  (never reset). Identity equals r04 (global and PRISM pins), so the r04 pins
  (`regular/r04-inputs/PRISM_WORKSPACE_PINS.json`) stay in use. pid file `regular/r05-service.pid`.
- Rollback: stop r05 and start r04 (command in `docs/developer/MODEL_SERVER_OPERATIONS.md`). Older
  deployment folders r01 to r04, their pins and logs are kept.
- No principals file exists, so only the owner's shared token works. No personal account, token or device
  has been created.
- The owner's private `demo.env` names r05. Live AI was not rerun after the r05 switch (outside AI hours).
- GPU0 only. Never GPU1, Ollama, V100, Podi or other teams' work. Daily limits: 1,500 calls, 43,200
  GPU-seconds, AI hours 06:00 to 22:00 Thai time. The owner allows extending the budget during development,
  but a change of the authority config needs a new authority record (new state folder; old one kept).
- The project account cannot run Docker on dr-train (not in the `docker` group; not changed).

## 4. Standing owner rules

- Only public or consented images go to dr-train. Real hospital use runs on the hospital package.
- No secrets, PHI, model weights, runtime databases or `local-state/` in Git, logs, chat or the browser.
  Owner's private files live outside Git (`.archives/` is ignored).
- No middle dot or em dash in UI text (use "/", ":" or a short "-"); Worklist status names and table
  content stay English; no university or faculty name in the UI.
- Claude may not create accounts or change system security settings (ACLs, firewall, groups, credentials).
- Marking a workspace as consented is the owner's decision; Claude never marks consent.
- Human grade and annotations are authoritative; no automatic referral rule without a signed clinical
  definition; empty AI output is not "no lesions"; scores are not calibrated probabilities.
- Model identities and pins are provenance; changing them needs the owner.
- Follow `AGENTS.md`: bounded branch and worktree, never write on `main`, merge gate, rebuild
  `frontend/dist` on main after frontend changes.

## 5. Open owner decisions

- Demo workspace AI-server choice and consent: the launcher now asks on first start; whether the owner has
  answered is not recorded here.
- Personal access: the dr-train administrator runs `create-restricted-user.sh` per person, the operator
  issues tokens, the owner invites devices. Nothing created yet.
- Audit open items: Model API without a token (4), public-folder demo mode (5), Host check (7), `full`
  profile sign-in (8), plain-text patient fields and backups (11), plain http between hosts (14), login rate
  limit (15), root containers and database superuser (16, 17), cookie `Secure` flag (21), hardening items
  (29 to 31, 33), owner names in examples (34), signing with sign-in off (37), PRISM job binding (12 part).
- Thai wording for a physician to check: GradeGuide ICO criteria and the Yes/No answers on the report form.
- PRISM on the legacy public samples is refused before model work (no recorded source projection for that
  workspace); needs a projection approval for the workspace or another approved public PRISM path.
- The Model API model-boundary colour check refuses some public UWF images; changing it is a frozen Model
  API decision.

## 6. Known limits

- Package 2 has not run on a hospital GPU server.
- Multi-user is not commissioned: local sign-in exists, but the Model API still uses only the shared token
  until personal tokens are issued.
- Batch PRISM on images with quality NOT_EVALUATED is refused by the host (needs GRADABLE) while the app
  still offers it.
- Mask A2 is conservative: some images keep a little dim rim; boxes on eyelids and lashes remain (outside
  the phase 1 goal).
- Opening the app warms the GPU child (one segment per start). A queued batch item holds the app's
  inference lock for at most the 300 s queue wait.
- Installation candidate `0.8.0-m1-regular.rc1` was built and extraction-tested; not a final release.
- Automatic referral suggestions, vessel segmentation and training are phase 2 (see `GOAL.md`).

## 7. How to resume

1. Read `AGENTS.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, this file and `GOAL.md`. Reading is not
   authorization to run GPU work or change dr-train.
2. Write gate: report repository root, worktree path, branch, HEAD and `git status --short --branch`. If on
   `main`, stop and create a `feat/`, `fix/` or `docs/` worktree from clean, synchronized main.
3. Several old worktrees exist (`git worktree list`); leave them for the owner. Never reset, clean, stash or
   discard unexpected work.
4. Validate before handoff:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider     # about 10 to 14 minutes; 69 skips are normal
   .\.venv\Scripts\python.exe -m ruff check dr_support tests
   cd frontend; npm.cmd test; npm.cmd run typecheck; npm.cmd run build; cd ..
   npm.cmd test                                                     # needs python -m dr_support.fetch_samples first
   .\.venv\Scripts\python.exe scripts\docs\check_docs.py
   git diff --check
   ```
5. GPU or live AI work: inside AI hours, GPU0 only, public or consented images only, report to the owner
   before anything that changes the authority config or creates accounts.
6. Next planned steps: the three Thai PDFs (`docs/pdfs/DEPLOYMENT_GUIDE_TH.pdf`, `TEST_REPORT_TH.pdf`,
   `USER_MANUAL_TH.pdf`; the screenshot tool is `scripts/docs/capture_manual_screenshots.py`), then switch
   `REQUIRE_PDFS` on in `scripts/docs/check_docs.py`; a code-tidy pass may remove historical M1 scripts and
   their tests.
