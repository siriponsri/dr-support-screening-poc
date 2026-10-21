# Hospital annotation and training-data traceability


Current correction status: [Final bounded follow-up](FINAL_COMPARISON_PROVENANCE_RESPONSE.md) supersedes earlier round counts and open-comparison/draft status below. The four P1 mechanisms were independently re-reviewed at de5cfd3; follow-up validation and remaining limits are recorded in the final handoff. Clinical UAT remains pending.
This app is both a fast review workstation and a hospital-owned annotation/dataset collection system. The 100 carefully physician-reviewed images are intended as a gold-reference seed for similarity matching or other automatic expansion; they can also produce separate grading and lesion label sets; neither image count, AI inference, Admin actions nor a saved DB row alone establishes clinical ground truth or permission to export/train.

## Evidence boundary

Source: [Project Progress sheet](https://docs.google.com/spreadsheets/d/1eL3VCplj0MuLTTJwlTxB2sCf9kGvpH8Mu32EggN1U_k/edit). Parent read A1:L100 and supplied its verified summary: 27-task progress summary of the 24 September meeting, updated 16 October; **not raw meeting minutes**. This matrix maps the requirements in that supplied summary, not independently retrieved sheet cells or invented row numbers. Labels below distinguish implementation tests from clinical acceptance. No privileges were assigned, hospital export enabled, data transmitted, or model trained.

## Feature matrix

| Requirement from supplied progress summary | Status in this candidate | Code / proof | Remaining decision or qualification |
|---|---|---|---|
| Human decisions distinct from AI suggestions | Implemented and synthetic-tested | `services/dataset.py`, `_annotation_rows`; `test_training_readiness_audit.py`: untouched AI never gold, human correction keeps original score separately | Real clinician UAT; authenticated clinical role/identity not established by test names |
| Explicit five-grade DR labels | Implemented and hardened with synthetic tests | `_final_grade` rejects booleans, strings, floats, out-of-range grades, explicit non-confirmed status, mismatched cache/review and non-grade actions | Legacy records lacking explicit status/action retain compatible treatment; validate their provenance during owner integration |
| Admin actions are not physician grade confirmations | Present, clinical acceptance pending | Source summary says four Admin actions are not clinician-confirmed; exporter tests reject non-grade review actions | No inference that existing Admin-reviewed real cases are ground truth; role policy/authentication needed |
| Grading and lesion readiness independent | Implemented and synthetic-tested | `_task_reason`, `_rows`; grade-only and lesion-only fixture | UI routine annotation entry currently follows confirmed grade even though dataset task readiness is independent; detailed annotation-only UX needs product/clinical decision |
| Empty/unreviewed distinct from reviewed-none | Implemented and synthetic-tested | Core completeness state and negative policy remain separate; empty successful ROI message explicitly not negative | Clinical owner must define any gold-negative policy/version; current `negative_training_authorized=false` stays |
| Current lesion confirmation must match geometry | Implemented and hardened with synthetic tests | Recompute `annotation_set_hash` from active shapes; stale cached hash fixture is ineligible | PG-backed concurrent write/source reconciliation NOT RUN |
| Editable ROI boxes and original coordinates | Present; frontend geometry tests and exporter rectangle fixture | AnnotationEditorPage, RetinalCanvas, geometry tests; `original_image_pixels` in snapshot | Clinical review of all 100 images, boundary quality and scale equivalence on real cameras |
| Polygon/point/circle annotations | Present; existing frontend geometry coverage | AnnotationEditorPage and annotation schemas | No claim these are pixelwise segmentation masks |
| Editable lesion segmentation masks | Missing | No qualified brush/pixel-mask lesion editor identified | Define lesion mask ontology, file encoding and original↔analysis transform acceptance before adding |
| Approved FOV distinct from lesion masks | Present processing separation; approval workflow incomplete | Processing details / analysis-field overlay; FOV is processing evidence, not `lesion_labels.csv` | Owner approval route for four prior UWF examples still missing; do not assume approval or use FOV as lesion truth |
| Label ontology/version | Implemented for four classes; synthetic snapshot-tested | `canonical-v1`, MA/HE/EX/SE and completeness policy versions in manifest | NV and quadrant-count rubric remain pending; no verified NV detector or labels invented |
| Quality/ungradable/unsupported | Implemented guards and synthetic type/status tests | Ungradable never exported as numeric grade; unsupported UI says manual review | Image quality rubric/camera-specific acceptance needs clinical owner |
| Annotator identity and revision history | Present; provenance fields synthetic-tested, persistence unverified here | reviewer/time, case revision, annotation hashes, review history, source-state digest | Local self-declared reviewer is not authenticated clinician privilege; independent annotator/adjudication roles need policy |
| Snapshot and manifest architecture | Existing architecture reused; synthetic package tests | `s4.dataset-snapshot.v4`, `s4.dataset-manifest.v2`; source-state digest, per-file hashes and row counts | No second exporter; full PostgreSQL/DB↔UI↔package acceptance NOT RUN |
| Hospital export disabled | Preserved and synthetic-tested | `_export_authorization`, export guard raises before directory creation; UI snapshot button disabled with truthful reason | Hospital permissions/allowed destinations/privacy minimization contract must be approved separately; no real-image export acceptance |
| Grading and lesion files contain eligible human labels only | Synthetic package-tested | `dr_labels.csv`, `lesion_labels.csv`, separate NON_GOLD `ai_evidence.csv`; reviewed-negative absent from gold | Only synthetic in-memory fixtures exported to temporary files; not a training-ready real-hospital release |
| Source hashes, model/revision provenance | Present; synthetic-tested | source SHA, case revisions, detection/model evidence, annotation hash and file hashes | Snapshot contains metadata/labels only, not originals; full original-byte inventory/backup/restore NOT RUN |
| Leakage-resistant patient/eye/exam grouping | Confirmed-key rule synthetic-tested; grouping acceptance pending | `training_group_key=patient:<pseudonymous key>` only when resolved; laterality/visit fields in records | Keep all images/eyes/exams of one patient in one split when a future approved trainer assigns splits. No automatic split now; unlinked identity must be held for resolution |
| Identity privacy | Present hospital-export block; future design decision | Hospital guard prevents package creation. No actual identifiers used in this audit | Existing allowed engineering schema carries filenames/pseudonymous keys; do not claim automatic PHI removal. Hospital export needs steward review of opaque IDs, camera/DICOM metadata and linkage protection |
| Reproducibility | Synthetic-tested for stable content, not identical timestamps | Two snapshots have distinct IDs but same source-state digest and label-file hashes | Preserve release/policy/taxonomy/snapshot identity in future training run; no training started |
| Previous exam side-by-side | Present but not requalified in this dataset audit | ReviewPage and comparison service | No registration, progression claim or lesion matching. Same-case comparison request races remain separately tracked |
| Hospital camera metadata and workflow roles | Missing/clinical decision needed | Existing visit/source fields are insufficient for a qualified camera/domain protocol | Data steward/clinical owner define camera, acquisition, annotator/adjudicator roles and allowed destinations |
| Full backup and isolated restore | Guidance/template only; NOT RUN | `WEB_DEPLOYMENT_HANDOFF.md` includes originals outside DB and separate target procedure | Operator-qualified full restore and hash/count/revision reconciliation required |

## Workflows using the same records and exporter

**Fast screening (proposed product path; partial current behavior).** Confirm image/context → inspect original and optional AI → explicitly confirm human grade → return to queue with lesion review still pending. Dataset reports grade readiness separately. An untouched or empty ROI list never marks lesion review finished. Current UI automatically advances into Annotation Editor after confirming grade; a clearly labeled defer-lesion/return-to-queue action is a product proposal, not implemented/clinically accepted here. No human decision is automated.

**Detailed annotation collection (existing core path, qualification pending).** Confirm source/context and quality → explicit grade when that task is performed → inspect every region at original-image scale → correct/add human findings with provenance → finish Core review deliberately → resolve uncertainties via the accepted review process → inspect task-specific readiness and authorization → create the existing canonical snapshot only for an authorized scope. Advanced/NV/quadrants and lesion masks remain deferred until their rubric is approved. Annotation-only task readiness already exists at the dataset level; do not fake a numeric grade merely to access an annotation workflow.

For a 100-image collection, retain the exact image inventory and immutable originals outside the DB, grade labels, lesion labels, reviewed completeness, source/annotation hashes, annotator history, policy/taxonomy versions and patient/eye/exam linkage. Different tasks may have different eligible counts. An export must explain those counts rather than fill missing grades with 0 or turn unreviewed empties into negatives.

## Reproduced exporter defects and proof

Against the original source snapshot, 20 of 35 new in-memory synthetic checks fail; 15 already pass. The failures are invalid/nonconfirmed/cached grade eligibility and trusting a stale cached annotation hash. Candidate reuses the same exporter and narrows acceptance of malformed/stale data; schemas, clinical grade thresholds and hospital/negative authorization rules are unchanged. Test harness does not import `create_app`, open a DB, call any inference endpoint or load a model. Existing API/database tests remain present but were not executed as part of this permission-bounded audit.

Reproduce from the isolated repository using the already available interpreter and a fresh writable temporary directory:

```powershell
python -B -m pytest tests/test_training_readiness_audit.py tests/test_web_deployment_plan.py -q --basetemp <fresh-workspace-temp-directory>
```

Do not use a live clinical database or the other team's acceptance schema to replace this in-memory proof. Frontend regression tests and screenshots do not constitute clinical UAT.


## Gold-seed expansion clarification

See `GOLD_SEED_EXPANSION_DESIGN.md` and the proposal-only `gold-expansion-plan.example.json`. These extend the requirement mapping without enabling a new ML pipeline.

| Additional owner requirement | Status | Evidence / gap |
|---|---|---|
| 100 physician-reviewed images as gold-reference seed | Design and acceptance gates documented | Existing Admin actions do not qualify the seed; clinician acceptance and protected local snapshot/reference still pending |
| Gold, retrieved candidates and pseudo-labels remain distinct | Proposal consistency validator and synthetic tests implemented | Not an installed API/schema migration or clinical authentication mechanism |
| Seed snapshot + selection model/version/score + target source lineage | Proposal metadata validated | No selection run, inference, model load or image acquisition |
| Image/patient deduplication and diversity | Exact SHA and patient queue grouping validated in proposal; queue/diversity design documented | Near-duplicate detection, camera metadata, sampling engine and actual Worklist integration missing |
| Independent patient-grouped evaluation not used for selection | Proposal rejects seed/candidate overlap by group and source hash | Engine/index exclusion and true identity linkage require future qualification; no evaluation consumed |
| Candidate acceptance/correction queue | Existing Worklist reuse designed; canonical human grade/ROI review already exists | Candidate fields/actions/persistence integration not implemented; candidate acceptance never confirms labels |
| No lesion transfer from similar images | Explicit prohibition validated | Target-image manual localization/qualified target model remains necessary; no geometry was transferred |
| No automatic candidate/pseudo-label promotion to gold | Proposal rejects promotion; existing exporter still admits eligible human rows only | Gold comes from a later approved snapshot after actual human review, not from this validator |
