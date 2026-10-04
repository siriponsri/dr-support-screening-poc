# DR Screening M1 - Phase 4 Execution r3.0

**Prepared:** 2026-10-04  
**Execution baseline:** `80e7460252518a63c88f4ae7d73fb6f0bb5a4d37`  
**Document status:** `OWNER_DIRECTED_EXECUTION_SPEC`  
**Implementation status at entry:** `NOT_STARTED`  
**Phase 1:** `DONE`  
**Phase 2:** `DONE`  
**P3-0:** `DONE / UX FREEZE ACCEPTED`  
**Phase 3:** `DONE / OWNER_ACCEPTED`  
**P3.1 runtime/model-host qualification:** `DEFERRED / NON-BLOCKING`  
**Phase 5:** `NOT_STARTED`

---

## 1. Purpose

Phase 4 turns the physician review state produced by M1 into a reproducible,
traceable, contamination-resistant dataset snapshot for later M2 model
development.

Phase 4 is not a training phase and is not a model qualification phase.
It must work when every AI capability is disabled.

The primary Phase 4 outcomes are:

1. a read-only Workspace Data surface over authoritative review state;
2. explicit DR-grade and lesion readiness with conservative negative semantics;
3. processing, provenance, explainability, and review-completeness inspection;
4. a versioned snapshot/export contract suitable for later model development;
5. strict separation between physician-confirmed labels and AI evidence;
6. a durable receipt that identifies exactly what state was exported;
7. truthful source-origin and export-authorization behavior;
8. evidence sufficient for Phase 5 end-to-end validation.

Phase 4 does not authorize export of hospital data outside an approved boundary.

---

## 2. Authority and required reading before writing code

MAIN/IMPLEMENT/REVIEW must read the current baseline before modifying code.
At minimum:

- `AGENTS.md`
- `DESIGN.md`
- `README.md`
- `docs/milestone/m1/M1_MASTER_PLAN.md`
- `docs/milestone/m1/M1_PHASE2_UWF_LABELING.md`
- `docs/milestone/m1/PRE_PHASE3_CLINICAL_UX_DESIGN_FREEZE.md`
- `docs/milestone/m1/M1_PHASE3_EXECUTION_R3.md`
- `docs/milestone/m1/M1_PHASE3_EVIDENCE.md`
- `docs/milestone/m1/M1_PHASE4_DATASET_REVIEW_EXPORT.md`
- `docs/milestone/m1/M1_PHASE5_E2E_VALIDATION.md`
- `docs/adr/0004-three-human-confirmation-milestones.md`
- `docs/adr/0005-task-specific-dataset-readiness.md`
- the accepted patient/eye/visit identity ADR
- `docs/reference/DATASET_MANIFEST.md`
- `dr_support/services/dataset.py`
- `dr_support/api/dataset.py`
- `dr_support/persistence/*`
- `dr_support/services/workspaces.py`
- `dr_support/workflow.py`
- `dr_support/presentation.py`
- `dr_support/images.py`
- `frontend/src/pages/DatasetsPage.tsx`
- `frontend/src/lib/api.ts`
- current dataset/workspace/PostgreSQL/frontend tests.

The old Phase 4 r2.2 document is historical planning evidence. This r3.0 file is
the Phase 4 execution authority. Do not rewrite historical evidence to make the
current implementation look complete.

---

## 3. Entry state and current-repository reconciliation

The execution baseline is the Phase 3 owner-closeout commit:

```text
80e7460252518a63c88f4ae7d73fb6f0bb5a4d37
```

Phase 3 is closed with model runtime qualification deferred. Phase 4 must not
reopen P3.1 or depend on a live model host.

### R4-A01 - PostgreSQL foundation exists, but current DatasetManifestService is not yet a Phase 4 PostgreSQL snapshot reader

Current PostgreSQL persistence is workspace-scoped through `PostgresCaseStore`
and uses revision-checked JSONB rows. This is authoritative when the application
runs in PostgreSQL mode.

Current `DatasetManifestService`, however, is still structured around application
memory plus `app.state.store`. Its docstring still refers to in-memory admission
and SQLite records. Its image set is derived from in-memory workspace admission
and image IDs rather than an explicit PostgreSQL snapshot of every persisted
workspace case.

Phase 4 must make the read/export path authoritative for the active workspace
without requiring that every persisted case currently has source bytes loaded in
memory.

### R4-A02 - Dataset v2 is a compatibility baseline, not Phase 4 completion

Current schema:

```text
s4.dataset-manifest.v2
policy s8.2-task-specific-v1
```

already provides:

- separate DR and lesion readiness;
- image/grade/annotation confirmation fields;
- original-pixel annotation geometry;
- patient grouping key;
- file hashes;
- compatibility export fields.

