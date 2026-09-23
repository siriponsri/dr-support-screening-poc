# Change Log

## 0.7.0 - 2026-09-23

### Clinician workflow

- The current product is Retinal Review Workbench, a clinician-controlled retinal review and dataset workstation.
- The workflow uses explicit **Confirm Image**, **Confirm DR Grade**, and **Confirm Annotation** milestones.
- Model assistance remains optional; PRISM ROI correction and removal do not create a per-lesion confirmation queue.

### Annotation and review

- Original AI class, score, geometry, identity, and provenance remain auditable when a clinician corrects or removes an ROI.
- Reviewer defaults remain browser-local conveniences and never rewrite historical attribution.

### Dataset and deployment

- Dataset export uses `s4.dataset-manifest.v2` with separate DR-ready and Lesion-ready states.
- The Model API verifies pinned local RETFound and PRISM-DR assets before serving and supports offline-after-setup startup.
- Supported ophthalmic DICOM behavior remains bounded; non-fundus DICOM is reported as **Unsupported modality**.

### Documentation

- The clinician manual is authored and rendered as a Quarto Book with focused synthetic UI figures.
- Operator setup, health checks, offline operation, and release acceptance are documented separately.
