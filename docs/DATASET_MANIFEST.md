# Dataset manifest v2

The Dataset page exports a provenance-preserving package for the active Workspace:

```text
dataset-export-<timestamp>/
├── manifest.json
├── images.csv
└── annotations.csv
```

The current schema identifier is `s4.dataset-manifest.v2`. The export keeps the compatibility fields from the earlier manifest and adds explicit workflow milestones and task-specific readiness. It does not rewrite historical exports.

## Image fields

`images.csv` contains source identity and workflow fields including:

- `image_id`, `filename`, `image_sha256`, `width`, `height`, `modality`, and `source_type`;
- pseudonymous `patient_key`, `laterality`, and resolver methods;
- `modality_admission`, `quality_state`, and `queue_state`;
- RETFound `ai_grade`, model id/version, and `ai_confidence`;
- `clinician_grade`, `grade_review_source`, `reviewer`, and `reviewed_at`;
- human, AI, and CVAT annotation counts;
- compatibility `verification_status`, `include_in_training`, and `eligibility_reason`;
- image milestone fields: `image_confirmation_status`, `image_confirmed_by`, and `image_confirmed_at`;
- DR-grade milestone fields: `dr_grade_confirmation_status`, `dr_grade_confirmed_by`, and `dr_grade_confirmed_at`;
- annotation milestone fields: `annotation_confirmation_status`, `annotation_confirmed_by`, `annotation_confirmed_at`, `annotation_set_hash`, and `confirmed_annotation_hash`;
- task fields: `dr_grade_training_ready`, `grade_eligibility_reason`, `lesion_training_ready`, `lesion_eligibility_reason`, and `training_group_key`.

The `training_group_key` is derived only from a confirmed pseudonymous patient key (`patient:<key>`). No automatic train/validation/test split is created by export.

## Annotation fields

`annotations.csv` contains `annotation_id`, `image_id`, canonical `label`, `shape_type`, `geometry_json`, source, reviewer, timestamp, model provenance, `score`, verification state, and eligibility. Geometry is always expressed in `original_image_pixels`.

AI ROI corrections add `annotation_source=HUMAN_CORRECTION`, `source_detection_id`, `original_label`, `original_score`, and `original_geometry_json`. The corrected row has `score` empty because the original model score belongs to the original AI class. A removed AI detection remains represented for audit with `verification_status=REMOVED` and `include_in_training=false`.

## Task-specific readiness

### DR-grade readiness

`dr_grade_training_ready=true` requires valid source provenance, an included fundus image, acceptable/confirmed image state, a final clinician grade, a reviewer and timestamp, and valid grade provenance (`AI_ACCEPTED`, `AI_CORRECTED`, or `MANUAL`). Annotation confirmation is not required.

### Lesion readiness

`lesion_training_ready=true` requires valid source provenance, an included fundus image, acceptable/confirmed image state, and a current case-level annotation confirmation with reviewer, timestamp, and a hash matching the active annotation set. A final DR grade is not required.

If the active annotations change after confirmation, the confirmation is invalidated until **Confirm Annotation** is performed again. An empty active set can be confirmed as reviewed; it must not be interpreted as proof that no lesion exists.

## Readiness examples

| Case state | DR-ready | Lesion-ready | Meaning |
| --- | ---: | ---: | --- |
| Final clinician grade; no annotation confirmation | Yes | No | Suitable for classification work only |
| Annotation set confirmed; no final grade | No | Yes | Suitable for lesion work only |
| Both milestones confirmed and current | Yes | Yes | Both task outputs meet the current policy |
| AI output only, or excluded/ungradable image | No | No | Needs review or is excluded |

## Compatibility and leakage control

The legacy `include_in_training`, `training_ready_count`, and `eligibility_reason` fields remain for downstream compatibility. New consumers should use the task-specific fields and reasons. An AI-only ROI is never silently promoted to ground truth because it was displayed or included in a case-level review. Human correction, human addition, CVAT import, and untouched AI evidence remain distinguishable.

`manifest.json` also records the coordinate system, canonical lesion taxonomy, policy version, file hashes, and package counts. The package contains no raw PHI by design; validate local privacy policy before export.
