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

## S2 Workspace Manager closeout (2026-09-20)

Status: OWNER ACCEPTED / FROZEN.

The accepted S2 surface provides the complete local workspace lifecycle:

- create, edit, switch, and last-opened workspace restoration;
- optional workspace notes, including legacy catalog compatibility;
- safe deletion of inactive saved profiles, with explicit confirmation;
- active profiles cannot be deleted and must be switched away from first.

Workspace configuration consists of an input folder, output folder, and SQLite
review database. Native local folder/database pickers report selected,
cancelled, and unavailable states explicitly; cancellation leaves the form
unchanged and headless/unavailable environments do not invent browser paths.
SQLite is the authoritative S2 review storage backend, alongside the local
SQLite workspace catalog. Multi-database support, including PostgreSQL, MySQL,
and MongoDB, is deferred and is not part of S2.

The shell sidebar shows only the active workspace name and optional note, with
the Manage workspace action. Settings shows compact Input, Output, and
`SQLite · <database path>` metadata with copy affordances and full-value
accessible/title text for truncated paths. The Current Workspace panel uses
`[Active] [Edit]`; inactive saved profiles use `[Switch] [Edit] [Delete]`.
Long paths remain constrained to the Settings layout.

Safety and compatibility invariants remain frozen:

- deleting a profile removes only catalog metadata;
- input/output folders, retinal images, SQLite review data, and model result
  files are never deleted by profile removal;
- failed switching opens the candidate database before changing the active
  pointer/store, preserving the previous active workspace and store;
- existing SQLite catalogs/profiles without a note remain readable;
- S1 viewer behavior, model/provider contracts, API/clinical semantics, and
  legacy `/ui/` behavior remain unchanged.

Final S2 validation from the authoritative `main` worktree:

```text
python -m pytest -q tests/test_workspaces.py
python -m pytest -q
python -m ruff check dr_support tests
cd frontend && npm test -- workspace.test.tsx shell.test.tsx
cd frontend && npm test
cd frontend && npm run typecheck
cd frontend && npm run build
npm test
```

The frontend production bundle was rebuilt from `main`; `frontend/dist/` is
generated and gitignored.

## S2A1 Image Admission closeout (2026-09-20)

Status: OWNER ACCEPTED / FROZEN.

The merged S2A1 implementation at `838d644` passed a post-merge acceptance
audit against `docs/S2A_IMAGE_ADMISSION_SPEC.md`.

Audit conclusions:

- Workspace create, update, open, startup restoration, and explicit scan run a
  synchronous, local-only, top-level input-folder scan in deterministic filename
  order. Decode failures and per-file admission errors remain isolated from the
  rest of the scan. Identical file bytes use one stable hash-based case record;
  deleted files leave the active worklist and are not inferable.
- Admission and quality remain separate. Ambiguous, small, extreme-ratio,
  near-uniform, or extreme-brightness images stay reviewable; automatic logic
  does not assign `REJECTED_NON_FUNDUS`. Manual modality and quality decisions
  retain reviewer, timestamp, note, previous state, new state, and history.
- The backend eligibility predicate is enforced before both review inference
  routes and both standalone model API routes. Invalid, unresolved, non-fundus,
  ungradable, and quality-review states cannot reach RETFound, PRISM-DR, mock,
  or remote inference. Remote payloads contain image bytes and contract
  identifiers, not local workspace paths.
- Existing SQLite case data remains readable through additive JSON defaults;
  automatic and manual admission history remains persisted. The primary React
  worklist and review surfaces use plain-language admission status copy and do
  not expose admission enums or reason codes.

Known non-blocking limitations deferred to S2A2 or operational hardening:

- Each scan is a synchronous full-folder pass and re-decodes unchanged files;
  valid image bytes are retained in process memory for serving. Very large
  folders may therefore make workspace open or scan slow and memory-heavy.
- Discovery is intentionally top-level only. Recursive datasets, incremental
  fingerprints, background scanning, and path-change reconciliation are not
  part of S2A1.
- Real-browser owner smoke testing remains environment-dependent; the optional
  Playwright browser check was skipped because no browser runtime was available.

