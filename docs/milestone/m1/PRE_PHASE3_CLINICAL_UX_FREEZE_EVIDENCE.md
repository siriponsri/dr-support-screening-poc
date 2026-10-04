# P3-0 Clinical UX & Design System Freeze Evidence

**Status:** `COMPLETE / OWNER_ACCEPTED` — deterministic browser and synthetic 10-case runtime gates are recorded below; Owner UAT passed and the UX freeze is accepted. The pre-UAT receipt remains historical evidence.
**Baseline:** `f288ae5e8a527f124aaa99eedc6f3d6f7a3e32cb`
**Candidate:** `8ba18ebfb68021136315a3ff4b128c56fdbce3b8` (`feat/pre-phase3-clinical-ux-freeze`); exact implementation candidate reviewed before integration
**Integrated P3-0:** `580bd9a2112dd8b552a361f9fadde4d6e16fb13c`
**Documentation evidence closeout:** `dc281a7821fd11c8b6da0f0aa48cc4cc534d1c97`
**Pre-closeout main state:** `1440bd5dd696d81ec1cf5859dfc77b6c5d08f9d4` (clean and synchronized `main` / `origin/main`)
**Owner UAT:** `PASS` on 2026-10-04; owner accepted the P3-0 workflow and UX freeze
**Freeze acceptance:** `COMPLETE / OWNER_ACCEPTED`
**Phase 1:** `DONE`
**Phase 2:** `DONE`
**Phase 3:** `NOT_STARTED`
**Scope:** frontend Annotation Editor convergence, design-token naming, focused regression coverage, and bounded documentation evidence

This record accompanies `PRE_PHASE3_CLINICAL_UX_DESIGN_FREEZE.md`. It records what was inspected and verified for the P3-0 candidate. It does not qualify a model, approve clinical deployment, authorize hospital data, or start Phase 3.

The live checks used synthetic cases only through the local workstation at `http://127.0.0.1:8124/app/`, with `APP_PROFILE=full`, `MODEL_RUNTIME=local`, CPU execution, and system Chrome launched through the existing root `playwright` package. Raw screenshots and JSON results remain outside Git at `C:\Users\User\Desktop\myProject\p3-0-browser-audit-20261003`.

## Reference study

The study was bounded to interaction patterns relevant to retinal labeling. It used the current Workbench source/manuals and established public workflow patterns; it did not copy branding or artwork.

| Pattern | Current Workbench | Reference pattern | Decision | Reason |
|---|---|---|---|---|
| Image-first annotation | Retinal image and overlays are the main editor surface | MONAI Label / OHIF task-centered viewer | Keep | Clinician judgment stays next to the image |
| Contextual geometry tools | Box, Polygon, Point, and Circle were previously expanded in the normal flow | CVAT / 3D Slicer progressive tool organization | Adapt | Keep Box primary and disclose low-frequency tools through More tools |
| Sample progression | Finish advances to the next incomplete case | MONAI Label task progression | Keep | Reduces manual Worklist navigation while preserving explicit confirmation |
| AI assistance | AI ROI actions remain optional and preserve original evidence | Viewer/server separation in OHIF-style workflows | Keep | Model evidence remains secondary to human decisions |
| Dense technical controls | Technical persistence/completeness language was visible in the editor | 3D Slicer/CVAT advanced tool separation | Reject for routine flow | Keep implementation state in audit/details surfaces |
| External branding | Existing Workbench has its own clinical shell and token system | Reference products have distinct product identities | Reject | Do not clone another product or imply model qualification |

## User-effort evidence

The before/after values below are source-level interaction proxies, not clinician time-study results. A continuous 10-case workflow requires an authorized running workstation and synthetic/public case set.