Preserve this history and compatibility. Phase 4 must not silently change the
meaning of an existing v2 field.

### R4-A03 - Phase 2 now records Core completeness deliberately

The current clinician finish path writes Core completeness as one of:

```text
REVIEWED_FINDINGS_RECORDED
REVIEWED_NONE_FOUND
```

and binds annotation confirmation to the current annotation-set hash.

This is valuable review evidence. It is not by itself approval to use a zero-row
lesion set as a training negative.

### R4-A04 - Empty confirmed annotation set remains ambiguous for training

ADR-0004 and current Dataset Manifest documentation explicitly state:

```text
empty confirmed annotation set = reviewed
empty confirmed annotation set != proof that no lesion exists
```

Phase 4 must preserve that distinction.

Default Phase 4 policy in this execution:

```text
REVIEWED_NONE_FOUND = review-completeness evidence
negative training eligibility = DEFERRED / NOT AUTHORIZED by default
```

No owner decision is required to continue Phase 4 under this conservative rule.
A future policy may authorize explicit negatives by taxonomy group and version,
but that is a separate versioned decision.

### R4-A05 - Current lesion export has a contamination risk that Phase 4 must close

Current `_annotation_rows()` can mark an active AI lesion row as
`include_in_training=true` when the case-level annotation confirmation is current.
Case-level confirmation does not prove that an untouched AI ROI was individually
accepted as a physician label.

Phase 4 must enforce:

```text
untouched AI suggestion -> never gold
rejected AI suggestion -> never gold
empty AI output -> never negative label
model attention -> never lesion label
explicit human annotation -> candidate gold after applicable confirmation
explicit human correction -> candidate gold after applicable confirmation
clinician-confirmed imported annotation -> candidate gold after applicable confirmation
```

This is a REQUIRED FIX, not a deferred enhancement.

### R4-A06 - Source origin and export permission are separate

Current image objects intentionally keep:

```text
source_type
source_origin
```

separate because Bridge v1 can only serialize PUBLIC/SYNTHETIC while workspace
origin may be WORKSPACE or UNKNOWN.

Current v2 dataset rows primarily expose `source_type`. Phase 4 must carry
truthful source origin separately and must not infer export permission from it.

Default engineering boundary:

```text
PUBLIC       -> engineering snapshot/export allowed if other gates pass
SYNTHETIC    -> engineering snapshot/export allowed if other gates pass
WORKSPACE    -> inspect locally; external/training export authorization not implied
UNKNOWN      -> export authorization blocked
```

Do not invent a permanent hospital-approved origin enum in this phase.
Authorization must be represented separately from descriptive origin.

### R4-A07 - Grouped-by-grade export is an operational utility, not the canonical M2 training snapshot

The current grouped export copies rendered images into grade/ungradable/review
folders. It preserves source immutability and has useful hashes.

Phase 4 must keep this feature compatible if it is still useful, but label it as
an operational/manual organization export. It must not be treated as the
canonical Phase 4 training-ready snapshot because it does not carry the complete
review/provenance policy needed by M2.

### R4-A08 - Local process locking is not a PostgreSQL consistent-snapshot guarantee

Current dataset reads use the store lock. For PostgreSQL this protects one
application process, not concurrent writers in other processes/connections.

Phase 4 must use either:

1. a short-lived PostgreSQL read-only repeatable-read transaction for snapshot
   construction; or
2. an explicit revalidation/retry mechanism with an equivalent consistency
   receipt.

Do not keep a database transaction open while a clinician browses the UI.

### R4-A09 - Durable dataset identity needs more than a timestamp directory

The current export already hashes CSV files, which is good. Phase 4 must add a
stable source-state identity sufficient to answer:

```text
which workspace?
which case revisions?
which policy/taxonomy/schema?
which source state?
which files and SHA-256 values?
when was the snapshot created?
was it eligible/blocked and why?
```

A transient PostgreSQL snapshot token is not a durable dataset ID.

### R4-A10 - Current Datasets UI is list-oriented and lacks record-level audit inspection

The current page shows:

- workspace scope;
- image count;
- annotation count;
- DR-ready and lesion-ready tabs;
- export actions.

Phase 4 must add a compact record detail path for:

- review milestones;
- completeness;
- source/provenance;
- processing details;
- explainability availability/evidence identity;
- readiness reasons;
- current revisions/hashes.

Do not duplicate the Phase 2 clinician review UI.

### R4-A11 - Workspace Data should be queryable without loading the whole workspace into browser memory

Add bounded server-side pagination/filtering for the Phase 4 data surface.
Exact implementation is flexible, but the contract must support at least:

