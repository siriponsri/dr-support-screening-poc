---
status: Accepted (owner decision, V4)
date: 2026-09-23
---

# ADR-0006: Admit only human-selected, hospital-staged images; the team monitors coverage outside the Workbench

## Context and problem statement

The project needs coverage of Refer/Not-refer, sex, and left/right eyes. Hospital images remain in hospital-controlled storage, and clinicians must not become data managers.

## Considered options

- The team browses or queries hospital storage and pre-selects images
- Clinicians fill per-image quota forms
- Clinicians or authorized users select images during normal work and stage them through the approved hospital process; the team monitors coverage from exports and its own record

## Decision outcome

The Workbench admits only what appears in the configured Workspace input folder (top level). The project team does not browse storage or pre-select images. The source Refer/Not-refer class and sex are **not** stored in the Workbench; the team links them outside the software (`IMG-SAMP-013`, `IMG-SAMP-091`). Laterality comes from Confirm Image. Clinicians get a one-page guide with no forms.

### Consequences

- Good: a clear privacy and ownership boundary; minimal clinician burden; no software change needed.
- Bad: coverage monitoring depends on a team-held record and an owner-chosen linking mechanism (still open).

## More information

`docs/image-sampling-requirements/REQUIREMENTS_TRACEABILITY.md`, `docs/IMAGE_SAMPLING_REQUIREMENTS.pdf`.