| Measure | Baseline source observation | Candidate source observation | Status |
|---|---|---|---|
| Toolbar vertical bands | Separate tool, history, and class/visibility rows | One compact wrapping control band | RUNTIME_PASS across required viewports |
| Secondary geometry disclosure | Collapse-expanded controls in the routine editor | Adjacent More tools popover with three secondary tools | PASS, 16 focused tests plus live keyboard audit |
| Technical state decisions | Record partial review exposed in Advanced disclosure | No normal-flow control for internal partial state | PASS; no such control appeared in runtime audit |
| Completion guidance | Completion panel plus page-level next-action hint | Compact Review complete panel and CTA only on the editor | PASS in focused tests and completed runtime state |
| Manual reviewer entry | Remembered reviewer support already existed | Compact reviewer summary remains unchanged | RUNTIME_MEASURED in the synthetic continuation |
| Clicks per routine case | No live pre-candidate baseline was collected | 6.25 logical clicks/case in the instrumented cases 3–10 continuation; includes the one-time default-reviewer checkbox | RUNTIME_MEASURED; source baseline unavailable |
| Manual fields per case | No live pre-candidate baseline was collected | 1.125 reviewer/image-type entry events per case in the same continuation; patient/eye remained Unknown where unsupported | RUNTIME_MEASURED; source baseline unavailable |
| Route transitions | No live pre-candidate baseline was collected | 4 transitions/case in the instrumented continuation | RUNTIME_MEASURED; source baseline unavailable |
| Scroll friction | No live pre-candidate baseline was collected | 1 deliberate scroll to the completion panel per instrumented case; no horizontal overflow | RUNTIME_MEASURED; source baseline unavailable |

## Annotation Editor acceptance

- **One-row toolbar:** RUNTIME_PASS at 1920x1080, 1440x900, 1366x768, and 1280x720 with a compact wrapping control band; deliberate wrapping measured at 1024px and mobile widths. No horizontal overflow was observed.
- **More tools:** PASS in 16 focused tests and live keyboard audit. Enter opened the popover, Polygon was available, Escape closed it, and focus returned to More tools. See `p3-0-playwright-results.json` and `p3-0-annotation-viewports.json` in the external evidence directory.
- **Contextual help:** PASS in the 16 focused tests and source/runtime audit; Select, Box, Polygon, Point, and Circle guidance remained available without exposing internal state terminology.
- **Inline active tool:** PASS in the focused tests and runtime audit; the editor exposed `Active tool: Select` and concise drawing guidance.
- **Record partial review:** PASS; absent from the normal clinician UI and from all inspected runtime annotation pages.
- **Advanced default:** PASS; `Advanced findings (optional)` remained collapsed and untouched in the inspected runtime pages.
- **Completion panel:** PASS; completed cases showed `Review complete`, `Open next image`, and explicit editing, with no duplicate next-step hint.
- **Duplicate guidance:** PASS; the annotation page did not render the generic page-level next-action hint beside the completion CTA.
- **Image dominance:** PASS; at 1440px the retinal image measured 733x550px and at 1280px 606x455px, remaining the dominant editor object. Mobile remained single-column without horizontal overflow.

## Design and clinical UX

- Brand tokens are named `brand.universityAccent` and `brand.medicinePrimary` as project tokens. No exact official KKU or Faculty of Medicine value is claimed because authoritative current brand verification was not performed in this pass.
- Clinical status colors remain separate from brand colors.
- Retinal lesion colors remain local to the viewer and unchanged.
- Thai/English resilience is preserved through existing system-font fallback and unconstrained reviewer input. A live Thai-label browser pass is `NOT_RUN`.
- Human authority, three confirmation milestones, completeness mapping, Advanced deferral, AI/Human provenance, original-image coordinates, immutable source behavior, and PostgreSQL authority were not changed.

## Validation receipt

| Check | Result | Evidence |
|---|---|---|
| Focused Annotation Editor tests | PASS, 16 tests in MAIN local run | `npm.cmd test -- --run tests/annotationEditor.test.tsx` |
| Frontend typecheck | PASS | `npm.cmd run typecheck` |
| Full frontend test suite | PASS WITH ONE UNRELATED BASELINE TIMEOUT, 123/124 | `npm.cmd test`; the timeout is the pre-existing `tests/uwfIntake.test.tsx` jsdom `window.scrollTo` behavior |
| Frontend build | PASS | `npm.cmd run build`; existing large-chunk warning only |
| Backend/Ruff | NOT_RUN; no backend files changed | Not required for source-only frontend iteration; report final decision |
| Documentation QA | PASS | `python scripts/docs/check_docs.py`; 90 Markdown/Quarto sources |
| Root smoke | NOT_RUN | Historical legacy root-smoke limitation remains; the feature-worktree `.venv` was unavailable in the final source-audit environment |
| `git diff --check` | PASS | Final integrated repository check |
| Playwright viewport audit | PASS | System Chrome via existing `playwright`; Worklist and Annotation Editor screenshots/metrics at 1920x1080, 1440x900, 1366x768, 1280x720, 1024x768, and 390x844; no horizontal overflow |
| Stagehand exploratory audit | NOT_RUN | Optional package is not installed; deterministic Playwright evidence was used and Stagehand is not a substitute for it |
| 10-case continuous audit | PASS, synthetic/manual-only | P3CASE01_L1 through P3CASE10_L1 completed; Worklist reported every image complete. Raw continuation receipt is `p3-0-ten-case-continuation.json` outside Git |

