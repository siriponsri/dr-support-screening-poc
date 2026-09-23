# Feature reference

This reference describes the clinician-facing feature surface and the state it records. Model evidence is assistive. Human review remains authoritative.

| Feature | Location and action | Persisted state / audit effect | Training eligibility | Limitation |
| --- | --- | --- | --- | --- |
| Workspace | **Settings**; create or select a Workspace | Input/output folders and SQLite catalog/profile | None by itself | Source images are not copied or deleted by profile removal |
| Worklist | **Worklist**; scan, filter, open, or exclude a case | Admission, queue, resolver, and case state | Exclusion prevents readiness | Filename suggestions are evidence, not identity confirmation |
| Confirm Image | Worklist **Confirm Image** | Image review, patient/eye context, reviewer, timestamp, and audit event | Required for new task readiness | Uses a self-declared reviewer name; no authentication is implied |
| Review | **Review**; inspect image and choose model assistance | No per-ROI mutation or evidence-resolution state | None directly | It is an inspection surface, not a detailed annotation queue |
| RETFound | Review **Analyze** | Model id/revision, grade, score, inference metadata, and hashes | Grade output is not final until clinician confirmation | Scores are not calibrated probabilities |
| PRISM overlays | Review **Show AI suggestions** and lesion filter | Original ROI geometry, class, score, model and inference provenance | AI-only ROIs are not ground truth | Empty output does not prove lesion absence |
| Edit Annotations | Review **Edit annotations** | Human annotations, original-image coordinates, reviewer and timestamp | Draft edits do not make a case ready | Geometry correction remains separate from Review |
| AI ROI correction/removal | Edit Annotations; select an AI ROI and use the contextual action | Adds a human correction/removal related to the stable detection identity; preserves original class, score, geometry, and model provenance | Does not automatically promote AI output | A corrected class does not inherit the original AI score |
| Human annotations | Edit Annotations; draw, move, resize, lock, or delete | HUMAN annotation records and annotation-set hash | Requires Confirm Annotation for lesion readiness | Original-image coordinates are authoritative |
| Reviewer default | **Settings** or any reviewer field; edit and clear **Default reviewer** | Browser-local workstation preference only | None | Not an authenticated identity |
| Autosave | Edit Annotations after a stable edit | Draft annotation save through the existing API path | Never confirms or makes training-ready | Requires a non-empty reviewer and can fail visibly |
| Unsaved guard | Edit Annotations navigation or browser close | No clinical state; prevents accidental loss | None | A completed draft save does not prompt unnecessarily |
| Previous/Next | Review, Clinician Review, and Edit Annotations | Changes route only | None | Never implicitly saves or confirms |
| Save & Next | Edit Annotations | Same draft save as **Save draft**, then next route | None | It is not a sign-off action |
| Next action hint | Major case pages; close or Settings re-enable | Browser-local display preference | None | Guidance only; it does not mutate case state |
| Confirm DR Grade | Clinician Review; select grade and confirm | Final grade, source (`AI_ACCEPTED`, `AI_CORRECTED`, or `MANUAL`), reviewer, timestamp, and review history | Required for DR-ready | Does not require annotation confirmation |
| Confirm Annotation | Edit Annotations | Case-level confirmation, reviewer, timestamp, active annotation-set hash | Required for Lesion-ready | Does not prove absence of lesions or change DR grade |
| Dataset Manifest | **Datasets**; inspect status and export | Versioned manifest, CSV rows, file hashes, and provenance | Shows DR-ready and Lesion-ready independently | Compatibility `include_in_training` is retained but is not the only readiness field |
| Export | **Datasets > Export manifest** | Writes `manifest.json`, `images.csv`, and `annotations.csv` to the Workspace output folder | Exports current state; does not manufacture eligibility | Requires an active Workspace |
| Models & Audit | **Models & Audit**; inspect read-only details | Model readiness, counts, scores, event metadata, source/analysis hashes, and annotation provenance | None | It is an inspection surface, not another task queue |
| CVAT | Optional dense annotation round trip | Remote task/job ids, source hash, analysis hash, imported geometry and provenance | Imported annotations need local finality | Requires private credentials and network access; masks are outside connector scope |

## Confirmation boundaries

The three confirmation labels are intentionally separate:

1. **Confirm Image** confirms the case context and image admission state.
2. **Confirm DR Grade** confirms the clinician's final grade.
3. **Confirm Annotation** confirms the active annotation set at a particular hash.

An ROI correction or removal is an optional edit. It is not a fourth confirmation queue and does not require processing every PRISM suggestion.
