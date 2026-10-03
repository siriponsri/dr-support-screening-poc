# P3-0 Clinical UX & Design System Freeze Evidence

**Status:** `OPEN / NOT_RUN / NOT_READY_FOR_OWNER_UAT` — the exact candidate still has unrun runtime gates; no owner-UAT readiness or freeze acceptance is claimed.
**Baseline:** `f288ae5e8a527f124aaa99eedc6f3d6f7a3e32cb`
**Candidate:** `8ba18ebfb68021136315a3ff4b128c56fdbce3b8` (`feat/pre-phase3-clinical-ux-freeze`); exact implementation candidate reviewed before integration
**Phase 1:** `DONE`
**Phase 2:** `DONE`
**Phase 3:** `NOT_STARTED`
**Scope:** frontend Annotation Editor convergence, design-token naming, focused regression coverage, and bounded documentation evidence

This record accompanies `PRE_PHASE3_CLINICAL_UX_DESIGN_FREEZE.md`. It records what was inspected and verified for the P3-0 candidate. It does not qualify a model, approve clinical deployment, authorize hospital data, or start Phase 3.

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
| Toolbar vertical bands | Separate tool, history, and class/visibility rows | One compact wrapping control band | SOURCE_REVIEWED; runtime visual gate OPEN / NOT_RUN |
| Secondary geometry disclosure | Collapse-expanded controls in the routine editor | Adjacent More tools popover with three secondary tools | PASS, 16 focused tests; browser/runtime UAT OPEN / NOT_RUN |
| Technical state decisions | Record partial review exposed in Advanced disclosure | No normal-flow control for internal partial state | SOURCE_REVIEWED; runtime/test gate OPEN / NOT_RUN |
| Completion guidance | Completion panel plus page-level next-action hint | Compact Review complete panel and CTA only on the editor | SOURCE_REVIEWED; runtime/test gate OPEN / NOT_RUN |
| Manual reviewer entry | Remembered reviewer support already existed | Compact reviewer summary remains unchanged | SOURCE_REVIEWED; exact candidate tests not collected |
| Clicks per routine case | NOT measured in a live 10-case run | NOT measured in a live 10-case run | NOT_RUN |
| Route transitions / scroll friction | NOT measured in a live browser | NOT measured in a live browser | NOT_RUN |

## Annotation Editor acceptance

- **One-row toolbar:** SOURCE_REVIEWED; responsive wrapping remains allowed below desktop widths. Rendered viewport confirmation is deferred to Owner UAT.
- **More tools:** Source inspection preserves Modal containment and viewport-safe placement; `frontend/tests/annotationEditor.test.tsx` passes 16 focused tests covering focus entry, active tool/help, inline Escape after focus moves to a later toolbar control, fullscreen retention, outside-pointer close, and trigger focus return. Browser/runtime UAT is OPEN / NOT_RUN.
- **Contextual help:** PASS in the 16 focused tests; source inspection also retains concise instructions for Select, Box, Polygon, Point, and Circle in both the page and fullscreen toolbar scopes. Rendered browser UAT remains OPEN / NOT_RUN.
- **Inline active tool:** PASS in the 16 focused tests; the inline toolbar exposes `Active tool: ...` and its concise drawing guidance. Rendered browser UAT remains OPEN / NOT_RUN.
- **Record partial review:** SOURCE_REVIEWED; removed from the normal clinician UI and its page action is no longer wired. Runtime/test gate OPEN / NOT_RUN.
- **Advanced default:** SOURCE_REVIEWED; unopened Advanced is not mutated by the editor. Runtime/test gate OPEN / NOT_RUN.
- **Completion panel:** PASS in the focused completed-state test; confirmed read-only cases use `Review complete`, retain the existing confirmation alert summary, omit a second ReviewerField, and keep one `Open next image` primary action plus explicit editing. Rendered browser UAT remains OPEN / NOT_RUN.
- **Duplicate guidance:** SOURCE_REVIEWED; the annotation page no longer renders the generic next-action hint beside the completion CTA. Runtime/test gate OPEN / NOT_RUN.
- **Image dominance:** SOURCE_REVIEWED; the image column remains the larger desktop grid column and toolbar is compact. Rendered viewport confirmation is deferred to Owner UAT.

## Design and clinical UX

- Brand tokens are named `brand.universityAccent` and `brand.medicinePrimary` as project tokens. No exact official KKU or Faculty of Medicine value is claimed because authoritative current brand verification was not performed in this pass.
- Clinical status colors remain separate from brand colors.
- Retinal lesion colors remain local to the viewer and unchanged.
- Thai/English resilience is preserved through existing system-font fallback and unconstrained reviewer input. A live Thai-label browser pass is `NOT_RUN`.
- Human authority, three confirmation milestones, completeness mapping, Advanced deferral, AI/Human provenance, original-image coordinates, immutable source behavior, and PostgreSQL authority were not changed.