## Known limitations

- The feature-worktree `.venv` was unavailable in the final source-audit environment, and a PostgreSQL DSN was unavailable for the final audit run; no PostgreSQL persistence/restart or CAS qualification is claimed here.
- The browser audit used system Chrome and synthetic local SQLite runtime state only. Screenshots are recorded outside Git; no hospital data was used.
- Official institutional brand values were not verified; project token names are intentionally non-official.
- Reviewer account independence remained unverified; the configured review account was not independently established from MAIN.
- Thai-label live browser coverage was not run; source-level font fallback and unconstrained reviewer input were inspected.
- Historical Phase 2 legacy root-smoke limitations and deferred live Model API success remain historical/phase-boundary evidence and are not converted into P3-0 PASS claims. Live Model API success remains deferred to Phase 3.
- A narrow mobile header title wraps/truncates into a compact form while remaining usable and overflow-free; this is NON-BLOCKING / DEFERRED for pre-Phase-3 UX follow-up, not a Phase 2 regression.

## Review and self-audit

- MAIN self-audit: BOUNDED SOURCE, keyboard, responsive, manual-only UWF, completion, and synthetic 10-case checks reviewed. No frozen clinical, persistence, provenance, geometry, model, or phase-boundary contract was changed.
- Browser self-audit: PASS for the required deterministic viewport and interaction checks; the one narrow mobile title-wrap observation is NON-BLOCKING / DEFERRED and does not prevent Owner UAT readiness.
- User-effort self-audit: the instrumented cases 3–10 completed through the next-case path with no manual patient/eye invention, no technical `Record partial review` control, and no need to enter Advanced findings.
- Independent review: configured O1 exact-candidate review found no source-level blockers; reviewer-account independence remains unverified and is reported as a limitation.
- Fresh configured O1 review of the first candidate: REQUIRED FIX findings included fullscreen popover DOM/focus/viewport behavior, completed reviewed-none copy, and stale readiness evidence.
- Follow-up bounded repair: fullscreen entry now closes any inline More tools popup before the Modal opens; outside-pointer close restores the stable trigger; Advanced copy is truthful. Focused MAIN tests pass 16/16; owner UAT remains open.
- Fresh configured O1 changed-diff review of candidate `e9436ba`: REQUIRED FIX findings covered focus classification for the viewer, Advanced wording, and exact-SHA evidence.
- Follow-up repair commit `2413b00`: viewer clicks now restore the More tools trigger, Advanced is explicitly optional/deferred, and the focused regression covers viewer dismissal; focused MAIN tests remain 16/16.
- Fresh exact-candidate O1 re-review of `f05ab3f`: REQUIRED FIX findings identified stale candidate wording and trailing whitespace in the base-to-candidate documentation diff; no approval is claimed for that revision.
- Follow-up documentation repair for exact candidate `8ba18eb`: the normative spec's trailing whitespace is removed; the historical `f05ab3f` and `d3a0031f` review findings remain preserved. This documentation-only correction is included in the final pre-integration review.

## Runtime UAT boundary

The deterministic runtime gate is `PASS` for the required Playwright viewport and interaction checks, and the synthetic 10-case gate is `PASS`. Stagehand remains `NOT_RUN` because it is optional and not installed. This paragraph records the historical pre-owner-UAT `READY_FOR_OWNER_UAT` boundary; it is not a freeze acceptance, production/clinical approval, hospital-data authorization, native UWF model qualification, or Phase 3 start.

## Owner UAT boundary

