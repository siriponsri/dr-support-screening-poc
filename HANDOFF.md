The full engineering history (old sections 1 to 41, receipts, plans) is in Git tag `archive/docs-before-cut-20261101`.

# HANDOFF: current engineering checkpoint

Checkpoint: 1 November 2026. All work so far is TEST_ONLY and single-user commissioning. Not a clinical
service, not a final release, not accepted by a hospital.

## 1. Current main

- `main` at `158169d` (6 November 2026), synchronized with `origin/main`. Merges since phase 1 finish:
  - `110b47e` phase 1 finish (referrals, personal tokens, Thai on every page, security audit fixes);
  - `08074bb` easy setup: the demo launcher asks once on first start (type YES that the workspace holds only
    public or consented images; reversible on the Admin page); `SETUP_WEB_APP.bat` sets up package 1;
  - `5b9b1fb` install kits: `deployment/hospital-server/install.sh` + `IT_CHECKLIST.md` + offline bundle,
    `deployment/cloudflare-access/` (team demo, invited emails only, tunnel to `127.0.0.1:8010`, demo images only);
  - `e357f81` docs cut (old docs in tag `archive/docs-before-cut-20261101`; owner's untracked old files moved
    to the ignored `.archives/` folder);
  - `be72dd0` one presentation: `presentation/index.html` (reveal.js + GSAP, offline), opened by `PRESENT.cmd`;
  - `5acf01d` code tidy (behaviour unchanged): `workflow.py` route groups in `dr_support/workflow_routes/`,
    `api/_factory.py` split into `model_connection.py`, `inference.py`, `batches.py`; dataset export split;
    frontend helpers extracted (`useAnnotationDraft`, `apiTypes/apiClient/apiLabels`); legacy `web/` and `/ui`
    removed; historical QA tools removed; `scripts/qa/m1_server_app.py` is now `scripts/demo/server_app.py`;
    owner defaults removed from public scripts (the private `demo.env` sets `DR_HOST`/`DR_KEY`);
  - `8c81082` narrated Thai user-journey video (`frontend/public/media/journey-th.mp4` + `.vtt`, built from
    `media/journey-video/`, Gemini `gemini-3.8-flash-tts` voice Achernar) and the "ดูวิธีใช้งาน" pop-up on the sign-in page;
  - `158169d` three Thai PDFs in `docs/pdfs/` (user manual with screenshots, deployment guide, test report),
    built by `scripts/docs/build_pdfs.py` from `docs/th/`.
- Validation on main after these merges: backend 2,192 passed, 71 skipped, 0 failed (lower than before because
  removed tools took their tests); frontend 45 files, 342 tests passed; typecheck 0; Ruff clean; root API smoke
  PASS; docs QA passed; `frontend/dist` rebuilt. Some frontend tests are timing-flaky under load (pass alone).
- The one-click demo was not run live after the code tidy (the first start asks the owner to type YES).

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
- Thai wording for a physician to check: GradeGuide ICO criteria, the Yes/No answers on the report form, and
  the three Thai PDFs.
- Listen to the narrated video once (3 scenes had spoken style notes trimmed: Confirm Image, Annotation
  Editor, Screening report). The free Gemini key allows 10 TTS requests a day; a full regeneration needs 9.
- The `full` demo profile merges routes without the sign-in middleware (audit item 8); the video and PDF
  capture used `review` instead.
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
   .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider     # about 10 to 14 minutes; about 71 skips are normal
   .\.venv\Scripts\python.exe -m ruff check dr_support tests
   cd frontend; npm.cmd test; npm.cmd run typecheck; npm.cmd run build; cd ..
   npm.cmd test                                                     # root API smoke test (synthetic case)
   .\.venv\Scripts\python.exe scripts\docs\check_docs.py
   git diff --check
   ```
5. GPU or live AI work: inside AI hours, GPU0 only, public or consented images only, report to the owner
   before anything that changes the authority config or creates accounts.
6. Next planned steps: the three Thai PDFs (`docs/pdfs/DEPLOYMENT_GUIDE_TH.pdf`, `TEST_REPORT_TH.pdf`,
   `USER_MANUAL_TH.pdf`; the screenshot tool is `scripts/docs/capture_manual_screenshots.py`), then switch
   `REQUIRE_PDFS` on in `scripts/docs/check_docs.py`; a code-tidy pass may remove historical M1 scripts and
   their tests.