```text
page/limit or cursor
readiness filter
review status filter
laterality
modality
source origin
patient-group presence
text-safe image/case identifier search
```

Avoid expensive unrestricted scans in the browser.

### R4-A12 - Patient grouping must require confirmed identity evidence

A syntactically valid patient key is not enough.

`training_group_key=patient:<key>` must require the current case to have a
confirmed/resolved pseudonymous patient identity under the accepted identity
contract. Do not derive grouping from an unconfirmed candidate or merely from a
string that passes normalization.

### R4-A13 - Persisted metadata remains useful even if source bytes are unavailable

Workspace Data must be able to show a persisted record and its review/export
status even if the source image is currently missing or not loaded.

The UI should show source availability explicitly. Missing source bytes may block
image-copy export but should not erase stored review/audit metadata.

### R4-A14 - AI/model state remains optional

Phase 3 terminal model states are inherited exactly:

- USPEC disabled / artifact-runtime qualification deferred;
- native UWF lesion localization deferred;
- PRISM CFP comparator only, not validated for UWF;
- MONAI deferred;
- Clef comparator deferred;
- longitudinal learned model disabled.

Phase 4 may display recorded AI evidence where it exists, but must not require a
live model service or create new model claims.

### R4-A15 - Phase 4 is the M1-to-M2 data handoff, not an automatic training trigger

A Phase 4 snapshot may later be referenced by an authorized training job.
Phase 4 itself must not:

- start training;
- create train/validation/test splits automatically;
- fine-tune from saved labels;
- replace an enabled model;
- infer clinical negatives from missing labels;
- create referral/DME targets without an approved contract.

---

## 4. Phase 4 product objective

Provide one trustworthy path:

```text
PostgreSQL authoritative review state
-> read-only Workspace Data
-> task-specific eligibility
-> explicit review completeness
-> deterministic snapshot
-> physician-confirmed gold outputs
-> provenance/evidence sidecars
-> durable receipt and file hashes
```

The result must be safe to hand to a future M2 training workflow without forcing
that workflow to guess which rows are physician truth versus AI evidence.

---

## 5. Frozen Phase 4 policy decisions for this execution

These decisions are authorized for Phase 4 implementation and avoid unnecessary
owner interruptions.

### P4-D1 - Gold DR-grade policy

A DR grade may be exported as gold only when all required image/grade gates pass
and grade provenance is one of:

```text
MANUAL
AI_ACCEPTED
AI_CORRECTED
```

with physician reviewer/time and a confirmed current image context.

The original AI score/result remains evidence, not the gold authority.

### P4-D2 - Gold lesion policy

Gold lesion rows may come only from explicit physician-owned state:

```text
HUMAN
HUMAN_CORRECTION
clinician-confirmed imported annotation
```

An untouched AI ROI must never appear in a gold lesion-label file even when the
case-level annotation set has been confirmed.

### P4-D3 - Negative lesion policy

For this execution:

```text
REVIEWED_NONE_FOUND -> completeness evidence only
lesion-negative training row -> NOT AUTHORIZED
```

The export must represent this state explicitly so a future policy can promote
qualified negatives without reconstructing historical clinician actions.

### P4-D4 - Advanced findings

Advanced findings remain optional and must not be silently declared complete.
Only recorded group-level review state may be exported.

No automatic negative is created for an unreviewed Advanced group.

### P4-D5 - Patient grouping

Create a training grouping key only from a confirmed/resolved pseudonymous
patient key.

No automatic train/validation/test split is permitted.

### P4-D6 - Longitudinal data

Phase 4 may expose same-eye visit evidence and acquisition metadata.

It must not infer chronology from visit ordinal alone and must not create
improvement/worsening labels.

### P4-D7 - Hospital/workspace export authorization

Implement the authorization contract and blocked states, but do not authorize
real hospital export in this execution.

Synthetic/public fixtures may be used for full engineering export tests.

### P4-D8 - Model runtime

P3.1 remains deferred. Phase 4 must work with all AI capabilities unavailable.

---

## 6. Phase 4 canonical snapshot contract

Preserve `s4.dataset-manifest.v2` compatibility. Phase 4 may introduce a new
versioned canonical contract, recommended:

```text
s4.dataset-snapshot.v3
```

Exact naming can be refined by MAIN, but it must be a new version and must not
silently reinterpret v2.

Recommended package:

```text
dataset-snapshot-<snapshot_id>/
  manifest.json
  records.csv
  dr_labels.csv
  lesion_labels.csv
  review_completeness.csv
  ai_evidence.csv             # optional, clearly NON_GOLD
```

If MAIN chooses different filenames, preserve the semantic separation below.

