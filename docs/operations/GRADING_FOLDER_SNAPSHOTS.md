# Grade-organized image snapshots

Status: local organization of already authorized sources is implemented.
The 22 October owner authorization permits local hospital demo copies; this is
not permission for network transfer. Live deployment evidence and clinician UAT
remain separate qualification gates.

## Daily workflow

Open Datasets, then **Preview grading folders**. Inspect Grade0–4, UNREVIEWED,
UNGRADABLE and UNDETERMINED counts, estimated copy size, duplicate records and
skipped reasons. **Create grading-folder snapshot** becomes available only for a
supported backend, an authorized Workspace and at least one verified source.
The operation copies original bytes into a new `dataset-snapshot-ID` package.
The completion notice identifies that package; prior snapshots and originals
stay unchanged after a later grade revision.

Grade0–4 requires the existing grade-ready policy plus an explicit current
CONFIRMED numeric human review, accepted review action, reviewer, timezone-aware
timestamp, valid revision and matching original-source hash. Missing legacy
provenance goes to UNDETERMINED. AI-only records go to UNREVIEWED; an AI suggestion
never assigns a numeric folder. Ungradable and second-review states remain
non-numeric. No clinical decision, privilege or referral record is created.

Folder membership organizes recorded review data. It does not establish clinician
credentials, clinical validity or lesion readiness. Grade and lesion label
completeness stay independent, and reviewed-empty lesions remain unauthorized as
training negatives. Resolve old/missing confirmation through the normal authorized
review workflow; do not edit DB records to force an export.

## Reuse of the canonical snapshot

The existing `s4.dataset-snapshot.v4` package, source-state receipt and separate
human/AI CSVs are retained. The opt-in adds:

```text
dataset-snapshot-ID/
  manifest.json
  receipt.json
  records.csv, dr_labels.csv, lesion_labels.csv, ...
  grading_folders/
    manifest.json
    Grade0/ ... Grade4/
    UNREVIEWED/ UNGRADABLE/ UNDETERMINED/
```

Only used image groups are created. Folder filenames use content-hash prefixes,
extended on collision; original patient/source filenames never determine output
paths. Full SHA256, case/review revisions, opaque record/annotator keys and hashed
patient/exam grouping are recorded in the grading manifest. Identical content in
one group is copied once with separate alias records. Conflicting confirmed grades
or confirmed patient identities on the same content are held in UNDETERMINED.
There is no automatic patient split or similarity label propagation.

Source identity/integrity, supported admission and source availability are checked
before planning copies. Unsupported or missing sources have explicit skip reasons.
Strict numeric-folder selection also governs `dr_labels.csv` in this opt-in
package; skipped sources supply no gold label files. Independently confirmed
lesions may remain eligible on a copied UNREVIEWED-grade image. AI evidence stays
in `ai_evidence.csv` as non-gold. Metadata-only snapshots retain existing behavior.

PNG/JPEG/TIFF/DICOM source bytes can be copied without transcoding. This preserves
embedded metadata and burned-in content; it is not a de-identification operation.
Existing canonical metadata CSVs may also contain source names or pseudonymous
identifiers. Export authorization and hospital privacy policy remain mandatory.
WORKSPACE and UNKNOWN export lanes remain blocked. HOSPITAL_AUTHORIZED local
copies require matching recorded source authorization and integrity. No endpoint
grants authorization to a previously unknown source.

## API and consistency

GET `/v2/dataset/snapshot/preview?include_grade_folders=true` returns counts,
copy bytes, skips and a deterministic grading plan SHA256. It writes nothing.
POST `/v2/dataset/snapshot` uses:

```json
{
  "include_grade_folders": true,
  "expected_workspace_id": "workspace-id-from-preview",
  "expected_source_state_digest": "64-hex-digest-from-preview",
  "expected_grading_plan_sha256": "64-hex-digest-from-preview"
}
```

Server recomputation rejects changed source/label/scope inputs before writing.
An older backend without grading-folder preview support cannot be used silently.
The default empty-body snapshot request still creates metadata only. No endpoint
accepts source moves, deletion or an override of hospital authorization.

## Completion, recovery and integration limits

Snapshots are created exclusively with new IDs. A name collision preserves the
existing directory. Writes use exclusive file creation and confined generated
paths, reject redirected roots, check free-space estimates and verify all output
hashes. `receipt.json` is written last as the success marker; an in-progress
directory without a complete matching receipt is not a completed dataset.
Planning manifests retain their planned-copy status; the root SUCCESS receipt is
the completion record. Ordinary failures clean only the directory created by that
operation. Sudden process/power loss can leave an incomplete directory; automated
crash cleanup, durability and network-filesystem behavior are not qualified here.

Windows output roots must be short enough for the complete generated paths; an
excessive path is rejected before writing. No registry/ACL/long-path setting is
changed. Keep input and output directories separate so copied snapshots cannot be
rescanned as new originals. On a timeout, inspect the output and completion receipt
before deliberately starting another new snapshot; there is no automatic retry.

The older **Export grouped images** tool still updates its shared legacy folder
and is labelled separately in the UI. Use the new snapshot option when revisions
must not relocate or merge previously exported groups. The implementation extends
the existing exporter rather than creating a parallel export service. No DB
migration is required; rollback of this feature must preserve existing snapshots.
