# DR Support Screening POC — B0–B8 delivery

The standalone implementation is complete with warnings. This is a research POC, not a clinically validated screening service. Live CVAT execution and GitHub publication are not complete.

| Gate | Result | Evidence / limitation |
|---|---|---|
| B0 | PASS | Independent Git repository and lifecycle; OcuForge retained read-only; provenance documented. |
| B1 | PASS | Provider-neutral validated Model API, explicit fixture providers, unsupported modality handling. |
| B2 | PASS_WITH_WARNINGS | CVAT Online REST connector restricted to project 445923; environment-only token; live authentication unavailable. |
| B3 | PASS_WITH_WARNINGS | Real RETFound five-class checkpoint smoke on public 01_dr; grade 2 suggestion; uncalibrated, research/noncommercial restrictions. |
| B4 | PASS_WITH_WARNINGS | Real PRISM five-fold pipeline smoke retained 200 raw lesion suggestions; clinician overlay/CVAT pre-label now uses a separate configurable bounded review view. All 21 released weights verified; HRF domain and license limitations documented. |
| B5 | PASS_WITH_WARNINGS | Durable review state, idempotent sync, import and explicit confirmation tested against remote fixtures; live CVAT round-trip pending. |
| B6 | PASS_WITH_WARNINGS | English-only KKU clinical theme applied; ten public HRF images and offline preview included. Lesion colors are separate from KKU product chrome. |
| B7 | PASS_WITH_WARNINGS | Owner audit patch: 17 backend/contract/workflow tests passed; optional real-Chromium preview smoke is present but skipped in this host because Chromium navigation is blocked by administrator policy. JavaScript syntax passed; no clinical accuracy evaluation or live CVAT test claimed. |
| B8 | PASS_WITH_WARNINGS | Source ZIP, local gate commits, complete standalone Git bundle and patch; no GitHub repository-creation capability or configured standalone remote. |

## Recorded evidence

See RETFOUND_SMOKE.json, PRISM_SMOKE.json, SAMPLE_MANIFEST.json and VERIFIED_RUNTIME.json. Examples contain actual recorded model responses. Only 01_dr has recorded real model inference; the remaining nine public images are available for runtime inference. Synthetic responses are visibly identified and never replace failed real model calls.

## Remaining owner/runtime actions

- Run the API on a permitted Python host; START.cmd requires Python 3.12. Restricted browser-only machines can open PREVIEW.html but cannot run inference or save reviews.
- Supply CVAT_TOKEN in the host environment and perform a live send/edit/save/sync/confirm round-trip. Never paste the token in chat or commit it.
- Review model license restrictions before use beyond this research POC. Deployment with identifiable patient data is outside scope.
- Create an independent GitHub repository when available and restore/push the included standalone bundle. No push to OcuForge was attempted after the boundary override. The final B8 publication check found no standalone remote and no repository-creation capability; therefore no network push could run.

## Boundary and release integrity

OcuForge main and scientific R1/R2/R3 artifacts were not modified by this standalone implementation. Its pre-override local history remains preserved separately as audit material. No OcuForge research code, scientific datasets or contracts are included in this standalone project. Model upstream sources and large weights are retrieved independently by the setup script and excluded from delivery. The ten HRF images are public smoke data with recorded hashes and provenance, not DR-grade ground truth.

The UI reviewer name is a self-declared audit field, not authenticated clinician identity. Runtime is bound to localhost and intended for one process; production authentication, multi-user hosting and clinical validation remain outside scope.

COMMIT_SHAS.txt in the delivery records all nine gate commits, including B8. The bundle contains the complete independent history; main retains B0 while feat/bridge-poc contains the implementation.

## Owner audit hardening v0.1.1

See `OWNER_AUDIT_V0_1_1.md` and `UI_THEME.md`. Added explicit geometry behavior, raw-vs-review lesion separation, configurable caps, review action guards, repository-level licensing notices, and KKU customer theme. Live CVAT remains the only required acceptance action before promoting the integration lane to PASS.


## Owner live CVAT patch v0.1.2

Owner live testing on CVAT Project `445923` proved that clinician-edited geometry was imported into the backend and changed from the original AI box while the case moved to `IMPORTED_REQUIRES_REVIEW`. v0.1.1 had a presentation-only defect: the Annotation canvas continued drawing the original AI review subset. v0.1.2 renders imported CVAT geometry as the primary solid overlay and preserves original AI rectangles as dashed/faded provenance. See `LIVE_CVAT_ACCEPTANCE.md`.

Current gate: **PASS_WITH_WARNINGS** pending owner visual re-check of the v0.1.2 overlay and explicit confirmation of the imported annotations.
