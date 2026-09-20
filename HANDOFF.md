# Handoff: S1 retinal viewer

Date: 2026-09-19

## Protected baseline

- Accepted clinician demo commit: `5482ae56c1e57adf7bea1f94e50ff72be92497ec`
- Annotated local tag: `v0.4-demo-2026-09-19`
- The tag is the pre-feature baseline. History was not rewritten.

## Delivered in this session

The S1 retinal viewer now has a shared transformed image/SVG stage with:

- fit-to-screen, 100% zoom, bounded zoom in/out, mouse-wheel zoom, drag pan, and double-click fit;
- a viewport-filling full-screen review modal with visible controls and close/exit actions;
- the same AI ROI, human annotation overlays, and annotation callbacks in inline and full-screen modes;
- original admitted image URLs rendered directly, with no preview/model-sized derivative introduced;
- overlay and annotation geometry kept in original-image pixel coordinates;
- full-screen editor controls for select, box, polygon, point, circle, label selection, undo, visibility toggles, and delete selected.

## Files changed

- `frontend/src/components/review/RetinalCanvas.tsx` — shared viewer stage, navigation, and full-screen surface.
- `frontend/src/pages/AnnotationEditorPage.tsx` — routes existing editor controls/callbacks into full-screen mode and prevents drawing gestures from becoming pans.
- `frontend/tests/retinalCanvas.test.tsx` — navigation and full-screen regression coverage.

## Scope and invariants

Do not modify RETFound, PRISM-DR, remote model API contracts, inference thresholds, admitted-image serving, annotation payload semantics, clinician-review semantics, `/app/` base behavior, or legacy `/ui/`. DICOM, PACS, and tiled-image infrastructure remain out of scope.

The viewer intentionally remains a client-side transform over the admitted source asset. If a future high-resolution/TIFF/DICOM backend is added, keep the viewer stage and geometry model independent of the asset transport layer.

## Validation

Run from the repository root unless noted:

```text
cd frontend && npm test
cd frontend && npm run typecheck
cd frontend && npm run build
python -m pytest -q
python -m ruff check dr_support tests
npm test
```

The focused viewer suite, full frontend suite, frontend typecheck/build, backend suite (`157 passed, 1 skipped`), Ruff, and root Node smoke tests passed during this session. A browser smoke check confirmed the modal fills the viewport after its portal layout settles, preserves the source image and AI ROI, and exposes the review controls. `agent-browser` was unavailable; Playwright CLI was used instead.

## Next-agent checklist

1. Confirm `git status`, the baseline tag, and the latest feature commit before further work.
2. Keep any future viewer changes inside the shared original-pixel stage; add tests for geometry alignment before changing persistence or API contracts.
3. Stop local Vite/API processes after manual verification if they are still running.
4. Do not add generated browser artifacts or runtime state to the commit.

## S1 interaction polish (2026-09-20)

The fullscreen retinal viewer now supports the clinician interaction pass requested after the accepted S1 viewer:

- compact fullscreen annotation controls that keep the image viewport dominant and avoid normal-page scrolling;
- right-mouse drag and Space + left-drag panning, with context-menu suppression scoped to the retinal canvas;
- selection and original-pixel movement for human rectangles, polygons, points, and circles;
- one-step movement history and Undo integration, with AI geometry remaining immutable;
- persistent additive HumanAnnotation.locked state; records without the field remain readable and are treated as locked by default;
- Lock / Unlock controls, V/B/Escape/Space/F/X/L/Arrow shortcuts, and a fixed original-image coordinate inspector status;
- crosshair cursor and status coordinates under the same transformed image/SVG stage.

## Interaction invariants

- The admitted source image remains the rendered asset; no preview, model-sized derivative, recompression, DICOM, PACS, or tiled backend was introduced.
- Human movement is clamped to the admitted image bounds and persisted in original-image pixel coordinates.
- RETFound, PRISM-DR, inference thresholds, Remote Model API contracts, clinician-review semantics, `/app/`, and legacy `/ui/` remain unchanged.
- The additive `locked` field defaults to `True` in the backend request contract for older clients; new editor drafts are explicitly unlocked until the clinician locks them.

## Files changed in the polish pass

- `frontend/src/components/review/RetinalCanvas.tsx` - gestures, coordinate inspector, compact status, and fullscreen layout.
- `frontend/src/pages/AnnotationEditorPage.tsx` - human selection/movement, locking, keyboard movement, and compact controls.
- `frontend/src/lib/api.ts` and `dr_support/workflow.py` - additive lock-field compatibility.
- `frontend/src/lib/icons.ts` - unlock icon export.
- `frontend/tests/retinalCanvas.test.tsx` - fullscreen navigation, gesture, context-menu, and coordinate regression coverage.
- `frontend/tests/annotationGeometry.test.ts` - bounded original-pixel translation coverage.
- `frontend/tests/annotationEditor.test.tsx` - movement, undo, and lock interaction coverage.
- `tests/test_workflow.py` - lock persistence/default compatibility coverage.

## Polish validation

```text
cd frontend && npm test                 # 23 passed
cd frontend && npm run typecheck        # passed
cd frontend && npm run build            # passed; existing chunk-size warning
python -m pytest -q                      # 157 passed, 1 skipped
python -m ruff check dr_support tests   # passed
npm test                                 # passed
```

Rendered smoke validation used the installed Chrome executable through Playwright because `agent-browser` and the Playwright browser bundle were unavailable. Review and annotation-editor fullscreen routes opened, source image URLs were verified, coordinate inspector toggled, compact controls rendered, and no application console/network errors were observed. The browser also reports the existing `/favicon.ico` 404.

## Owner acceptance checklist

1. Open a case and enter fullscreen review.
2. Confirm the source image remains detailed and AI ROI remains aligned.
3. Use wheel zoom, Zoom controls, Fit, double-click Fit, right-drag, and Space + left-drag.
4. In Annotation Editor, select an unlocked Human shape, drag it, and verify alignment at zoom and pan offsets.
5. Undo the movement, lock the shape, and confirm it no longer moves until unlocked.
6. Toggle Coordinate Inspector and verify original-image X/Y values in the bottom status bar.
7. Add or edit a Human annotation in fullscreen, then save through the existing review workflow.

## Final S1 viewer patch (2026-09-20)

- Selected unlocked Human rectangles support eight screen-space resize handles; geometry is clamped to original-image bounds with a 4 px minimum ROI dimension and one-step Undo history.
- Locked Human annotations expose no resize handles and remain immovable; AI/PRISM geometry remains immutable.
- Human geometry uses a 1.5 px normal stroke and 2.5 px selected stroke with non-scaling SVG strokes; handles stay usable across zoom levels.
- Coordinate Inspector is an exclusive mode: it blocks annotation creation, selection, movement, and resize; wheel zoom, right-drag pan, and Space + left-drag pan remain available.
- Inspector X/Y values remain in the bottom status bar only. Toggle-off and Escape return the editor to Select mode and cancel any in-progress drawing.

Final patch validation: frontend tests (29 passed), typecheck, production build, backend tests (157 passed, 1 skipped), Ruff, root smoke tests, and `git diff --check` passed. Optional real-browser smoke was skipped because Playwright and `agent-browser` were unavailable in the environment.
