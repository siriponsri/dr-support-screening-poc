# Standalone B0–B8 plan

Owner repository-boundary override supersedes the original V1.1 handoff.
Project: dr-support-screening-poc. Display: DR Support Screening POC.
OcuForge is READ-ONLY. Never merge/push this work into it.

- B0: independent repository, provenance, governance boundary.
- B1: versioned provider-neutral API and explicit offline fixtures.
- B2: CVAT Online REST connector, project 445923, token only from CVAT_TOKEN environment.
- B3: pinned RETFound five-class DR adapter, verified weights, public smoke.
- B4: pinned PRISM-DR released five-fold ensemble, verified weights, public smoke.
- B5: task/image/pre-label/sync; idempotency; offline contract test when token unavailable.
- B6: minimal light English-only Review Queue, Case Review, Annotation, Models UI.
- B7: durable clinician-review round-trip, conflict protection, explicit confirmation.
- B8: final report, runbook, source manifest, ZIP, patch, bundle, commit list.

PASS and PASS_WITH_WARNINGS continue automatically. Missing CVAT_TOKEN defers only live CVAT steps.
GitHub write failure is PASS_WITH_WARNINGS; deliver standalone ZIP and bundle if unavailable.
No WSL, Docker, local CVAT, paid services, training, or private/hospital images.
Ten authorized public HRF DR images are pipeline smoke examples only; no lesion/ordinal GT claim.
UNGRADABLE/UNCERTAIN are states, not grade 5. DME is a separate unsupported task.
UWF is unsupported by these CFP providers. OcuForge may integrate later only via API adapter.