### 6.1 manifest.json

Must contain at least:

```text
schema_version
snapshot_id
created_at
workspace_id
workspace_name
application_version
git_commit if available without shell ambiguity
eligibility_policy_version
taxonomy versions
coordinate_system
source_state_digest
case_count
file list
file SHA-256 map
row counts per file
source-origin summary
export-authorization summary
negative-policy status
patient-grouping policy
model-evidence inclusion policy
limitations
```

No secret, DSN, bearer token, absolute patient source path, or PHI.

### 6.2 records.csv

Read-only case/image-level audit and readiness data.

Minimum fields should include:

```text
case/image ID
source SHA-256
source origin
source availability
retinal modality
image confirmation
quality/gradability state
patient-group key if confirmed
laterality
visit evidence status
case revision
DR readiness + reason
lesion-positive readiness + reason
lesion-negative eligibility status + reason
Core completeness state/version/reviewer/time
Advanced completeness state/version/reviewer/time
annotation-set hash
confirmed annotation hash
processing representation/version identifiers when recorded
selected AI evidence identity when recorded
```

Do not expose unnecessary filesystem source paths.

### 6.3 dr_labels.csv

Gold-only classification labels.

Each row must be eligible under P4-D1 and include enough provenance to trace back
to the source/review state:

```text
image/case ID
source SHA-256
DR grade 0-4
grade provenance
reviewer identity or approved local identifier
reviewed_at
case revision
patient-group key if confirmed
policy version
```

Ungradable, Needs Second Review, draft, or AI-only cases are excluded from this
gold file and remain visible in records.csv.

### 6.4 lesion_labels.csv

Gold-only explicit physician lesion labels.

Each row must include:

```text
annotation ID
image/case ID
canonical label
shape type
original-image-pixel geometry
annotation source
reviewer/time
source detection ID if derived/corrected from AI
case/annotation confirmation identity
annotation-set hash
policy/taxonomy version
```

AI-only rows are forbidden from this file.

### 6.5 review_completeness.csv

Preserve group-level review semantics independently from lesion labels.

Minimum fields:

```text
image/case ID
group CORE/ADVANCED
state
reviewer
timestamp
taxonomy_version
case revision
annotation-set hash where applicable
negative_training_authorized = false by default
negative_eligibility_reason
```

This file is the future bridge for explicit negative-label policy without
retroactively guessing clinician intent.

### 6.6 ai_evidence.csv

Optional evidence sidecar. If implemented, it must be explicitly marked
`NON_GOLD` in manifest metadata.

May include:

- raw AI grading evidence;
- raw lesion suggestions;
- model/capability identity;
- inference invocation ID;
- source/analysis hashes;
- explanation identity/status;
- warnings;
- stale/current result status.

It must never be required by a consumer to discover gold human labels.

---

## 7. Source origin, authorization, and destination policy

Phase 4 needs two distinct concepts:

```text
source_origin         # descriptive provenance
export_authorization  # permission for the requested destination/use
```

Suggested authorization states:

```text
ALLOWED_ENGINEERING_PUBLIC
ALLOWED_ENGINEERING_SYNTHETIC
BLOCKED_WORKSPACE_NOT_AUTHORIZED
BLOCKED_UNKNOWN_ORIGIN
BLOCKED_DESTINATION_NOT_APPROVED
```

Exact enum names may differ.

Do not encode clinical/organizational permission by changing source origin.

### 7.1 Preview versus export

Read-only preview of local workspace records may still work when external export
is blocked.

For blocked records:

- show the reason;
- do not copy image bytes to an external/unapproved destination;
- do not mark as training-ready-for-release;
- retain local review state.

### 7.2 Output folder

A workspace output folder is not automatically an approved hospital export
destination.

For current engineering tests, use public/synthetic fixture workspaces only.

---

## 8. Consistent snapshot design

### 8.1 PostgreSQL path

Preferred design:

```text
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY
-> select active workspace cases
-> derive rows from one database snapshot
-> record sorted case_id/revision/payload-digest state
-> compute source_state_digest
-> finish DB read quickly
-> write package files
-> hash files
-> write final manifest/receipt
```

Do not hold this transaction open while a user browses.

If repository architecture makes this impractical, use explicit revalidation:

```text
read revision set
-> build snapshot
-> reread revision set
-> if changed: fail/retry
```

but document and test the chosen algorithm.

### 8.2 SQLite compatibility path

Legacy/test SQLite may use a bounded local lock to materialize all case state.

SQLite compatibility is not evidence that PostgreSQL concurrency behavior is
correct.

### 8.3 Source-state digest

Create a deterministic durable digest from sorted workspace case state, for
example:

