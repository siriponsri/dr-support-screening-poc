# Product presentation source map

Traceability for [`RETINAL_REVIEW_DEMO.html`](RETINAL_REVIEW_DEMO.html), built from [`src/RETINAL_REVIEW_DEMO.source.html`](src/RETINAL_REVIEW_DEMO.source.html).

Every on-screen claim comes from the Clinician User Manual, the sampling requirements, or verified code. Narration: [`PRESENTATION_SCRIPT_TH.md`](PRESENTATION_SCRIPT_TH.md). `check_docs.py` confirms that the reveal count and the `[กด Space]` count match for each scene.

**Path abbreviations** used in the table:

- CUM = [Clinician User Manual](../manual/index.qmd)
- TISR = [Team Image Sampling Requirements](../image-sampling-requirements/index.qmd)
- Req = [`REQUIREMENTS_TRACEABILITY.md`](../image-sampling-requirements/REQUIREMENTS_TRACEABILITY.md)
- `shots/` = `docs/manual/screenshots/`
- `assets/` = `docs/demo/assets/`

| Scene | Reveals | Manual / source document | UI route / component | Asset | Key claim | Requirement IDs |
|:--|--:|:--|:--|:--|:--|:--|
| 01 Cover | 0 | CUM §1 *Before You Begin*; README | None | `assets/demo-synthetic-fundus.png`, `assets/dr-support-logo.svg` | The Workbench turns a selected retinal image into a reviewed, traceable dataset. It is a research and clinical-support POC, and human review is authoritative. | None |
| 02 Where the images come from | 7 | TISR ch. 2–4, 7; [Clinician Image Selection Guide](../image-selection/IMAGE_SELECTION_GUIDE.html) | Workspace input folder (`dr_support/services/admission.py` `scan_input_folder`) | `assets/demo-synthetic-fundus.png` (drawing) | Clinicians or authorized users choose the images; the team does not browse storage. Images arrive by approved staging. The team monitors Refer/Not-refer, sex, and left/right coverage; clinicians do not manage quotas. | IMG-SAMP-001, 002, 003, 010, 020, 031, 033, 040, 070, 071, 090, 100 |
| 03 The review workflow | 3 | CUM Quick Start, Figure 1 | `/worklist` → `/review/:imageId` → `/clinician-review/:imageId` → `/edit/:imageId` → `/datasets` | None (drawn) | Eight steps with three case-level confirmations. AI is optional. There is no per-lesion queue. | None |
| 04 Worklist and Confirm Image | 3 | CUM §2 | `WorklistPage`, `ConfirmImageDialog`; `POST /v1/cases/{id}/confirm-image` | `assets/demo-worklist.png`, `shots/02-confirm-image.png`, `assets/hotspots.json` (`worklist_row`) | Source files are never modified. Confirm Image records a pseudonymous patient key, the eye (Left/Right/Unknown), and the reviewer. Filename hints are evidence only. | IMG-SAMP-041, 042, 050 |
| 05 Review with optional AI | 4 | CUM §3 | `ReviewPage`, `RetinalCanvas`; `POST /v1/infer/global`, `/v1/infer/lesion-roi` | `assets/demo-review-canvas.png`, `assets/demo-dr-assessment.png`, `assets/demo-lesion-suggestions.png`, `hotspots.json` (`review_roi`) | Analyze is optional. The RETFound score is not a calibrated probability. An empty PRISM-DR result does not prove absence. Review is read-only. | None |
| 06 Confirm DR Grade | 3 | CUM §4 | `ClinicianReviewPage`; `POST /v1/cases/{id}/review` | `shots/05-confirm-dr-grade.png`, `shots/06-dr-grade-recorded.png` | The Final DR grade (0–4) is recorded as `AI_ACCEPTED`, `AI_CORRECTED`, or `MANUAL`; the human grade is authoritative. This grade is not the source Refer/Not-refer class. | IMG-SAMP-011 |
| 07 Edit Annotations | 3 | CUM §5, §6 (autosave), §7 | `AnnotationEditorPage`; `PUT /v1/cases/{id}/annotations`; `POST /v1/cases/{id}/review` (`CONFIRM_ANNOTATIONS`) | `shots/07-annotation-editor.png` | Human annotations are stored in original pixels. The draft autosaves. A draft is not a confirmation; Confirm Annotation records reviewer, time, and the active-set hash. | None |
| 08 Correct or remove an AI ROI | 4 | CUM §5.2 | `LesionActionPopover`; `POST /v1/cases/{id}/lesion-review` | `assets/demo-roi-before.png`, `assets/demo-roi-popover.png`, `assets/demo-roi-after.png`, `assets/demo-roi-corrected-chip.png` | Correction or removal keeps the original AI class, score, geometry, and provenance. A score is never shown with a corrected class. | None |
| 09 Built for repeated review | 5 | CUM §6 | `CaseNavigation`, `NextActionHint`, `lib/reviewerPreference.ts`, `AnnotationEditorPage` (autosave, leave guard) | `shots/10-navigation-hint.png`, `assets/demo-grade-nav.png`, `assets/demo-draft-unsaved.png`, `shots/11-draft-status.png`, `shots/13-reviewer-default.png` | Navigation never saves or confirms. The reviewer default is browser-local and is not authentication. Unsaved changes are guarded. | None |
| 10 Dataset readiness | 3 | CUM §8; [`DATASET_MANIFEST.md`](../DATASET_MANIFEST.md) | `DatasetsPage`; `GET /v1/dataset/manifest`, `POST /v1/dataset/export` | `shots/14-dataset-readiness.png` | DR-ready and Lesion-ready are separate. PAT0003 is DR-ready only. The export is `manifest.json`, `images.csv`, and `annotations.csv`. | IMG-SAMP-051 (no automatic split) |
| 11 Provenance and deployment | 3 | CUM §9; [Deployment & Operations Manual](../operator-manual/index.qmd); [architecture](../architecture/) | `ModelsPage`; `dr_support/app.py` profiles; `scripts/model-server/*.sh` | None (drawn) | Source and analysis SHA-256 identities are kept. Model weights never run on the workstation. The Model API runs on the hospital GPU host and works offline after setup. CVAT is optional. | None |
| 12 Live demo | 1 | CUM Quick Start | `/app/` on `127.0.0.1:8000` | None | Live walkthrough on a synthetic Workspace only. | IMG-SAMP-110 |

## Asset rules

- Every screenshot is a real v0.7.0 UI capture with synthetic or public data. No PHI, tokens, or private paths appear.
- `demo-synthetic-fundus.png` and the drawings in scene 2 are illustrations, not retinal photographs.
- Hotspot rectangles are percentages of the captured frame (`docs/demo/assets/hotspots.json`). Re-measure them if a screenshot is replaced.
- The clinician-facing deck deliberately omits the full team sampling matrix. That matrix appears only in [`TECHNICAL_BRIEFING.html`](TECHNICAL_BRIEFING.html) and the Team Image Sampling Requirements.