This candidate stopped before Phase 3. The historical owner-UAT handoff was `READY` / pending owner action. The owner could inspect the normal synthetic/public workflow, toolbar/popover, reviewed-none completion, and target workstation resolutions. Phase 3 remains `NOT_STARTED`.

## Owner-UAT handoff

- **Synthetic workflow:** 10 cases completed with UWF confirmed, patient/eye left Unknown where unsupported, AI unavailable/manual-only messaging preserved, DR grade confirmed, reviewed-none Core completion recorded, and no Advanced entry.
- **Required limitations:** feature-worktree `.venv` unavailable in the final source audit; PostgreSQL DSN unavailable; 1920px was checked with system Chrome but was not an owner-workstation qualification; reviewer account independence unverified; historical legacy root-smoke limitation preserved; live Model API success deferred to Phase 3.
- **Deferred Pre-Phase-3 UX:** compress the Annotation Editor toolbar toward one-row operation and move low-frequency tools to compact progressive disclosure where practical; preserve the Owner-UAT observation that future completeness UX should derive internal state from clinical actions and must not expose backend terminology such as `Record partial review`. These are non-blocking follow-ups and were not implemented in this closeout.

**Historical pre-UAT marker:** `PRE-PHASE 3 CLINICAL UX FREEZE READY_FOR_OWNER_UAT`

## Formal owner UAT and freeze closeout (2026-10-04)

Owner UAT result: `PASS`. The owner verified the intended P3-0 workflow and UX:

- compact Annotation Editor toolbar;
- More tools progressive disclosure/popover;
- no normal-flow `Record partial review` control;
- optional, untouched Advanced findings behavior;
- compact completion and next-image flow;
- retinal image remains visually dominant; and
- the normal multi-case workflow is understandable and usable.

The accepted P3-0 freeze carries these contracts into Phase 3:

- **One-primary-action rule:** each routine state exposes one dominant next action, including compact completion and next-image guidance.
- **Image-first hierarchy:** the retinal image and its clinician-relevant overlays remain the primary object; supporting controls stay compact.
- **Annotation controls:** Box remains the primary tool; the Annotation toolbar stays compact and low-frequency geometry uses progressive disclosure through More tools.
- **Hidden implementation state:** backend completeness/state-management terminology, including `Record partial review`, stays out of the normal clinician flow; persisted semantics and audit evidence remain intact.
- **Advanced behavior:** Advanced findings remain optional; an unopened Advanced group remains `NOT_REVIEWED` and does not block Core completion.
- **Reviewer treatment:** remembered reviewer identity remains compact and convenient without being treated as authentication.
- **Color separation:** brand colors, clinical status colors, and retinal lesion/provenance colors remain separate and are not interchangeable.
- **Responsive and accessible baseline:** supported layouts remain overflow-free and readable; keyboard access, visible focus, adequate targets, text/non-color cues, and progressive disclosure remain required.
- **Manual AI-off workflow:** image confirmation, grading, findings, completion, and next-case progression remain usable without model integration or a live Model API.

Known limitations remain accepted and explicitly bounded:

- the feature-worktree `.venv` was unavailable in the final audit environment;
- PostgreSQL DSN/server access was unavailable for the final audit run, so no PostgreSQL persistence/restart or CAS qualification is claimed here;
- the 1920px audit used system Chrome and was not an owner-workstation qualification;
- reviewer account independence remained unverified;
- the historical legacy root-smoke limitation remains historical evidence, not a fabricated PASS;
- live Model API success remains deferred to Phase 3;
- Thai-label live browser coverage was not run; and
- the narrow mobile header title wrap/truncation remains non-blocking deferred UX follow-up.

The earlier Phase 2 deferred observations remain preserved as non-blocking/deferred history. P3-0 owner UAT verifies the resulting compact toolbar and More tools disclosure; future completeness copy should still derive internal state from clinical actions rather than expose backend terminology. No deferred UX change is authorized by this closeout.

This closeout does not authorize model integration, MONAI adoption, Clef integration, hospital-data use, production/clinical deployment, Phase 3 start, or Phase 4 changes. Phase 3 remains `NOT_STARTED`.

**Final closeout marker:** `P3-0 CLOSED — READY FOR PHASE 3 RECONCILIATION`
