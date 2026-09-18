# DR Support Screening POC

Independent, public/synthetic clinician-review proof of concept.
RETFound grade suggestions → PRISM-DR lesion suggestions → clinician review → CVAT Online.

This project has its own Git history, model API, runtime, and release lifecycle.
OcuForge is a read-only architecture reference, not a dependency or destination for these commits.
No frozen OcuForge scientific artifacts, research code, datasets, or results are included.

See [the plan](docs/MASTER_PLAN.md), [V2 implementation plan](docs/V2_IMPLEMENTATION_PLAN.md), and [provenance](docs/PROVENANCE.md).
Research-only AI suggestions require clinician review. No diagnosis or autonomous referral.

Current UI profile: neutral premium clinical aesthetic with a subtle red-soil accent (`#A73B24`).
Lesion overlay colors remain an independent high-contrast annotation palette.

## Open the delivery

Extract the ZIP into a new folder. Double-click `PREVIEW.html` to inspect all ten public samples
and recorded real-model suggestions for 01_dr without installing anything. The preview cannot
run models or record reviews.

For live inference/review on a Python-capable developer host, see
[LOCAL_RUNBOOK.md](docs/LOCAL_RUNBOOK.md); Windows entrypoint: `START.cmd`.
The restricted owner workstation can remain browser-only when a developer hosts the API later.

## V2 clinician-first redesign

The interface is now organized around three views:

1. **Worklist** — select a case and see review status at a glance.
2. **Case Review** — the hero experience: large retinal image viewer, AI grade suggestion,
   lesion overlay, per-class filters, and a right-side AI Review panel.
3. **Models & Audit** — provider readiness, provenance, and limitations.

Primary clinician workflow:

- Open a case from the Worklist.
- Click **Analyze** (or review pre-computed suggestions) to generate the grade and lesion findings.
- Inspect the retinal image with zoom, pan, and lesion overlays.
- Record a decision: **Accept**, **Adjust Grade**, **Needs Annotation**, or **Escalate**.
- Use **Advanced Edit** only when geometry-level correction in CVAT Online is necessary.

CVAT integration remains intact underneath: Advanced Edit prepares the CVAT task, pushes the
bounded pre-label set, and opens the CVAT job. Synced corrections are imported back into the
case and shown as solid geometry over the original AI suggestions.

## v0.1.2 live CVAT overlay patch

The live backend round-trip has been observed on CVAT Project `445923`. After syncing clinician
edits, the Annotation canvas shows imported CVAT corrections as the primary solid geometry and
preserves original AI boxes as dashed/faded provenance. `START.cmd` also supports a uv-managed
Python 3.12 fallback when Windows `py -3.12` is unavailable.
