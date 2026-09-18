# Changelog — V2 UI/UX Redesign

## 0.2.0 — 2026-09-18

### Added
- Clinician-first Case Review hero experience:
  - Large retinal image viewer with zoom, pan, and fit controls.
  - Lesion overlay toggle and per-class filters.
  - Right-side AI Review panel with grade suggestion, probabilities, lesion summary, warnings, and review status.
  - Sticky bottom action bar: Accept, Adjust Grade, Needs Annotation, Escalate, Advanced Edit.
- Unified **Analyze** action that runs both global grading and lesion ROI inference in one step.
- V2 implementation plan at `docs/V2_IMPLEMENTATION_PLAN.md`.

### Changed
- Reduced product navigation to three views: **Worklist**, **Case Review**, **Models & Audit**.
- Combined grade review and lesion annotation into a single Case Review screen.
- CVAT preparation, pre-label push, and sync are now hidden behind **Advanced Edit**; the live
  CVAT round-trip remains available via the same backend endpoints.
- Visual redesign:
  - Removed all visible "KKU" text and logos.
  - Neutral premium clinical palette with `#A73B24` retained only as a subtle accent.
  - Generous whitespace, subtle borders, restrained shadows, improved typography.
- Updated `PREVIEW.html` for the new layout and disabled controls.
- Updated `README.md` and `docs/LOCAL_RUNBOOK.md` to describe the new workflow.
- Updated `docs/UI_THEME.md` to reflect the v2 palette.

### Fixed
- Backend test failure on Windows caused by `socket.connect` monkeypatch blocking asyncio
  `socketpair()` used by `TestClient`; `tests/conftest.py` now permits localhost-only socket
  plumbing.

## 0.2.1 — 2026-09-18

### Added
- Provider-neutral **REMOTE** inference mode (opt-in via `MODEL_RUNTIME=remote`).
  - `REMOTE_MODEL_URL` points the backend at an external Remote Model API.
  - `REMOTE_MODEL_TOKEN` is read from the environment only and sent as `Authorization: Bearer ...`;
    it is never returned by the API, persisted, or surfaced in the UI.
  - Backend proxies `/v1/predict/dr` and `/v1/predict/lesions`; preserves the existing
    `GlobalResult`/`LesionResult` Bridge v1 schema and the existing `/v1/models` metadata contract.
  - Inference latency and remote runtime status are surfaced in the Models & Audit metadata.
  - Clear timeout (504) and remote-error (502) responses; local-mode 503 path preserved.
- New tests with a mocked remote transport (`tests/test_remote.py`) covering success, timeout,
  non-2xx, malformed schema, token isolation, and metadata surfacing.

### Changed
- Action-bar hierarchy: primary review actions (Accept, Adjust Grade, Needs Annotation, Escalate) are now visually grouped; Advanced Edit/CVAT is separated and de-emphasized with a subtle style and external-link hint.
- Simplified clinical copy: "Model & provenance" → "Model details", "Preprocessing" → "Image preparation", and tightened lesion-help text.
- Improved empty-state guidance in the AI Review panel.
- Fixed a redundant disabled-condition in the Advanced Edit button template.
- Improved skip-link accessibility styling and focus visibility.

### Preserved
- Backend API contracts for `/v1/cases`, `/v1/infer/*`, `/v1/cases/{id}/review`, CVAT round-trip,
  persisted review state, and AI-vs-clinician overlay semantics unchanged.
- Local RETFound/PRISM and synthetic-mock providers remain the default and continue to work.
- Lesion colors remain independent from UI semantic colors.
- CVAT_TOKEN and REMOTE_MODEL_TOKEN remain environment-only; no secrets hardcoded or exposed.
