# S5 Medical Imaging Package

**Project:** DR Support Screening POC  
**Milestone:** S5 — Medical Image Ingestion & Data Integrity  
**Baseline main:** `9067ed91672a40bf1a326b84f83f13021c2f51c0`

## Objective

S5 extends the current retinal-image workflow into a safer medical-imaging ingestion layer while preserving frozen S1–S4 behavior.

Hero objective:

> A retinal source image — including a supported ophthalmic DICOM object — can be ingested without modifying the source, decoded at the highest defensible fidelity needed by the workflow, displayed safely in the browser, analyzed through the existing model path when compatible, and exported with provenance tracing back to the authoritative source bytes.

Direct PACS/DICOMweb connectivity is deferred until local DICOM ingestion and provenance are stable.

## Execution model

Use one short foundation lane first, then three parallel feature lanes.

```text
main + S5 docs
      |
      v
feat/s5f-imaging-foundation
      |
      v
main (foundation merged)
      |
      +--> feat/s5a-integrity-core
      +--> feat/s5b-dicom-ingest
      +--> feat/s5c-derivative-delivery
      |
      v
main integration
      |
      v
WS05 owner acceptance
      |
      v
S5 FROZEN
```

## Package files

- `S5_MASTER_SPEC.md`
- `S5_FOUNDATION_SPEC.md`
- `S5A_INTEGRITY_CORE_SPEC.md`
- `S5B_DICOM_INGEST_SPEC.md`
- `S5C_DERIVATIVE_DELIVERY_SPEC.md`
- `WS05_ACCEPTANCE_PLAN.md`
- `S5_PARALLEL_INTEGRATION_PLAN.md`
- `S5_MAIN_ORCHESTRATOR_PROMPT.md`
- `S5_GOAL_PROMPTS.md`

## Frozen baseline

S5 must preserve:

- S1 viewer and annotation geometry semantics;
- S2 Workspace behavior;
- S2A1 conservative admission;
- S2A2 patient/eye resolver;
- PRE-S3 remote Model API boundary;
- S3 Worklist UX;
- S4 dataset/provenance/training-eligibility semantics;
- original image immutability;
- human review as authoritative.

## Terminology

Use these terms precisely:

- **source bytes**: exact original file bytes;
- **source SHA-256**: hash of exact source bytes;
- **decoded master**: highest-fidelity decoded representation available to the app;
- **display derivative**: browser-safe representation;
- **analysis payload**: exact bytes sent to the Model API;
- **analysis SHA-256**: hash of those exact payload bytes.

A decoded derivative may be lossless relative to decoded pixels while the source DICOM itself may already contain lossy-compressed pixel data.
