# HyperFrames Presentation Source Map

This map covers the 19-scene main line and the two-scene clinical-validation
branch in [`hyperframes/index.html`](hyperframes/index.html). The offline file
[`RETINAL_REVIEW_DEMO.html`](RETINAL_REVIEW_DEMO.html) is generated from that
source by `python scripts/docs/build_docs.py demo`; edit the HyperFrames source,
not the generated file. The Thai narration is in
[`PRESENTATION_SCRIPT_TH.md`](PRESENTATION_SCRIPT_TH.md).

## Truth labels

- **Current UI** means a screenshot or behavior from the accepted React
  Workbench and is marked `UI` in the deck.
- **Upstream example** means a public or owner-provided retinal image or model
  illustration that is not local product validation and is marked `UPSTREAM`.
- **Conceptual** means framing or a proposed validation question, not an
  outcome claim.
- Source notes are shown on the slides when a visual or claim could otherwise
  be mistaken for a local clinical result.

## Canonical inputs

- Clinician behavior: `docs/manuals/clinician/` and
  `docs/clinician/FEATURE_REFERENCE.md`.
- Image boundary and sampling responsibility: ADR-0006 and
  `docs/clinician/sampling/`.
- Model identities and deployment boundary: `dr_support/services/model_api.py`,
  `docs/operations/MODEL_SERVER.md`, and the developer manual.
- Dataset, annotation, and DICOM behavior: `dr_support/`,
  `docs/reference/DATASET_MANIFEST.md`, and the developer manual.
- UI screenshots: public/synthetic fixtures captured from the accepted UI and
  stored under `hyperframes/assets/`.
- Team provenance: the owner-provided `DR_Screening_OrgChart.pptx` is kept as
  an untracked local source reference. Five supplied portraits are used as
  `portrait-1.png` through `portrait-5.png`; roles without supplied portraits
  use initials and no biography is inferred.

## Main line

| Scene | Visual / purpose | Canonical source and truth label |
|---|---|---|
| `title` | Product name, real retinal image, and research-POC boundary | Product scope in `README.md`; retinal asset is an owner-provided/upstream example. |
| `why` | Why structured, traceable review matters | Conceptual framing; no local volume or outcome claim. |
| `is-not` | Assistive review boundary and non-goals | `README.md`, `AGENTS.md`, and clinician manual; current product positioning. |
| `scope` | Supported input, evidence, review, and output | Clinician manual, admission contracts, and dataset manifest. |
| `org-chart` | Seven supplied team roles | Owner-provided org-chart deck; names and roles preserved exactly. |
| `team` | Portrait-led team view | Five owner-provided portraits; `Dependa` and `Thiphornphan Uthaithat` use initials because no portraits were supplied. |
| `ai-architecture` | Separate global-grade and lesion-ROI evidence paths | Model provider contracts; conceptual architecture, not validation. |
| `retfound` | RETFound context and `retfound-aptos5` product identity | `dr_support/services/model_api.py` and upstream RETFound attribution; score is not calibrated probability. |
| `prism` | PRISM-DR lesion ROI evidence and four classes | `dr_support/services/model_api.py` and upstream PRISM-DR attribution; output is not product validation. |
| `uncertainty` | Ungradable and empty-detection safety boundary | `AGENTS.md`, clinician manual, and ICO guidance reference; no detection is not absence. |
| `boundary` | Hospital-controlled selection to approved staging | ADR-0006 and `docs/clinician/sampling/`. |
| `workflow` | Current explicit clinician path and next-case action | Phase-1 workflow in `docs/manuals/clinician/` and `frontend/src/`. |
| `worklist` | Select case and Confirm Image | `hyperframes/assets/ui-worklist.png`; current UI screenshot using a public/synthetic fixture. |
| `review` | Image-first review with optional model evidence | `hyperframes/assets/clinical/retina-upstream-roi.png`; upstream image/example plus current UI behavior. |
| `decision` | Select and confirm the final DR grade | `frontend/src/pages/ClinicianReviewPage.tsx`; current UI behavior and explicit grade requirement. |
| `annotation` | Confirm, correct, or remove an ROI while retaining provenance | `frontend/src/components/review/LesionActionPopover.tsx`, `RetinalCanvas.tsx`, and annotation tests; current UI screenshot. |
| `dicom-export` | Immutable source, analysis derivative, and grouped export | `dr_support/images.py`, dataset services, and `docs/reference/DATASET_MANIFEST.md`. |
| `deployment` | Separate Windows review workstation and Linux GPU Model API | `docs/operations/INSTALLATION.md`, `MODEL_SERVER.md`, and architecture ADRs. |
| `close` | Questions requested from ophthalmologists | Presentation purpose only; no clinical outcome claim. |

## Clinical-validation branch

The `clinical-questions` sequence is intentionally separate from the main
line. `clinical-questions-1` asks which global and lesion evidence changes the
next action. `clinical-questions-2` asks how to handle ungradable images and
evaluate the human-AI team. Both are discussion prompts, not product claims.

## Build and QA

```powershell
python scripts/docs/build_docs.py demo
python scripts/docs/check_docs.py
npx hyperframes lint docs/presentation/hyperframes
npx hyperframes check docs/presentation/hyperframes --snapshots
npx hyperframes present docs/presentation/hyperframes
```

`check_docs.py` requires the HyperFrames source, a 19-scene main line, the
two-scene branch, local assets, and the generated offline presentation. It
also checks local documentation links, retired paths, PDF locations, and
temporary task-spec cleanup.
