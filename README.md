# DR Support Screening POC

Independent, public/synthetic clinician-review proof of concept.
RETFound grade suggestions → PRISM-DR lesion suggestions → clinician review → CVAT Online.

This project has its own Git history, model API, runtime, and release lifecycle.
OcuForge is a read-only architecture reference, not a dependency or destination for these commits.
No frozen OcuForge scientific artifacts, research code, datasets, or results are included.

See [the plan](docs/MASTER_PLAN.md) and [provenance](docs/PROVENANCE.md).
Research-only AI suggestions require clinician review. No diagnosis or autonomous referral.

Current UI profile: KKU clinical palette using Red Soil `#A73B24` for product chrome; lesion colors remain a separate high-contrast annotation palette. Raw lesion model output is retained, while the clinician overlay/CVAT pre-label set is bounded by configurable review thresholds and caps.

## Open the delivery

Extract the ZIP into a new folder. Double-click `PREVIEW.html` to inspect all ten public samples
and recorded real-model suggestions for 01_dr without installing anything. The preview cannot
run models or record reviews.

For live inference/review on a Python-capable developer host, see
[LOCAL_RUNBOOK.md](docs/LOCAL_RUNBOOK.md); Windows entrypoint: `START.cmd`.
The restricted owner workstation can remain browser-only when a developer hosts the API later.

## v0.1.2 live CVAT overlay patch

The live backend round-trip has been observed on CVAT Project `445923`. After syncing clinician edits, the Annotation canvas now shows imported CVAT corrections as the primary solid geometry and preserves original AI boxes as dashed/faded provenance. `START.cmd` also supports a uv-managed Python 3.12 fallback when Windows `py -3.12` is unavailable.
