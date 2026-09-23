# Clinician Workflow Quick Reference

This page is a short entry point, not a second workflow specification. The
canonical procedural source is the [Clinician User Manual](../manuals/clinician/index.qmd).

## Normal path: one line per image

1. **Worklist**: choose **Confirm Image** in the case row.
2. **Confirm Image**: confirm patient key, eye, and reviewer; Review opens.
3. **Review**: inspect the image and optional model suggestions, then choose
   **Continue to clinician review**. Nothing is decided on this page.
4. **Clinician Review**: select the final DR grade and choose **Confirm DR
   Grade**. *Grading complete* appears and the Annotation Editor opens.
5. **Annotation Editor**: optional. Click an AI ROI only where you disagree,
   change its class or box, and choose **Confirm**, **Remove**, or **Close**.
6. **Confirm Annotation**: *Case complete* appears and Confirm Image opens for
   the next unfinished Worklist image.

The three case-level confirmations are **Confirm Image**, **Confirm DR Grade**,
and **Confirm Annotation**. A grade is *Not confirmed* until you confirm it;
there is no separate senior-review or not-confirm action. You do not need to
inspect every AI ROI, and untouched AI suggestions never become human labels.
A score is not a calibrated clinical probability, and an empty lesion result
does not prove that lesions are absent. **Datasets** shows DR-ready and
Lesion-ready separately.

## Find the detail

- [Worklist and Confirm Image](../manuals/clinician/02-workflow.qmd)
- [Review and optional AI assistance](../manuals/clinician/03-review.qmd)
- [Confirm DR Grade](../manuals/clinician/04-confirm-grade.qmd)
- [Annotation Editor](../manuals/clinician/05-annotations.qmd)
- [Confirm Annotation](../manuals/clinician/07-confirm-annotation.qmd)
- [Working through cases: Previous/Next, autosave](../manuals/clinician/06-repeated-review.qmd)
- [Dataset readiness and export](../manuals/clinician/08-datasets.qmd)
