# Gold-reference seed and reviewed candidate expansion

**Proposal / not executed.** The owner intends the 100 carefully physician-reviewed images as a gold-reference seed for similarity matching or other automatic expansion, not merely a 100-image training run. No new image acquisition, similarity inference, embedding/index build, training, export permission or clinician privileges are authorized by this design. The four Admin actions in the supplied progress summary are not evidence of clinician-confirmed gold. The actual seed still needs clinical acceptance and the existing hospital data/export boundaries remain closed.

## Reuse the existing architecture

Use the existing workspace, Worklist, immutable originals, human review history and canonical snapshot exporter. Do not add a second gold CSV/export service. A seed is identified by an approved canonical snapshot/reference, source-state digest, task/policy/taxonomy and source-image SHA inventory. Hospital export is currently blocked, so this design does not assert that a real hospital seed package can already be created/exported. A future owner-approved local seed-reference mechanism must fit the same snapshot provenance and permission contract.

Keep three provenance classes:

| Class | Meaning | Allowed transition |
|---|---|---|
| Physician-confirmed gold | An explicitly eligible human grade and/or reviewed lesion label in an accepted seed snapshot | Remains immutable; corrections create a new clinical revision and later snapshot |
| Retrieved candidate | Similarity/rule retrieval has selected an image, with seed reference, source identity, selection model/version/checkpoint/run and score semantics | Enter review queue; similarity does not provide a gold grade, a negative label or lesion localization |
| Pseudo-label | A separate automated suggestion with its own model/provenance and target image hash | Remains non-gold evidence until actual human review is recorded in the existing case store and a later approved snapshot includes eligible labels |

Candidate acceptance means accepting an image into the review workflow, **not accepting its labels as gold**. Even a candidate record that references completed human review stays candidate provenance; the gold output is a new versioned snapshot derived from the canonical review records. A JSON string claiming CLINICIAN_CONFIRMED cannot authenticate a doctor or establish clinical truth.

## Queue and diversity design — engine/UI integration remains missing

Adapt the existing Worklist rather than creating another queue application. Proposed queue fields: seed snapshot ID, candidate source hash/origin, opaque confirmed patient group and eye/exam, selection run/model/version/checkpoint, score plus score definition, modality/camera/quality when approved, review status, canonical case/revision pointer and admission/export status. Keep actual identifiers and source paths in the protected linkage layer.

Proposed actions map to the existing admission/clinical review: **Accept for review**, **Reject candidate**, **Review/correct image context**, **Confirm human grade**, **Correct/add human ROI**, and explicit **Finish findings**. Accept for review must not execute a grade/annotation confirmation. Label corrections must be drawn/reviewed on the target image in original-image coordinates. Never copy lesion boxes, polygons or segmentation masks from a similar seed image; similarity is not spatial registration or proof of a lesion.

Deduplicate candidates against seed and previously queued images by source SHA256; group the same patient's images/eyes/exams into one review bundle. Multiple legitimate images from one patient can be reviewed, but are one patient group for selection/evaluation accounting. Use a reviewed diversity policy across modality, camera when available, quality, score band and patient group. Do not invent a similarity cutoff or allocate clinical labels from score alone. Sampling audits should include lower-score/random candidates and failure categories, with quotas chosen by the clinical/data owner rather than by this audit.

The selection engine, diversity sampler, candidate persistence/API/UI integration and adjudication-role controls are **not implemented**. The current audit supplies only a proposed JSON record/queue consistency validator and synthetic tests so these boundaries are reviewable before any ML pipeline is added.

## Independent evaluation must be held out before selection

Freeze a separate patient-grouped evaluation snapshot/inventory before building any selection index or tuning thresholds. Its patient groups and source hashes must be excluded from both the gold selection seed and the candidate pool; this includes both eyes, repeat exams, near duplicates and alternate encodings identified by the future deduplication protocol. Exact SHA checks alone do not catch recoded or visually duplicate images, and pseudonymous group resolution must be qualified before claiming independence.

Never consume evaluation images/labels during retrieval, candidate ranking, pseudo-label tuning or selection-model development. Later training experiments must cite seed snapshot, selected/reviewed snapshot, selection model/checkpoint/run and untouched evaluation identity. No training starts in this audit. The held-out metadata check is not proof that an unimplemented index obeys exclusion; engine-level exclusion, query logs and independent evaluation acceptance remain required.

## Proposal files and validation

`gold-expansion-plan.example.json` uses invented synthetic IDs/hashes/score, with seed clinical acceptance PENDING_OWNER and execution NOT_RUN. `scripts/audit/validate_gold_expansion_plan.py` checks provenance class separation, seed linkage, selection model/version/score/source binding, source SHA deduplication, patient grouping, held-out group/image exclusion, no lesion transfer and no automatic gold promotion. It does not read images, a database, environment secrets or any model/API.

```powershell
python scripts/audit/validate_gold_expansion_plan.py docs/audit/gold-expansion-plan.example.json
```

Passing means the proposal is internally consistent, not that a seed is clinically accepted, a model selected it, a hospital authorized export, or similarity expansion was run. Tests include attempted gold promotion, pseudo-label contamination, held-out patient/image leakage, duplicate seed/candidate images, missing model provenance, wrong target hash, transferred lesions, unresolved patient identity, nonfinite score and unsupported confirmation claims.

## Acceptance gate for a future bounded selection project

Require data-steward authorization for the exact local roots and allowed destination; clinical acceptance of the seed and rubric/roles; immutable seed/evaluation inventories with resolved patient groups; reviewed deduplication/diversity policy; a pinned selection model and score definition; a permission/budget-approved inference plan; candidate review queue acceptance/correction coverage; and proof that a later canonical snapshot contains only eligible human labels. Keep hospital export disabled until its separate policy and real-image acceptance are complete. Additional consented UWF/CFP images can be considered after the owner supplies authorized roots and de-identified metadata; this audit does not request, read or acquire them.
