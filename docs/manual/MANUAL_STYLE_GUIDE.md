# Clinician manual style guide

## Audience

Write for clinicians and reviewers using the local workstation. Include operator detail only when it changes safe clinician operation or interpretation.

## Terminology

Use the exact UI labels **Worklist**, **Review**, **Clinician Review**, **Edit Annotations**, **Confirm Image**, **Confirm DR Grade**, **Confirm Annotation**, **Datasets**, **Models & Audit**, and **Settings**. Use **AI suggestion**, **model score**, **DR-ready**, and **Lesion-ready** consistently.

## Safety language

- **Safety** (warning callout) identifies a potential inappropriate clinical use, safety, or data-handling concern.
- **Important** (important callout) identifies essential operating information.

Use a callout only when it changes safe operation or interpretation. Keep each callout short; callouts never split across pages.

Model output is assistive evidence. Do not call a model score a calibrated probability. Do not describe an empty lesion result as proof that lesions are absent. Human review remains authoritative.

## Procedure writing

Use **Purpose**, **Before you begin**, **Procedure**, and **Expected result** for substantial workflows. Keep one user action per numbered step. Add a callout only when it changes safe operation or interpretation.

## Capitalization and labels

Use sentence case in prose. Preserve the capitalization of buttons, fields, tabs, and page titles. Put UI labels in bold. Put paths, commands, model IDs, status values, and schema identifiers in code formatting.

## Screenshot rules

Capture the final UI only, with public or synthetic data. The committed screenshots are v0.7.0 captures; the earlier capture scripts were removed from `main` in `ec74af8`, so a re-capture needs a script written against the current UI (for example Playwright against `python -m dr_support.run` with a synthetic Workspace). Prefer a locator or bounded region over a full-page screenshot. Keep the retinal image and the control being described visible. Crop long lists to a readable header and representative rows. Do not capture PHI, tokens, private paths, raw DICOM identifiers, or development panels. Each figure needs a concise caption and a nearby procedural reference.

## Model-language restrictions

Use **RETFound grade suggestion**, **PRISM lesion suggestion**, **model score**, and **model-assisted evidence**. Never imply autonomous diagnosis, calibrated risk, lesion absence, or regulatory approval. Preserve original AI provenance when describing a human correction or removal.

## Figures and tables

Use Quarto automatic figure and table numbering. A figure should answer where to click, what to inspect, or what changes after an action. Do not include duplicate screenshots or full-page tables when a focused crop is readable.

## Document control

The Quarto sources under `docs/manual/` are the single authoring source. Run `python scripts/docs/build_docs.py clinician-manual` after changing UI labels, screenshots, workflow semantics, or document-control values. The script copies the Quarto PDF to `docs/CLINICIAN_USER_MANUAL.pdf`. Add `--html` to also render the HTML site under `dist/manual/site/`.

## Print layout

Both manuals share `docs/manual/latex-style.tex`: chapters do not force a new page, headings keep following lines with them, hyphenation is off, and widows/orphans are suppressed. After every rebuild, inspect each PDF page. Fix a stranded heading, split code block, or half-empty page with a local `\Needspace` or `\clearpage` raw block rather than a global setting.

Page layout rules (adapted from WriteTech Hub, *Document Layout*, and Hansem Global, *Effective Document Design for User Documentation*):

- A4 with 25 mm side and top margins; nothing is allowed to run into the margin.
- Body text is left-aligned with a ragged right edge, never justified, and never hyphenated.
- Body leading is about 1.45x the font size; code blocks and tables are single-spaced.
- Paragraphs are separated by space, not indentation.
- The header carries the product and manual title; the footer carries the document ID, version, date, and page number.
- For short procedures, put the steps beside their screenshot (two columns); otherwise the screenshot sits directly above or below its steps.
- Warnings use the amber Safety callout and important notes use the green Important callout; colour is never the only signal because each callout also has a title.
