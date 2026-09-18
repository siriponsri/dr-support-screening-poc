# V2 UI/UX Redesign Implementation Plan

## Goal
Transform the current multi-step technical UI into a clinician-first review workspace while preserving the backend API, persisted review state, CVAT integration, and lesion overlay semantics.

## Audit Findings
- Current navigation has four pages (Review Queue, Case Review, Annotation, Models) and forces clinicians to switch between Case Review and Annotation.
- CVAT steps (Prepare task, Run pre-label, Sync, Confirm) are exposed as primary workflow.
- "KKU" branding and red-soil chrome dominate the UI.
- Image viewer is static; no zoom/pan or lesion filtering.
- Backend review actions (`ACCEPT`, `CORRECT_GRADE`, `MARK_INCORRECT`, `ESCALATE`, `CONFIRM_ANNOTATIONS`) and CVAT endpoints already support the desired workflow.
- Frontend tests depend on removed element IDs; they must be updated.
- Windows backend tests fail because `socket.connect` monkeypatch blocks asyncio `socketpair()` used by `TestClient`; conftest must allow localhost-only socket usage.

## Changes

### 1. Information Architecture
Reduce visible product to three views:
- **Worklist** (was Review Queue)
- **Case Review** (combined grade + lesion hero experience)
- **Models & Audit** (was Models)

### 2. Case Review Hero Screen
- Large retinal image viewer with zoom, pan, reset, and fit.
- Lesion overlay toggle and per-class filters.
- Right-side AI Review panel:
  - Suggested DR grade + confidence/probabilities
  - Compact lesion summary
  - Warnings
  - Review status
  - Reviewer name + note fields
- Sticky bottom action bar:
  - **Accept** → `ACCEPT`
  - **Adjust Grade** → reveal grade selector → `CORRECT_GRADE`
  - **Needs Annotation** → `MARK_INCORRECT`
  - **Escalate** → `ESCALATE`
  - **Advanced Edit** → `/cvat/send` then open CVAT job URL

### 3. Workflow Automation
- Single **Analyze** action runs both global grading and lesion ROI inference.
- CVAT send/sync/confirm moves behind Advanced Edit; the live CVAT round-trip remains available via the same endpoints.

### 4. Visual Redesign
- Remove all visible "KKU" text and logos.
- Apply neutral clinical palette:
  - Primary accent `#A73B24`, hover `#8E311D`
  - Soft accent `#F7ECE8`
  - Muted gold `#C99A45`
  - Text `#1F2937`, secondary `#6B7280`
  - Background `#FAFAFA`, panel `#FFFFFF`, border `#E5E7EB`
- Minimal, professional, generous whitespace, restrained shadows.
- Lesion colors remain independent from UI semantic colors.

### 5. Files to Change
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `PREVIEW.html`
- `tests/ui.test.cjs`
- `tests/preview.test.cjs`
- `tests/conftest.py`
- `README.md`
- `docs/UI_THEME.md`
- `docs/LOCAL_RUNBOOK.md`
- New `CHANGELOG_V2.md`

### 6. Verification
- `python -m pytest -q`
- `npm test`
- `python -m ruff check dr_support tests`

## Compatibility
- No backend API contract changes.
- No scientific model scope changes.
- No OcuForge changes.
- CVAT_TOKEN remains environment-only.
