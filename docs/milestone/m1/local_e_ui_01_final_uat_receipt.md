# LOCAL-E-UI-01 Final UI UAT Receipt

**Engineering UI UAT status:** `PASS_WITH_DECLARED_PARTIALS`  
**Execution date:** 2026-10-13 (Asia/Bangkok)  
**Feature branch:** `feat/m1-local-e-ui-01-full-uat`  
**Baseline:** `73af341cab689b5a28f1d6fd887edcc0ee370807`

This receipt closes the bounded local product/UI UAT authorized for LOCAL-E-UI-01. It does not claim full M1 Phase 5 completion, public screenshot approval, model qualification, clinical validation, or production readiness. The detailed raw evidence remains ignored and local under `local-state/evidence/m1-ui-uat/run-20261012T102101Z-local-e-ui-01/`.

## PASS

| Area | Result and evidence |
|---|---|
| Responsive hardening | Reviewed the four existing responsive changes in `PageHeader`, `AppHeader`, `WorklistToolbar`, and `WorkspaceManager`. A separate mobile Worklist defect was found: the long unknown-image-type badge crossed into Patient/Eye. The badge now wraps within its cell. The local Playwright geometry assertion passes at 1440x900 and 390x844; page width equals viewport width in both captures. |
| Navigation and Worklist | Desktop/mobile route audit loaded all seven existing surfaces without page-wide horizontal overflow. Mobile Worklist horizontal scrolling exposed the action column. The mobile navigation, filename sorting menu, and filter controls were reachable. See `remaining_uat_results.json`, `closeout_ui_uat_results.json`, and the raw captures under `raw/`. |
| Filter scrolling | The existing PARTIAL was evidence incompleteness, not a remaining interaction failure. At 1440x900 the filter body measured 968/788 px; at 390x844 it measured 968/422 px. Playwright scrolled to and clicked the last `AI suggestion present` option on mobile. The filter interaction passes; no new infrastructure was added. Evidence: `ui_uat_result.json` and `worklist-filter-scroll-*.png`. |
| Review and model-degraded behavior | Review remained available in manual-only mode. The Model Connection surface showed `NOT_CONFIGURED`; no endpoint or token was configured. The bounded browser runs observed zero external hosts, no model-connection mutations, no inference request, and no page errors. Evidence: `ui_uat_result.json`, `remaining_uat_results.json`, and the Settings captures. |
| Grade and referral presentation | At both viewports, the browser pass verified an unconfirmed Grade 4 draft remains `Not determined`, confirmed Grade 4 displays `Refer`, confirmed Grade 3 displays `No referral indicated`, and Ungradable remains `Not determined`. Referral details displayed the source grade. This pass used in-memory UI response fixtures marked `WORKSPACE`; it did not persist or relabel a case. `tests/test_phase2_chunk_a.py` independently verifies persisted referral derivation and history. Evidence: `closeout_ui_uat_results.json`. |
| Annotation Editor | At both viewports, a confirmed-grade case rendered the Editor with Box, Finding class, and Finish controls enabled, without page overflow. Existing `annotationEditor.test.tsx` covers annotation editing, correction, movement, lock, completeness, and finish behavior. Existing local UAT also saved Finish image & next and exercised grade/annotation reopen warnings. Evidence: `closeout_ui_uat_results.json`, `complete_case1.py`, `case1-complete-worklist-desktop.png`, and `navigation_guard_results.json`. |
| Finish, save, and reopen | Prior local mechanics evidence shows Finish image & next completed the test case and returned to Worklist; grade and annotation edit warnings were shown on reopen. Reviewer preference persistence across reload also passed. These mechanics cases are not clinical ground truth. Evidence: `complete_case1.py`, `case1-complete-worklist-desktop.png`, `navigation_guard_results.json`, and `remaining_uat_results.json`. |
| Datasets safety | Datasets showed `WORKSPACE` records as unauthorized for protected/export use and kept export actions unavailable. Focused backend tests passed for admission, workflow, dataset, Phase 4 dataset, Bridge, and Phase 2 referral/manual-only behavior. This is negative-path safety evidence only. |
| Settings | Settings rendered at both viewports; the workspace row and controls fit mobile. The default reviewer preference was saved and reopened successfully. No Model Connection test or save action was invoked. |
| Focused validation | Frontend: 41 tests passed across seven Worklist, Review, Annotation Editor, reviewer preference, and Model Connection files. Typecheck passed. Production build passed with the existing large-chunk advisory. Backend: 69 focused tests passed across Phase 2 chunk A, admission, workflow, dataset, Phase 4 dataset, and Bridge. `git diff --check` passed. |
| Safety self-audit | Only six frontend component files are changed. The four owner-provided responsive changes are retained. The additional Worklist fix is presentation-only. No clinical rules, admission, patient/eye resolution, API/schema, provenance, annotation lineage, export authorization, or model/provider contract changed. WORKSPACE remains WORKSPACE and continues to fail closed for model-sensitive/export paths. Local fixtures/captures are ignored; no secrets, PHI, weights, runtime databases, logs, or screenshots are staged. |

