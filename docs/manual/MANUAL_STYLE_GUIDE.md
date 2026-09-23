# Clinician manual style guide

## Audience

Write for clinicians and reviewers using the local workstation. Include operator detail only when it changes safe clinician operation or interpretation.

## Terminology

Use the exact UI labels **Worklist**, **Review**, **Clinician Review**, **Edit Annotations**, **Confirm Image**, **Confirm DR Grade**, **Confirm Annotation**, **Datasets**, **Models & Audit**, and **Settings**. Use **AI suggestion**, **model score**, **DR-ready**, and **Lesion-ready** consistently.

## Safety language

- **WARNING** identifies a potential inappropriate clinical use or safety concern.
- **CAUTION** identifies a workflow, operational, or data-integrity risk.
- **IMPORTANT** identifies essential operating information.
- **NOTE** provides useful supplementary information.

Model output is assistive evidence. Do not call a model score a calibrated probability. Do not describe an empty lesion result as proof that lesions are absent. Human review remains authoritative.

## Procedure writing

Use **Purpose**, **Before you begin**, **Procedure**, and **Expected result** for substantial workflows. Keep one user action per numbered step. Add a callout only when it changes safe operation or interpretation.

## Capitalization and labels

Use sentence case in prose. Preserve the capitalization of buttons, fields, tabs, and page titles. Put UI labels in bold. Put paths, commands, model IDs, status values, and schema identifiers in code formatting.

## Screenshot rules

Capture the final UI only, with public or synthetic data. Prefer a locator or bounded region over a full-page screenshot. Keep the retinal image and the control being described visible. Crop long lists to a readable header and representative rows. Do not capture PHI, tokens, private paths, raw DICOM identifiers, or development panels. Each figure needs a concise caption and a nearby procedural reference.

## Model-language restrictions

Use **RETFound grade suggestion**, **PRISM lesion suggestion**, **model score**, and **model-assisted evidence**. Never imply autonomous diagnosis, calibrated risk, lesion absence, or regulatory approval. Preserve original AI provenance when describing a human correction or removal.

## Figures and tables

Use Quarto automatic figure and table numbering. A figure should answer where to click, what to inspect, or what changes after an action. Do not include duplicate screenshots or full-page tables when a focused crop is readable.

## Document control

The Quarto sources under `docs/manual/` are the single authoring source. Run `python scripts/manual/build_manual.py` after changing UI labels, screenshots, workflow semantics, or document-control values. The script produces the HTML site under `dist/manual/site/` and copies the Quarto PDF to `docs/CLINICIAN_USER_MANUAL.pdf`.
