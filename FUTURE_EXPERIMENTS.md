# Future Experiments

Status: **documentation-only probe**. None of the items below are part of the production-critical path for S8.

The deployed product must remain useful without any experiment in this file. Experiments may consume existing provider-neutral interfaces and exported datasets, but they must not silently change clinician workflow, dataset semantics, provenance, or model behavior.

## Guardrails

Future work must preserve:
- human review authority;
- S4 dataset eligibility and `AI only` semantics;
- S5 source/derivative identity and exact payload hashing;
- canonical image-pixel annotation coordinates;
- patient/eye resolver rules;
- frozen clinical review behavior;
- pinned model/checkpoint provenance.

Experimental results are never promoted automatically. Promotion requires an explicit owner decision, a bounded integration plan, regression tests, and updated deployment documentation.

## EXP-1 — Model evaluation harness

**Objective:** compare alternative DR grading or lesion models under one reproducible evaluator without changing the clinician UI.

Reuse:
- provider/model API contract;
- public/synthetic dataset export;
- sealed evaluation patterns where available;
- existing latency and provenance metadata.

Candidate outputs:
- AUROC/AUPRC for binary or multilabel tasks where appropriate;
- QWK for ordinal DR grading;
- confusion/error slices;
- latency, VRAM, model size, failure cases;
- provenance for model revision and checkpoint hash.

Do not select a new production model from one metric alone.

## EXP-2 — Calibration and threshold analysis

**Objective:** determine whether model scores support useful thresholds and whether displayed confidence requires calibration.

Requirements:
- held-out data distinct from model development;
- calibration curves / ECE or task-appropriate alternatives;
- threshold sensitivity analysis;
- explicit distinction between raw model score and calibrated probability.

No production UI may call a score a probability until this work supports that claim.

## EXP-3 — KKU / local-domain adaptation

**Objective:** study domain shift on local retinal imaging while preserving a sealed evaluation set.

Possible approaches:
- frozen-foundation + lightweight head;
- local SSL/domain adaptation;
- carefully bounded fine-tuning.

Requirements:
- de-identification/governance approval before any real clinical data use;
- patient-level split discipline;
- no leakage across tuning and final evaluation;
- baseline against the current frozen production model.

## EXP-4 — Validated attribution / XAI

**Objective:** evaluate whether a validated explanation method can support review of the DR grade model.

Important boundary:
`PRISM lesion detections != RETFound explanation`.

Candidate methods may include attribution or saliency techniques only after method-specific validation. Do not add heatmaps merely for visual appeal.

## EXP-5 — Alternative foundation / grading models

**Objective:** test newer ophthalmic foundation models or task-specific graders behind the same provider-neutral API.

Requirements:
- license and redistribution review;
- reproducible preprocessing;
- checkpoint provenance;
- fair same-dataset comparison;
- compute and deployment footprint report.

## EXP-6 — PACS / DICOMweb connector

**Objective:** add hospital image discovery/retrieval after local DICOM ingestion is operationally stable.

Likely first scope:
- QIDO-RS for study/instance discovery;
- WADO-RS for retrieval;
- no STOW-RS unless an actual workflow requires upload.

Keep PACS credentials, identifiers, and PHI out of logs and model requests. Do not bypass the existing admission/provenance pipeline.

## EXP-7 — Sealed local evaluation

**Objective:** create a prospective or strictly sealed evaluation protocol for a future validated release.

Requirements:
- freeze model/checkpoints before scoring;
- freeze preprocessing and thresholds;
- predefine metrics and exclusions;
- preserve case-level audit trail;
- report uncertainty and failure modes.

## Promotion rule

Any experiment entering the product must follow:

```text
experiment
→ reproducible result
→ owner review
→ explicit promotion decision
→ bounded implementation
→ regression + clinical workflow review
→ release documentation
```

Until that happens, this file is a research backlog only.
