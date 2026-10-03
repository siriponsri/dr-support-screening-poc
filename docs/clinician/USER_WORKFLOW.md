# Clinician Workflow Quick Reference

This page is a short entry point, not a second workflow specification. The
canonical procedural source is the [Clinician User Manual](../manuals/clinician/index.qmd).

## Normal path: one line per image

1. **Worklist**: choose **Confirm Image** in the case row.
2. **Confirm Image**: review the progressive-disclosure context summary and any supported filename/source evidence, then confirm patient key, eye, and reviewer; Review opens. Filename suggestions remain evidence until confirmed.
3. **Review**: inspect the image and optional model suggestions, then choose
   **Continue to clinician review**. Nothing is decided on this page.
4. **Clinician Review**: select the final DR grade and choose **Confirm DR
   Grade**. *Grading complete* appears and the Annotation Editor opens.
5. **Annotation Editor**: start with the image-first **Box** tool. Click an AI
   ROI only where you disagree, change its class or box, or add a human finding.
   Choose **Confirm**, **Remove**, or **Close** for an AI ROI when needed.
   Advanced findings are optional and deferred.
6. **Finish image & next**: this is the third human confirmation. It records
   Core findings recorded, or explicitly **reviewed none found** when there are
   no Core human findings, then opens the next unfinished Worklist image. A
   reviewed-empty set is not a negative lesion label.

The three case-level confirmations are **Confirm Image**, **Confirm DR Grade**,
and **Finish image & next** (the internal milestone remains annotation
confirmation). A grade is *Not confirmed* until you confirm it;
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
- [Finish image and next](../manuals/clinician/07-confirm-annotation.qmd)
- [Working through cases: Previous/Next, autosave](../manuals/clinician/06-repeated-review.qmd)
- [Dataset readiness and export](../manuals/clinician/08-datasets.qmd)