```text
SHA256(
  workspace_id
  + sorted(case_id, revision, canonical payload digest)
  + policy/schema identifiers
)
```

Exact encoding must be documented and tested.

A database transaction/snapshot token may be recorded as execution evidence but
must not be the only durable snapshot identity.

---

## 9. Export receipt

Every successful canonical Phase 4 snapshot must create a receipt.

Minimum receipt:

```text
snapshot_id
workspace_id
created_at
schema_version
policy_version
source_state_digest
case revision summary
file hashes
row counts
source-origin summary
authorization status
operator/app identity where appropriate
status SUCCESS/FAILED
```

Preferred persistence is a small append-only PostgreSQL export-receipt record or
an equivalent durable repository-supported ledger, plus the manifest on disk.

If a new table is introduced, use existing migration infrastructure and do not
store raw PHI or source bytes in the receipt.

Failed partial exports must not be reported as successful snapshots.

---

## 10. Workspace Data API

Add a read-only Phase 4 API surface over the active workspace.

Recommended conceptual routes:

```text
GET /v2/workspace-data/records
GET /v2/workspace-data/records/{case_id}
GET /v2/workspace-data/records/{case_id}/processing
GET /v2/workspace-data/records/{case_id}/explainability
GET /v2/dataset/snapshot/preview
POST /v2/dataset/snapshot
GET /v2/dataset/snapshots/{snapshot_id}
```

MAIN may choose another versioned route layout.

Do not make this requirement force a large API rewrite.

### 10.1 Record list

Support bounded pagination and filters.

Return only the fields needed to render the list and readiness status.

### 10.2 Record detail

Show:

- source identity/hash/origin;
- source availability/integrity status;
- patient grouping eligibility;
- laterality/visit evidence;
- review milestones;
- DR grade and provenance;
- annotation confirmation/hash;
- Core/Advanced completeness;
- gold-label counts;
- AI-evidence counts separately;
- readiness reasons;
- current case revision.

### 10.3 Processing details

Use recorded Phase 2/3 state only.

Where available:

```text
Original source SHA
analysis derivative SHA
mask/representation version
transform ID
coordinate mapping
model input identity
selected model/inference identity
```

Show unknown/unavailable honestly.

### 10.4 Explainability details

Separate from processing details.

Show recorded explanation status/evidence identity if present.

Do not create a new attention map or lesion evidence during Phase 4.

---

## 11. Workspace Data UI

The current Datasets page may evolve into the Phase 4 Workspace Data/Dataset
surface, or MAIN may add a closely related route. Avoid duplicate navigation.

Preserve P3-0 UX quality:

- compact hierarchy;
- clinician-safe wording;
- responsive layout;
- no raw exception leakage;
- explicit warning/status beyond color;
- technical details progressively disclosed.

### 11.1 List view

Recommended columns:

```text
image/case
patient group / eye
DR label/readiness
lesion label/readiness
Core completeness
source status/origin
dataset status
```

Do not display raw AI score as the primary dataset state.

### 11.2 Detail drawer/page

Provide tabs/sections:

```text
Review
Processing
AI evidence / Explainability
Dataset eligibility
Raw structured details (secondary)
```

No clinician mutation controls belong here.

### 11.3 Negative-state wording

For zero explicit lesion labels with Core `REVIEWED_NONE_FOUND`, use wording such
as:

```text
Core reviewed - none recorded
Training negative: not authorized by current policy
```

Do not display simply `Lesions: Ready` if that can be interpreted as a verified
negative label.

---

## 12. Gold contamination invariants

These are hard acceptance rules.

### 12.1 DR

Allowed gold:

```text
physician-final grade with valid provenance and current confirmation
```

Forbidden gold:

```text
raw AI grade
stale AI grade
second-review unresolved state
ungradable as grade 0
missing grade as grade 0
```

### 12.2 Lesions

Allowed gold:

```text
explicit human annotation
explicit human correction
clinician-confirmed imported annotation
```

Forbidden gold:

```text
untouched AI proposal
removed/rejected AI proposal
raw model empty output
attention patch
review box
case-level confirmation alone applied to AI ROI
```

### 12.3 Empty set

```text
empty active annotation set
+ confirmed annotation set
+ REVIEWED_NONE_FOUND
```

must remain:

```text
reviewed completeness evidence
```

and not become an exported negative training label under the current policy.

---

## 13. Processing and model evidence invariants

- Original source remains immutable.
- Geometry remains `original_image_pixels`.
- A processing/explanation record must stay bound to source/analysis/model
  identity when those identifiers exist.
- Stale inference history remains evidence only.
- P3.1 model runtime is not reactivated by Phase 4.
- No AI output is recomputed during dataset export unless a later approved phase
  explicitly requires it.