S2A1 validation from the authoritative `main` worktree:

```text
python -m pytest -q                         # 175 passed, 1 skipped
python -m ruff check dr_support tests       # passed
cd frontend && npm test                     # 42 passed
cd frontend && npm run typecheck            # passed
cd frontend && npm run build                # passed; existing chunk warning
npm test                                    # passed
python -m pytest -q tests/test_browser_ui.py # skipped; browser unavailable
```

## S2A2 Patient / Eye Resolver implementation handoff (2026-09-20)

Branch: `feat/s2a2-patient-eye-resolver`.

Status: implementation complete; awaiting integration review and owner smoke
acceptance. `main` was not modified by this implementation.

### Audit findings and boundaries

- Existing admitted-image records are JSON documents in the authoritative
  SQLite `cases.data` store. `workflow.detail()` is the shared projection used
  by the React Worklist and AI Review pages.
- The resolver is additive and leaves S1 viewer behavior, S2 Workspace Manager,
  S2A1 admission/inference guards, model providers, remote payloads, CVAT, and
  legacy `/ui/` unchanged.
- Existing S2A1 records without identity fields remain readable and default to
  an unlinked patient, `UNKNOWN` eye, and empty resolution history.
- The supplied `DR-DEMO/WS03_IDENTITY_PREVIEW` set contains synthetic filenames
  (`img13_L1`, `img15_L2`, `img14_R1`, `img16_R2`, and `unknown_001`) and public
  fundus pixels; no private patient data was added to the repository.

### Frozen contract

The additive case/API contract is recorded in
`docs/S2A2_PATIENT_EYE_CONTRACT.md`. It defines pseudonymous `patient_key`,
independent patient and laterality states/methods/reasons, `LEFT`/`RIGHT`/
`UNKNOWN`, automatic evidence, and append-only `resolution_history`.

`POST /v1/cases/{image_id}/resolver` uses the existing optimistic `revision`
guard. Patient actions (`CONFIRM`, `SET`, `LEAVE_UNLINKED`) and eye actions
(`SET` with `LEFT`, `RIGHT`, or explicit `UNKNOWN`) are independent. Manual
events preserve prior values, new values, reviewer, timestamp, note, and the
original automatic evidence.

### Parsing and reconciliation

- Full filename stems are parsed case-insensitively using explicit anchored
  patient-plus-eye/capture patterns, including `PAT0001_L1`,
  `PAT0001_LEFT_01`, `PAT0001-L`, `FI3010_L1_APR`, and matching right-eye
  forms.
- Patient-only patterns resolve the patient and leave eye `UNKNOWN`.
- Non-matching or ambiguous suffixes never infer an isolated eye letter.
- Filename evidence runs first. OCR is called only when filename evidence is
  incomplete or ambiguous; the default adapter is disabled and makes no network
  request.
- Filename/OCR disagreement yields `CONFLICT`; OCR candidates without a safe
  filename match require confirmation; no text, unavailable OCR, and OCR
  failure leave the image usable and unlinked when no other evidence exists.

### OCR adapter and privacy

`dr_support.services.resolver.OCRAdapter` is the optional provider boundary.
Adapters return structured candidate evidence/outcome status and never raw OCR
text. Credentials and any future remote-OCR configuration remain server-side.
RETFound and PRISM-DR payload construction was not changed; the privacy test
asserts that patient, laterality, and OCR fields are absent.

### Clinician surface

The Worklist shows a plain-language patient/eye status. AI Review provides
short confirmation, assignment, eye-side, and leave-unlinked actions. Primary
UI copy does not expose resolver enums, reason codes, or OCR status/error text.
S3 grouping/filter/navigation remains deferred.

### Validation on the feature worktree

```text
python -m pytest -q tests/test_resolver.py       # 16 passed
python -m ruff check dr_support tests             # passed
cd frontend && npm test -- resolver.test.tsx      # 1 passed
cd frontend && npm test                           # 43 passed
cd frontend && npm run typecheck                  # passed
cd frontend && npm run build                      # passed; existing chunk warning
```

Full backend and root smoke validation remain required before integration
review. Optional real-browser smoke is environment-dependent.
