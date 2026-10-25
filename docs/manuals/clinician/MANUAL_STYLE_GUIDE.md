# Clinician manual style guide

## Audience

Write for clinicians and reviewers using the local workstation. Include operator detail only when it changes safe clinician operation or interpretation.

## Terminology

Use the exact UI labels **Worklist**, **Review**, **Clinician Review**, **Annotation Editor**, **Confirm Image**, **Confirm DR grade** (**Confirm Ungradable** for Ungradable), **Datasets**, **Models & Audit**, and **Settings**. The sidebar groups are **Clinical review** and **Administration**. Use **AI suggestion**, **model score**, **DR-ready**, and **Lesion-ready** consistently. The backend action remains `CONFIRM_ANNOTATIONS`.

The Finish button changes its label: **Finish image & next** when findings exist, **Finish: reviewed none found** when there are no findings and no AI suggestions, and **Finish: no findings added (N AI suggestions not accepted)** otherwise. Both no-findings labels store `REVIEWED_NONE_FOUND`. In prose, call it "the Finish button" when the label does not matter.

Verify every label against the frontend source (`frontend/src/pages/*.tsx`, `frontend/src/components/**`) before writing it. Never describe a label or behaviour the code does not have.

## Safety language

- **Safety** (warning callout) identifies a potential inappropriate clinical use, safety, or data-handling concern.
- **Important** (important callout) identifies essential operating information.

Use a callout only when it changes safe operation or interpretation. Keep each callout short; callouts never split across pages.

Model output is assistive evidence. Do not call a model score a calibrated probability. Do not describe an empty lesion result as proof that lesions are absent. Human review remains authoritative.

## Procedure writing

Use **Purpose**, **Before you begin**, **Procedure**, and **Expected result** for substantial workflows. Keep one user action per numbered step. Add a callout only when it changes safe operation or interpretation.

## Punctuation

Do not use the middle dot or long dashes (including the LaTeX `--`) as separators, in quoted UI text or in prose. Use "/", ":" or a short "-" instead, for example `EX 0.82`, *DR grade confirmed: Moderate NPDR*, and "Grade 0-4" (see `DESIGN.md` 2.3). Callout titles use a colon, for example `Safety: clinical use`.

## Capitalization and labels

Use sentence case in prose. Preserve the capitalization of buttons, fields, tabs, and page titles. Put UI labels in bold. Put paths, commands, model IDs, status values, and schema identifiers in code formatting.

## Screenshot rules

Capture the final UI only, with public or synthetic data. The committed screenshots are v0.7.0 captures; the earlier capture scripts were removed from `main` in `ec74af8`, so a re-capture needs a script written against the current UI (for example Playwright against `python -m dr_support.run` with a synthetic Workspace). Prefer a locator or bounded region over a full-page screenshot. Keep the retinal image and the control being described visible. Crop long lists to a readable header and representative rows. Do not capture PHI, tokens, private paths, raw DICOM identifiers, or development panels. Each figure needs a concise caption and a nearby procedural reference.

## Screenshots pending refresh

The text was updated to the M1 UI on 2026-10-25, but most screenshots are still v0.7.0 captures and no longer match it. They stay referenced until they are re-captured. Never capture them from the hospital instance: it holds consented hospital images that must not be committed. Re-capture from a synthetic or public-sample Workspace (`python -m dr_support.run` with a synthetic Workspace), then rebuild the PDF.

