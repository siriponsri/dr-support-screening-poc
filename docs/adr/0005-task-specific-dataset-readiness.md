---
status: Accepted (retrospective)
date: 2026-09-23
---

# ADR-0005: Use task-specific dataset readiness and no automatic split

## Context and problem statement

A case can have a final grade without reviewed annotations. A single *ready* flag either blocks useful grade data or leaks unreviewed lesion data.

## Considered options

- One readiness flag
- Separate DR-ready and Lesion-ready states, patient-key grouping, and no automatic train/validation/test split

## Decision outcome

`services/dataset.py` computes DR-ready and Lesion-ready independently (policy `s8.2-task-specific-v1`, schema `s4.dataset-manifest.v2`). It exports `training_group_key` from the pseudonymous patient key and states `grouping_policy: patient_key_only; no automatic train-validation-test split`.

### Consequences

- Good: each task uses only the evidence it needs; future experiments can split by patient.
- Bad: consumers must read two flags; splitting is left to experiment code.

## More information

`docs/DATASET_MANIFEST.md`, `tests/test_dataset.py`.