---

## 14. Phase 4 implementation chunks

Use bounded feature worktrees. Do not write application implementation directly
on main.

### Chunk A - Policy, contracts, and contamination fixes

Work items:

- **P4-A1** freeze Phase 4 v3 snapshot schema/policy identifiers;
- **P4-A2** preserve v2 compatibility;
- **P4-A3** fix AI-only lesion leakage into training/gold outputs;
- **P4-A4** add explicit completeness/negative-policy representation;
- **P4-A5** require resolved patient identity for grouping key;
- **P4-A6** add truthful source_origin and separate export authorization;
- **P4-A7** add deterministic source-state digest contract;
- **P4-A8** add focused regression tests for all invariants above.

Review Chunk A before continuing.

### Chunk B - Authoritative Workspace Data reader and UI

Work items:

- **P4-B1** PostgreSQL-aware read-only workspace data reader;
- **P4-B2** bounded pagination/filter API;
- **P4-B3** record detail contract;
- **P4-B4** Processing detail projection;
- **P4-B5** Explainability/AI-evidence projection;
- **P4-B6** compact Workspace Data/Datasets UI;
- **P4-B7** source-missing and blocked-authorization UI states;
- **P4-B8** frontend/backend tests and P3-0 UX regression.

Review Chunk B.

### Chunk C - Canonical snapshot/export and receipt

Work items:

- **P4-C1** short-lived consistent snapshot/revalidation implementation;
- **P4-C2** build `records` data;
- **P4-C3** build gold-only DR label output;
- **P4-C4** build gold-only lesion label output;
- **P4-C5** build review-completeness output;
- **P4-C6** optional non-gold AI evidence sidecar;
- **P4-C7** manifest, file hashes, source-state digest;
- **P4-C8** durable export receipt;
- **P4-C9** failure cleanup/idempotency/prior-export preservation;
- **P4-C10** keep grouped-by-grade export clearly separate and compatible.

Review Chunk C.

### Chunk D - Integration, PostgreSQL proof, browser/UAT evidence, closeout candidate

Work items:

- **P4-D1** exact integrated build validation;
- **P4-D2** PostgreSQL concurrent-revision/snapshot test if an approved local DSN is available;
- **P4-D3** DB/API/UI/export reconciliation on one fixture state;
- **P4-D4** public/synthetic authorization matrix;
- **P4-D5** blocked WORKSPACE/UNKNOWN export tests without real hospital data;
- **P4-D6** browser matrix for Workspace Data/Datasets;
- **P4-D7** restart/reopen evidence where applicable;
- **P4-D8** final evidence/receipt documentation and owner UAT checklist.

If no approved PostgreSQL DSN exists, complete all independent work and record the
live PostgreSQL concurrency execution as `NOT_RUN`; do not manufacture a PASS.

Review Chunk D and prepare the owner-review candidate.

---

## 15. Required test matrix

### 15.1 Readiness policy

At minimum test:

1. confirmed image + final manual grade -> DR-ready;
2. confirmed image + accepted/corrected AI-assisted physician grade -> DR-ready;
3. AI grade only -> not DR-ready;
4. Needs Second Review -> not DR-ready;
5. Ungradable -> not DR-grade gold;
6. confirmed explicit human lesion -> lesion-positive ready;
7. corrected AI lesion -> explicit human correction lineage, ready when confirmed;
8. untouched AI lesion -> never gold;
9. rejected AI lesion -> never gold;
10. zero AI proposals -> not a negative;
11. `REVIEWED_NONE_FOUND` -> completeness preserved, negative export unauthorized;
12. Advanced `NOT_REVIEWED` -> no negative implication;
13. changed annotation hash -> prior lesion confirmation invalid;
14. case-level annotation confirmation alone -> cannot promote untouched AI ROI.

### 15.2 Identity and grouping

Test:

- resolved confirmed pseudonymous patient key -> grouping key;
- candidate/unconfirmed patient key -> no grouping key;
- missing patient key -> no grouping key;
- laterality UNKNOWN remains UNKNOWN;
- visit ordinal alone does not create chronology.

### 15.3 Source and authorization

Test:

- PUBLIC allowed for engineering snapshot;
- SYNTHETIC allowed for engineering snapshot;
- WORKSPACE visible locally but external/training export blocked by default;
- UNKNOWN blocked;
- no source relabeling to bypass authorization;
- source missing after review remains visible but byte-copy operation blocks safely.

### 15.4 Snapshot consistency

Test:

- deterministic digest for identical case state;
- digest changes when an included case revision changes;
- one snapshot cannot silently blend pre/post-concurrent revisions;
- concurrent change causes repeatable-read isolation or explicit retry/failure;
- prior successful export remains unchanged after a later failed export;
- file hashes match final bytes;
- tampered file/receipt is detected by verification logic where implemented.

### 15.5 UI

Test:

- filters/pagination;
- empty state;
- blocked export state;
- record details;
- processing unavailable state;
- explainability unavailable state;
- `REVIEWED_NONE_FOUND` wording does not claim lesion absence;
- no backend path/exception leak;
- keyboard/accessibility basics;
- responsive layouts.

---

## 16. Browser matrix

Use the established responsive contract and at minimum inspect:

```text
1920 desktop if available
1440 desktop
1366 laptop
1280 laptop
1024 tablet/laptop boundary
mobile narrow viewport used by existing regression suite
```

If a width cannot be executed in the available environment, record `NOT_RUN`.

Do not change the P3-0 clinician-review layout merely to make the Dataset page
fit.

---

## 17. Validation commands

Confirm exact repository commands before execution. Expected baseline:

```text
python -m pytest -q
python -m ruff check dr_support tests

cd frontend
npm test
npm run typecheck
npm run build
```

Also run:

- focused Phase 4 backend tests;
- focused dataset contamination tests;
- focused PostgreSQL snapshot tests;
- focused frontend Datasets/Workspace Data tests;
- docs-as-code QA;
- `git diff --check` over the complete Phase 4 range.

The historical root UI smoke may remain separately blocked by missing public HRF
fixtures. Do not weaken tests or create fake fixtures merely to call it PASS.

---

## 18. PostgreSQL acceptance rule

Phase 4 implementation must be PostgreSQL-correct by design.

A live PostgreSQL Phase 4 PASS may be claimed only if an approved DSN/server is
available and the exact integration/concurrency checks are executed.

Otherwise report:

```text
PostgreSQL code/tests: PASS as applicable
Live Phase 4 PostgreSQL snapshot qualification: NOT_RUN
```

Owner may accept the phase with this limitation, as long as it is explicit and
Phase 5 does not convert it into a fabricated PASS.

---

## 19. Security and privacy checks

Before closeout confirm:

- no PHI in Git;
- no real hospital images in evidence;
- no absolute patient filesystem paths in receipts;
- no DSN/password/token in logs or manifests;
- no model weights added;
- export errors are redacted for clinician UI;
- workspace isolation is enforced;
- output paths cannot escape the configured export root;
- filenames derived from source identity are pseudonymous/non-identifying;
- public/synthetic fixtures are clearly identified.

---

## 20. Failure semantics

### 20.1 Snapshot drift

If state changes during a revalidation-based export:

```text
fail/retry the snapshot
```

Never silently mix revisions.

### 20.2 Hash mismatch

If final generated-file hash verification fails:

```text
snapshot = FAILED
preserve previous successful snapshots
remove/quarantine partial new output
```

### 20.3 Authorization blocked

Do not create an external/training snapshot containing blocked source records.
Show a structured reason and allow local read-only inspection.

### 20.4 Missing source bytes

Preserve metadata/review history.
Block only operations requiring the missing bytes.

### 20.5 Policy unknown

Do not guess.
Mark the affected readiness/negative eligibility as unavailable/deferred.

---

## 21. Owner-decision checkpoints

MAIN should not interrupt the owner for ordinary implementation details.
Stop only for a genuine decision that changes product/clinical/privacy scope.

Explicit owner checkpoints:

### OD4-1 - Negative lesion policy expansion

Required only if someone proposes promoting `REVIEWED_NONE_FOUND` to a training
negative in Phase 4.

Default execution decision is NO; keep it deferred.

### OD4-2 - Hospital/workspace export authorization

Required before real hospital/workspace data is released to a training/export
destination beyond the currently approved boundary.

Phase 4 engineering proceeds with public/synthetic fixtures without this.

### OD4-3 - New clinical taxonomy interpretation

Required only if implementation would change Core/Advanced label meaning or
introduce new clinical target classes.

### OD4-4 - Patient/longitudinal inference rule

Required if implementation would infer chronology or identity beyond the
accepted resolver evidence.

No other routine Phase 4 implementation choice should trigger an owner pause.

---

## 22. Review process

Use the same review discipline accepted in prior phases:

- self-audit before review;
- one independent review per integrated chunk if the environment can provide it;
- findings categorized as `BLOCKER`, `REQUIRED FIX`, or `NON-BLOCKING-DEFER`;
- fix in-scope BLOCKER/REQUIRED FIX findings without asking the owner for every
  technical detail;
- re-review changed diff only;
- never simulate reviewer independence if delegation is unavailable.

If independent review cannot be obtained, report MAIN self-audit only and the
reduced independence limitation.

