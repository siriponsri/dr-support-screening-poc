# Clinician Feature Reference

This index names the current clinician-facing controls. The [Clinician User
Manual](../manuals/clinician/index.qmd) is the canonical source for procedures;
the [Developer Feature Implementation Map](../developer/FEATURE_IMPLEMENTATION_MAP.md)
is the canonical source for implementation ownership and contracts.

| Surface | Current responsibility | Canonical detail |
|:--|:--|:--|
| Worklist | Start each image with **Confirm Image**; status shows **Grade confirmed** or **Review complete**. | [Worklist](../manuals/clinician/02-workflow.qmd) |
| Confirm Image | Confirm pseudonymous patient key, eye, and reviewer attribution. | [Confirm Image](../manuals/clinician/02-workflow.qmd) |
| Review | Inspect the image and optional RETFound/PRISM-DR evidence; one forward action, **Continue to clinician review**. | [Review](../manuals/clinician/03-review.qmd) |
| Clinician Review | Select and confirm the final DR grade; *Not confirmed* until **Confirm DR Grade**. | [DR grade](../manuals/clinician/04-confirm-grade.qmd) |
| Annotation Editor | Optional: correct an AI ROI in place (class dropdown, drag/resize) with **Confirm / Remove / Close**, or draw human annotations. | [Annotations](../manuals/clinician/05-annotations.qmd) |
| Confirm Annotation | Finish the image (active set and hash recorded); opens the next unfinished Worklist image. | [Annotation confirmation](../manuals/clinician/07-confirm-annotation.qmd) |
| Datasets | Check task-specific readiness and export the current Workspace state. | [Datasets](../manuals/clinician/08-datasets.qmd) |
| Reviewer default | Prefill new forms in this browser; never authentication and never a rewrite of history. | [Repeated review](../manuals/clinician/06-repeated-review.qmd) |

## Safety boundaries

- Human review remains authoritative.
- AI scores are model scores, not calibrated clinical probabilities.
- An empty lesion result is not proof that lesions are absent.
- Original admitted images remain immutable.
- Confirmed grades and annotation sets are read-only until the clinician
  explicitly chooses the edit action; one warning appears per edit session and
  edits create a new revision.
- Previous/Next warns once while the current image is incomplete; a complete
  image switches without a warning.
- Confirm Annotation completes the case; it does not mean every AI ROI was
  individually verified.