## PARTIAL

- Worklist table text remains horizontally scrollable and some cells use truncation. The prior route audit measured 7 desktop and 20 mobile clipped text nodes; the action column was reachable, but a per-cell readability review was not completed. The separately observed unknown-modality badge overlap is fixed and re-tested.
- The new browser pass verified Annotation Editor controls and layout at both target viewports. It did not repeat human geometry editing and persistence as a live browser workflow at both sizes; the existing focused Annotation Editor tests passed those interactions.

## DEFERRED

- **PUBLIC/SYNTHETIC positive allowed-export/correction path:** `DEFERRED / NOT_RUN`. No canonical eligible persisted fixture was available within the delivery window. No fixture infrastructure was created.
- **PostgreSQL correction qualification:** `DEFERRED` where it depends on the unavailable eligible fixture.
- **Screenshot publication:** `BLOCKED / DEFERRED`. The privacy/publication gate and pixel-level owner review are incomplete. Captures remain raw, local, ignored, and unpublished.

These items are not PASS. The verified WORKSPACE protected/export/model-sensitive rejection remains valid safety evidence.

## NOT_RUN

- Model inference and injected model-error behavior; no model endpoint was configured.
- RunPod/GPU qualification, production deployment, clinical validation/use, regulatory readiness, and full M1 Phase 5 completion.
- Pixel-level owner privacy review and publication approval for screenshots.

## BLOCKED

- `SCREENSHOT_PUBLICATION`: `BLOCKED / DEFERRED` by the incomplete privacy/publication gate. This does not block the bounded engineering UI UAT.
- The broad frontend suite was previously interrupted after about six minutes without producing a result. The focused seven-file run above passed. Root smoke's legacy UI check could not load because root `node_modules/jsdom` was missing; its overlay and API-hardening checks passed.

## Evidence and Reproduction

Focused frontend command from `frontend/`:

```powershell
rtk npm test -- tests/worklist.test.tsx tests/worklistS3.test.tsx tests/worklistModel.test.ts tests/review.test.tsx tests/annotationEditor.test.tsx tests/reviewerPreference.test.tsx tests/modelConnectionSettings.test.ts
rtk npm run typecheck
rtk npm run build
```

Focused backend command from the repository root:

```powershell
rtk .venv/Scripts/python.exe -B -m pytest -q tests/test_phase2_chunk_a.py tests/test_admission.py tests/test_workflow.py tests/test_dataset.py tests/test_phase4_dataset.py tests/test_bridge.py
```

The bounded Playwright receipt is `closeout_ui_uat_results.json`. It records the candidate dirty-diff hash, 12 desktop/mobile assertions, screenshot hashes, `source_origin=WORKSPACE`, no persistence, no export/inference, no external hosts, and no mutation requests. The separate `ui_uat_result.json` records filter scrolling, sorting, navigation, Settings, Datasets, and Model Connection no-egress evidence.
