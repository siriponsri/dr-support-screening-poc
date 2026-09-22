# Clinician manual style guide

## Audience

Write for clinicians, reviewers, dataset operators, and hospital operators who need to use or safely support the workstation. Explain implementation details only when they change safe operation or interpretation.

## Terminology

Use **Review**, **Edit Annotations**, **Confirm Image**, **Confirm DR Grade**, **Confirm Annotation**, **AI suggestion**, **model score**, **Clinician corrected**, **DR-ready**, and **Lesion-ready** exactly as the interface uses them. Use “retinal image” for a supported fundus photograph and “unsupported modality” for a recognized MRI or other non-fundus DICOM object.

## Safety language

- **WARNING**: potential inappropriate clinical use or safety concern.
- **CAUTION**: workflow, operational, or data-integrity risk.
- **IMPORTANT**: essential operating information.
- **NOTE**: useful supplementary information.

State that model output is assistive evidence, not diagnosis, referral, treatment advice, or disease truth. Never call a model score a calibrated probability. Never describe an empty lesion result as proof that lesions are absent.

## Procedure writing

Important procedures use: **Goal**, **Before you start**, numbered **Steps**, **Expected result**, **What the system records**, and only relevant safety callouts. Use exact UI labels in bold. Keep one action per step and describe the expected state after the action.

## Capitalization and UI labels

Use sentence case in prose. Preserve the capitalization of buttons, fields, tabs, and headings exactly as rendered. Put UI labels in bold; put paths, commands, model ids, status codes, and field names in code formatting.

## Screenshot rules

Capture the final UI only, at a stable state, using public or synthetic data. Prefer a focused crop for a control or an image-first page for orientation. Do not capture PHI, tokens, private paths, raw DICOM identifiers, or hidden development panels. Every figure has a descriptive caption and is referenced from the procedure that uses it.

## Model-language restrictions

Use “RETFound grade suggestion”, “PRISM lesion suggestion”, “model score”, and “model-assisted evidence”. Do not imply autonomous diagnosis, calibrated risk, lesion absence, or regulatory approval. Preserve original AI provenance when describing a human correction or removal.

## Figure and table conventions

Use automatic Quarto numbering. Captions state what the reader should notice, not merely the route name. Tables contain only information needed for operation, safety, or audit. Avoid duplicate evidence tables and dashboard-style decoration.

## Document control

The Quarto sources under `docs/manual/` are the single authoring source. The build script produces the HTML site under `dist/manual/site/` and the printable PDF at `docs/CLINICIAN_USER_MANUAL.pdf`. Update the document-control section and run the manual build whenever UI labels, screenshots, or workflow semantics change.
