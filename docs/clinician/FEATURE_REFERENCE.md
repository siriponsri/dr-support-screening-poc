# Clinician Feature Reference

This index names the current clinician-facing controls. The [Clinician User
Manual](../manuals/clinician/index.qmd) is the canonical source for procedures;
the [Developer Feature Implementation Map](../developer/FEATURE_IMPLEMENTATION_MAP.md)
is the canonical source for implementation ownership and contracts.

| Surface | Current responsibility | Canonical detail |
|:--|:--|:--|
| Worklist | Select an admitted case and start **Confirm Image**. | [Worklist](../manuals/clinician/02-workflow.qmd) |
| Confirm Image | Confirm pseudonymous patient key, eye, and reviewer attribution. | [Confirm Image](../manuals/clinician/02-workflow.qmd) |
| Review | Inspect the image and optional RETFound/PRISM-DR evidence. | [Review](../manuals/clinician/03-review.qmd) |
| Clinician Review | Select and confirm the final DR grade. | [DR grade](../manuals/clinician/04-confirm-grade.qmd) |
| Annotation Editor | Add human annotations or confirm, correct, or remove an AI ROI when needed. | [Annotations](../manuals/clinician/05-annotations.qmd) |
| Confirm Annotation | Confirm the active annotation set and its provenance hash. | [Annotation confirmation](../manuals/clinician/07-confirm-annotation.qmd) |
| Datasets | Check task-specific readiness and export the current Workspace state. | [Datasets](../manuals/clinician/08-datasets.qmd) |
| Reviewer default | Prefill new forms in this browser; never authentication and never a rewrite of history. | [Repeated review](../manuals/clinician/06-repeated-review.qmd) |

## Safety boundaries

- Human review remains authoritative.
- AI scores are model scores, not calibrated clinical probabilities.
- An empty lesion result is not proof that lesions are absent.
- Original admitted images remain immutable.
- Confirmed grades and annotation sets are read-only until the clinician
  explicitly chooses the edit action; edits create a new revision.