---

## 23. Evidence files

Create/update a small authoritative Phase 4 evidence set, recommended:

```text
docs/milestone/m1/M1_PHASE4_EVIDENCE.md
docs/milestone/m1/phase4/final_phase4_receipt.md
```

Optional machine-readable receipts may live under:

```text
docs/milestone/m1/phase4/
```

but do not dump large raw logs into Git.

Evidence must include:

- starting/final SHA;
- feature/integration SHAs;
- schema/policy identifiers;
- contamination test results;
- snapshot consistency algorithm;
- source authorization matrix;
- frontend/backend validation;
- live PostgreSQL status;
- browser status;
- known limitations;
- reviewer independence status.

---

## 24. Owner UAT after integration

Owner UAT should be short and product-oriented.

Using synthetic/public fixtures only:

1. open the Dataset/Workspace Data page;
2. filter DR-ready, lesion-positive-ready, needs review, excluded;
3. open one record detail;
4. verify review milestones and completeness are understandable;
5. verify `REVIEWED_NONE_FOUND` does not claim a training negative;
6. inspect Processing and AI/Explainability state, including unavailable state;
7. create a canonical snapshot;
8. inspect manifest and gold-label files;
9. verify untouched AI suggestions are absent from gold lesion output;
10. verify file hashes/receipt are shown or inspectable;
11. verify manual operation does not require Model API.

Owner UAT is not clinical validation and does not authorize hospital export.

---

## 25. Phase 4 closeout categories

Report separate outcomes:

```text
Workspace Data read model
DR gold readiness
lesion-positive gold readiness
negative-label policy
snapshot consistency
export authorization
PostgreSQL live qualification
browser/UAT
privacy/security
```

One category's PASS must not imply another.

Expected terminal states may include:

```text
PASS
NOT_RUN
BLOCKED
DEFERRED
NOT_APPLICABLE
```

---

## 26. Phase 4 completion target

Do not mark Phase 4 `DONE` automatically at the end of implementation.

Implementation target:

```text
Phase 4 = READY_FOR_OWNER_REVIEW
```

At that point:

```text
Phase 1 = DONE
Phase 2 = DONE
P3-0 = DONE
Phase 3 = DONE / OWNER_ACCEPTED
P3.1 = DEFERRED / NON-BLOCKING
Phase 4 = READY_FOR_OWNER_REVIEW
Phase 5 = NOT_STARTED
```

After owner acceptance, perform a documentation-only Phase 4 closeout and then
reconcile Phase 5 against the exact final Phase 4 SHA.

---

## 27. Final execution receipt required from MAIN

Return this structure at the end of Phase 4 execution:

```text
Starting SHA:
Feature candidate SHA:
Integrated main SHA:
Final evidence SHA:

Chunk A:
Chunk B:
Chunk C:
Chunk D:

Snapshot schema:
Eligibility policy:
Negative policy:

AI-only lesion contamination test:
Reviewed-none handling:
Patient grouping rule:
Source-origin/export authorization:
Snapshot consistency mechanism:
Source-state digest:
Export receipt:

Backend tests:
Ruff:
Frontend tests:
Typecheck/build:
PostgreSQL Phase 4 live qualification:
Browser matrix:
Documentation QA:
Full-range git diff --check:
Independent review status:

Known limitations:

Phase 4: READY_FOR_OWNER_REVIEW
Phase 5: NOT_STARTED
Git/main/origin status:
Project Brain status:
```

Final marker:

```text
PHASE 4 READY_FOR_OWNER_REVIEW
```

---

## 28. Explicit non-goals

Phase 4 must not:

- set up Tailscale;
- set up the team GPU server;
- load USPEC weights;
- reopen Phase 3 runtime qualification;
- run Clef/MONAI experiments;
- train or fine-tune a model;
- perform automatic train/validation/test split;
- authorize production deployment;
- authorize hospital-data export;
- invent new clinical referral or DME rules;
- treat reviewed-none as an approved negative without a new owner decision;
- make the Dataset page a second clinician-labeling workflow.

---

## 29. Handoff to Phase 5

Phase 5 must consume from Phase 4:

- exact snapshot schema version;
- exact eligibility policy version;
- negative-policy status;
- source authorization behavior;
- snapshot consistency mechanism;
- source-state digest algorithm;
- final public/synthetic fixture identities;
- export file/hash reconciliation evidence;
- known PostgreSQL/browser limitations;
- exact integrated Phase 4 SHA.

Phase 5 must validate the actual integrated M1 product, not a separate demo
implementation.

Do not start Phase 5 implementation during Phase 4 execution.

---

# End of Phase 4 Execution r3.0
