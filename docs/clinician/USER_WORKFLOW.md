# Clinician Workflow Quick Reference

This page is a short entry point, not a second workflow specification. The
canonical procedural source is the [Clinician User Manual](../manuals/clinician/index.qmd).

## Normal path

1. **Worklist**: select an admitted case and choose **Confirm Image**.
2. **Review**: inspect the image and optional model suggestions.
3. **Clinician Review**: select a final DR grade and choose **Confirm DR Grade**.
4. **Annotation Editor**: open it only when human annotation or an AI ROI change
   is needed; otherwise continue with the active annotation set.
5. **Confirm Annotation**: record the reviewed active set.
6. **Datasets**: check DR-ready and Lesion-ready separately, then export or move
   to the next case.

The three case-level confirmations are **Confirm Image**, **Confirm DR Grade**,
and **Confirm Annotation**. Model suggestions are optional evidence. A score is
not a calibrated clinical probability, and an empty lesion result does not
prove that lesions are absent.

## Find the detail

- [Worklist and Confirm Image](../manuals/clinician/02-workflow.qmd)
- [Review and optional AI assistance](../manuals/clinician/03-review.qmd)
- [Confirm DR Grade](../manuals/clinician/04-confirm-grade.qmd)
- [Annotation Editor](../manuals/clinician/05-annotations.qmd)
- [Confirm Annotation](../manuals/clinician/07-confirm-annotation.qmd)
- [Repeated review and navigation](../manuals/clinician/06-repeated-review.qmd)
- [Dataset readiness and export](../manuals/clinician/08-datasets.qmd)