| File | Why it no longer matches | What the new capture should show |
|:-----|:-------------------------|:---------------------------------|
| `images/clinician-workflow.png` / `.svg` | Middle-dot separators; "Confirm DR Grade" and "Confirm Annotation" labels; "Confirm Image starts again". | Same eight steps with ":" or "/" separators, "Confirm DR grade", "Finish image & next", and "Next unfinished image". |
| `01-worklist.png` | Old sidebar groups; "N cases - N need attention"; Result shows AI grade; Review shows Review complete / Pending review. | Quick filter chips All / Not started / In progress / Done with counts, "N cases shown", Result with a clinician grade and "AI ready", Review with Not started / In progress / Done and a next step. Optional second capture: Done selected with the Final grade row. |
| (new) Quick look | Not captured yet. | Quick look panel for a done case: large image, AI suggestions and Clinician findings switches, final grade, findings, reviewer, Open review. |
| `02-confirm-image.png` | No image beside the fields, no image quality choice, full reviewer field. | Dialog with the retinal image on the left; Image type, Patient, Eye summaries; Image quality (optional) Usable / Not usable; "Reviewer: name" with Change. |
| `03-review-overview.png` | Old viewer modes and technical details on the page; sidebar expanded. | Sidebar collapsed; viewer modes Original / AI evidence / More views; Analysis with AI READY; DR assessment with "AI: RETFound (CFP grading)"; Processing details collapsed. |
| `04-ai-controls.png` | "Show AI suggestions" switch and middle-dot lesion filter labels. | AI evidence selected, lesion filter with "MA: Microaneurysm" style options, and "Active overlays N of M raw AI suggestions". |
| (new) PRISM quality gate | Not captured yet. | Preview PRISM input opened on an image without confirmed quality: "Confirm image quality before using PRISM." with Image quality acceptable. |
| `05-confirm-dr-grade.png` | Grade dropdown and "Confirm DR Grade". | Grade buttons 0-4 and U with one selected, Grade guide, "Reviewer: name", Confirm DR grade, Can't finalize this case. |
| `06-dr-grade-recorded.png` | "DR grade confirmed" heading and middle-dot toast. | Grading complete card with grade, reviewer, confirmed at, Continue to Annotation Editor, Edit confirmed grade. |
| `07-annotation-editor.png` | Old Finish label; sidebar expanded. | Sidebar collapsed; Review findings toolbar; Complete review panel with the Finish label for the case shown. |
| `08-roi-popover.png` | Overlay label uses a middle dot. | Selected AI ROI labelled `HE 0.55` with the AI suggestion card. |
| `09-roi-corrected.png` | Old corrected-label format. | Corrected ROI labelled `EX: clinician corrected` and a human box labelled `Human: HE`. |
| `10-navigation-hint.png` | Old third body line. | "Switch to another image?" with "Unconfirmed work will still need your attention." |
| `11-draft-status.png` | Shows the removed Save draft button. | Draft status line only ("N human annotations" and "Draft saved"). |
| `12-confirm-annotation.png` | Old Finish label. | Complete review panel with "Finish: no findings added (N AI suggestions not accepted)" or "Finish image & next". |
| `13-reviewer-default.png` | "Show next action hints" checkbox. | Review preferences with Default reviewer and the Guide mode checkbox. |
| `14-dataset-summary.png` | Old "Dataset manifest" summary and Lesion-ready tab. | Workspace Data header (Workspace, records, digest), filters, and tabs All / DR-ready / Lesion-positive ready / Needs review / Excluded. |
| `14-dataset-readiness.png` | Old table columns. | DR-ready tab with DR label, Lesion labels, Completeness, Source, and Details columns. |
| `19-case-complete.png` | Middle-dot toast, old Worklist, old Confirm Image dialog. | After Finish: the Worklist notice "Case complete. Opening the next Worklist image." behind the next image's new Confirm Image dialog. |

`15-export-success.png`, `16-models-audit.png`, `17-edit-grade-warning.png`, and `18-edit-annotations-warning.png` still match the current UI.

## Model-language restrictions

Use **RETFound grade suggestion**, **PRISM lesion suggestion**, **model score**, and **model-assisted evidence**. Never imply autonomous diagnosis, calibrated risk, lesion absence, or regulatory approval. Preserve original AI provenance when describing a human correction or removal.

## Figures and tables

Use Quarto automatic figure and table numbering. A figure should answer where to click, what to inspect, or what changes after an action. Do not include duplicate screenshots or full-page tables when a focused crop is readable.

## Document control

The Quarto sources under `docs/manuals/clinician/` are the single authoring source. Run `python scripts/docs/build_docs.py clinician-manual` after changing UI labels, screenshots, workflow semantics, or document-control values. The script copies the Quarto PDF to `docs/pdfs/CLINICIAN_USER_MANUAL.pdf`. Add `--html` to also render the HTML site under `dist/manual/site/`.

## Print layout

Both manuals share `docs/manuals/clinician/latex-style.tex`: chapters do not force a new page, headings keep following lines with them, hyphenation is off, and widows/orphans are suppressed. After every rebuild, inspect each PDF page. Fix a stranded heading, split code block, or half-empty page with a local `\Needspace` or `\clearpage` raw block rather than a global setting.

Page layout rules (adapted from WriteTech Hub, *Document Layout*, and Hansem Global, *Effective Document Design for User Documentation*):

- A4 with 25 mm side and top margins; nothing is allowed to run into the margin.
- Body text is left-aligned with a ragged right edge, never justified, and never hyphenated.
- Body leading is about 1.45x the font size; code blocks and tables are single-spaced.
- Paragraphs are separated by space, not indentation.
- The header carries the product and manual title; the footer carries the document ID, version, date, and page number.
- For short procedures, put the steps beside their screenshot (two columns); otherwise the screenshot sits directly above or below its steps.
- Warnings use the amber Safety callout and important notes use the green Important callout; colour is never the only signal because each callout also has a title.