## Validation receipt

| Check | Result | Evidence |
|---|---|---|
| Focused Annotation Editor tests | PASS, 16 tests in MAIN local run; O1 read-only collection limitation remains recorded separately | `npm.cmd test -- --run tests/annotationEditor.test.tsx`; MAIN passed on candidate `2413b00` |
| Frontend typecheck | PASS | `npm.cmd run typecheck` |
| Full frontend test suite | NOT_RUN | Not run for this exact candidate; only the focused Annotation Editor suite was executed |
| Frontend build | NOT_RUN | Not run for this exact candidate; no build PASS is claimed while the Vite/esbuild startup boundary remains unresolved |
| Backend/Ruff | NOT_RUN; no backend files changed | Not required for source-only frontend iteration; report final decision |
| Documentation QA | PASS | `python scripts/docs/check_docs.py`; 90 Markdown/Quarto sources |
| Root smoke | NOT_RUN | Not run for this exact candidate; backend-backed UI smoke requires the unavailable feature-worktree `.venv` |
| `git diff --check` | PASS | Repaired feature branch; base-to-candidate whitespace check rerun after documentation repair |
| Playwright viewport audit | OPEN / NOT_RUN | No authorized running workstation/browser evidence in this pass |
| Stagehand exploratory audit | OPEN / NOT_RUN | Exploratory only; never substitutes deterministic evidence |
| 10-case continuous audit | OPEN / NOT_RUN | Requires authorized synthetic/public runtime data |

## Known limitations

- Feature-worktree `.venv` availability and PostgreSQL DSN were not assumed; no persistence qualification is claimed here.
- 1920x1080, 1440x900, 1366x768, 1280x720, 1024x768, and mobile browser screenshots are not claimed until executed against a running workstation.
- Official institutional brand values were not verified; project token names are intentionally non-official.
- Reviewer account independence is an orchestration concern and is not established by this frontend pass.
- Historical Phase 2 legacy root-smoke limitations, unavailable final-audit environment, and deferred live Model API success remain historical/phase-boundary evidence and are not converted into P3-0 PASS claims.

## Review and self-audit

- MAIN self-audit: BOUNDED SOURCE CHECKS REVIEWED; focused annotation tests PASS (16/16), while the full suite and browser-audit/freeze acceptance remain OPEN / NOT_RUN. No frozen clinical, persistence, provenance, geometry, model, or phase-boundary contract was changed.
- Fresh configured O1 review of the first candidate: REQUIRED FIX findings included fullscreen popover DOM/focus/viewport behavior, completed reviewed-none copy, and stale readiness evidence.
- Follow-up bounded repair: fullscreen entry now closes any inline More tools popup before the Modal opens; outside-pointer close restores the stable trigger; Advanced copy is truthful. Focused MAIN tests pass 16/16; owner UAT remains open.
- Fresh configured O1 changed-diff review of candidate `e9436ba`: REQUIRED FIX findings covered focus classification for the viewer, Advanced wording, and exact-SHA evidence.
- Follow-up repair commit `2413b00`: viewer clicks now restore the More tools trigger, Advanced is explicitly optional/deferred, and the focused regression covers viewer dismissal; focused MAIN tests remain 16/16.
- Fresh exact-candidate O1 re-review of `f05ab3f`: REQUIRED FIX findings identified stale candidate wording and trailing whitespace in the base-to-candidate documentation diff; no approval is claimed for that revision.
- Follow-up documentation repair for exact candidate `8ba18eb`: the normative spec's trailing whitespace is removed; the historical `f05ab3f` and `d3a0031f` review findings remain preserved. This documentation-only correction is included in the final pre-integration review.

## Runtime UAT boundary

This document intentionally does not claim completion of the required live workstation checks. The runtime visual gate is `OPEN / NOT_RUN`: Playwright viewport screenshots at 1920x1080, 1440x900, 1366x768, 1280x720, 1024x768, and mobile widths remain pending. The 10-case continuous workflow gate is also `OPEN / NOT_RUN`, as is the Stagehand exploratory audit, until Owner UAT has an authorized running workstation and synthetic/public case set. The candidate remains `NOT_READY_FOR_OWNER_UAT`; this is not a browser-audit PASS, freeze PASS, or Owner UAT acceptance.

## Owner UAT boundary

This candidate stops before Phase 3. Owner UAT remains `OPEN / NOT_RUN / NOT_READY_FOR_OWNER_UAT`; after the required runtime gates are collected, the owner may inspect the normal synthetic/public workflow, the toolbar/popover, reviewed-none completion, and target workstation resolutions. Phase 3 remains `NOT_STARTED`.
