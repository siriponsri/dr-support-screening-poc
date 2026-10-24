# Hospital M1 amendment: recorded source identity on review cases

Status: **OWNER APPROVED 2026-10-24 (chat) — Part A and Part B, Part B scoped to
`ws_m1_63ed86c7d44f46d59479` only.** Drafted 2026-10-24 by Claude Code after the
QA_SERVER session (see [HANDOFF section 25](../../../HANDOFF.md)). The approval
covers implementation on a bounded `fix/` branch and the Part B dry run; the
Part B apply still needs the owner's approval of the exact plan SHA-256. It
authorizes no GPU window or model-host session.

## 1. Problem

The protected PRISM path refuses every case created by ordinary Workspace
admission. `POST /v1/cases/{image_id}/prism-input-preview` returns 503
"Recorded source attestation is unavailable; no model work is permitted."
No model request is sent and nothing is charged.

Three server checks build `recorded_source_identity`
(`prism-wire-binding.source-attested.v2`) from the case document:

| Consumer | Case keys it needs |
| --- | --- |
| `services/prism_preview_runtime.py` (preview snapshot and `before_forward`) | `case_source_sha256 = case.source_sha256 or case.image_sha256`; `image_recorded_sha256 = case.image_sha256 or admission.source_metadata.source_sha256` |
| `services/prism_workspace_authority.py` (`_read`) | same rule |
| `services/m1_workspace_context.py` (original-row reader) | at least one of `case.source_sha256` / `case.image_sha256` equal to the source hash |

Ordinary admission records the hash only on the admission projection
(`case.admission.source_sha256`, and `source_metadata.source_sha256` for
inspected rasters). It never writes `case.source_sha256` or `case.image_sha256`.
Only `case16_acquire.py` does, when it creates a new case. In the QA_SERVER
TEST_ONLY workspace the inspected case had neither key, and since no ordinary
admission path writes them, every Workspace-admitted case is affected. None of
the 3 server PRISM operations could be sent, and AC-06 is BLOCKED on both
profiles.

The [bound adapter contract](../../operations/PRISM_BOUND_ADAPTER_CANDIDATE.md)
deliberately keeps missing projections at 503 "without writing them or
manufacturing authority from current bytes". This amendment keeps that rule:
the preview path still never writes or derives these keys. It changes **where
and when** the existing recorded identity is persisted.

## 2. Frozen behaviour touched and preserved

Touched (requires this owner decision):

- Admission persistence: the case document gains two write-once keys at
  creation (Part A).
- Existing case documents in an approved workspace gain the same keys once,
  from their recorded admission hash (Part B).

Unchanged (any implementation that alters these is out of scope):

- The preview gate, `before_forward`, `WorkspaceAuthority._read`, the M1
  context reader, `prism_bound.py`, the v2 transport protocol and its required
  field set.
- The PostgreSQL entry fence and writer gate.
- Admission eligibility, quality/modality gating, CFP/UWF confirmation,
  resolver behaviour, inference eligibility and source-origin policy.
- Clinician grade, annotation, AI-ROI review and provenance semantics.
- Model identities, pins, preprocessing and the accounting ledger.
- The case GET response: it already reports `image_sha256`/`source_sha256`
  from the loaded image, so the API and frontend do not change.
- The 503 for any case that still lacks the recorded keys.
- No schema migration: the keys are additive JSON fields on the existing
  document.

## 3. Part A — write-once projection when a case is created

| ID | Requirement |
| --- | --- |
| RSI-A01 | When the normal admission flow creates a **new** case document (no persisted row: the store returned exactly `new_case(image_id)`) and persists its first admission projection, it sets `case.source_sha256` and `case.image_sha256` to `record.source_sha256` in the same store write. (Tightened after review: a persisted revision-0 document without admission is not "new".) |
| RSI-A02 | It writes only if all hold: the value is a lowercase 64-hex SHA-256; it equals the case `image_id`; the record's integrity status is `OK` or `DUPLICATE_CONTENT` with no `changed_sources`; and `record.source_metadata.source_sha256`, when present, is equal. Otherwise it writes neither key, and the case stays unavailable for PRISM. |
| RSI-A03 | The value comes only from the admission record produced by admission inspection (`admission_method` `AUTOMATIC` or `MANUAL`; `LEGACY_COMPAT` and `DATASET_IMPORT` records, which hash loaded bytes or imported metadata, never qualify). It is never taken from `BridgeImage.sha256` at preview or inference time, from a client request, or from the preview/infer routes. |
| RSI-A04 | Write-once: no later code path overwrites or removes either key. Rescans, manual admission edits, modality confirmation, resolver updates, SOURCE_MISSING marking, grade/annotation edits and inference saves leave them untouched. A conflicting existing value is never "repaired"; the existing gates keep refusing (`SOURCE_HASH_MISMATCH`, "Recorded source identities disagree"). |
| RSI-A05 | Existing cases are **never** filled by Part A, including on rescan of a case whose admission is rewritten. Only Part B may add the keys to an existing case. |
| RSI-A06 | `apply_case_defaults` and `new_case` do not add default values for these keys; absence keeps meaning "not recorded". |
| RSI-A07 | The rule is the same for the PostgreSQL and legacy SQLite stores, because both use the shared admission flow. |

Implemented by `record_source_identity_on_creation` and `admitted_source_hash`
in `services/source_identity.py`, called before the first admission projection
in `apply_scan` (`api/_factory.py`) and `case_with_admission` (`workflow.py`).
`case16_acquire.py` already followed this pattern and is not changed.

## 4. Part B — one-time projection for existing Workspace cases

| ID | Requirement |
| --- | --- |
| RSI-B01 | A bounded operator command, separate from `serve`/`prepare` and not reachable from the UI or API, runs against one explicit `workspace_id`. Initial scope, if approved: only the TEST_ONLY workspace `ws_m1_63ed86c7d44f46d59479`. Each further workspace needs its own owner approval naming the workspace and plan hash. |
| RSI-B02 | Preconditions, refused before any read of case contents if unmet: no app process serving that workspace; entry fence inactive (the DB trigger also enforces this); no M1 GPU/model-host session open; a backup of the workspace taken with the existing backup tooling, and its receipt recorded. |
| RSI-B03 | **Dry run** in a read-only transaction classifies every case as `ELIGIBLE`, `ALREADY_RECORDED`, `CONFLICT` or `INELIGIBLE` with a reason code. Eligible means: admission projection present; `admission.source_sha256` is valid and equals `case_id`; integrity `OK`/`DUPLICATE_CONTENT`, not `SOURCE_MISSING`, no `changed_sources`; `source_metadata.source_sha256` absent or equal; neither case key present; every `inference_history[].source_sha256` that is present is equal; and the source file is readable from the workspace's registered input root with a current SHA-256 equal to `admission.source_sha256`. |
| RSI-B04 | The current file hash in RSI-B03 is a **veto only**. The written value always comes from the recorded `admission.source_sha256`, never from current bytes. A missing or different file makes the case `INELIGIBLE`. |
| RSI-B05 | The dry run emits a plan with workspace ID, command version, and per case `case_id`, `revision`, canonical payload SHA-256, class and reason, plus the plan's own SHA-256. The plan contains no filenames, paths, patient keys or clinical fields. |
| RSI-B06 | **Apply** requires `--plan-sha256` equal to a plan the owner approved in chat. In one transaction it re-reads every `ELIGIBLE` case and refuses the whole apply (`CHANGED_SINCE_PLAN`, no partial write) if any revision or payload hash differs from the plan. |
| RSI-B07 | For each eligible case the apply sets both keys to the recorded hash, increments `revision` by exactly 1, and appends one `events` entry: `{action: RECORDED_SOURCE_IDENTITY_PROJECTION, value_source: ADMISSION_RECORD, sha256, plan_sha256, timestamp}`. Nothing else in the document changes. |
| RSI-B08 | A receipt outside Git records the plan hash, backup receipt pointer, counts per class, and per-case before/after payload hashes and revisions. A separate read-only readback confirms each written case before the receipt is final. |
| RSI-B09 | One-time: a rerun on the same workspace reports zero `ELIGIBLE` and writes nothing. There is no scheduled or automatic execution. |

Bumping the revision is deliberate: open clients reload ("Case changed;
reload"), and any staged M1 context or preview plan bound to the old revision
becomes stale instead of silently continuing.

Implementation notes (`scripts/qa/m1_recorded_source_projection.py`):

- The approved workspace is a constant in the command; any other ID is refused
  before private configuration is read.
- "No app serving" is checked as no listener on loopback ports 8000/8010, and
  "no model-host session" as no listener on the launcher's model tunnel port
  47860. An app started on a non-default port is not detected; its optimistic
  writes would still fail with "Case changed; reload".
- Plan and apply refuse unless the `m1_entry_fence` trigger is installed and
  enabled on `review_cases`. An active fence refuses the UPDATE
  (`DATABASE_REFUSED_55000`) and the transaction rolls back.
- Current bytes are hashed by the normal admission scanner
  (`scan_authorized_hospital_roots`) over the launcher's approved private
  hospital roots (all of them, not only one workspace input folder). This only
  widens the veto set; it never supplies a value.
- Every output must be new and inside the launcher's approved private directory
  (`M1PrivateConfig`), whose ACL must pass `private_hospital_root`; repository
  and other paths are refused.
- RSI-B02's backup: apply requires `--backup-receipt` (its SHA-256 goes into
  the receipt) and writes a private `PREIMAGE.pending.json` of every row it
  changes before the UPDATE, renamed to `PREIMAGE.json` only after commit. A
  pending name therefore means the transaction did not commit. The existing
  hospital backup in `persistence/recovery.py` needs a separately approved
  source map, so which backup produces the receipt is part of the apply
  decision.
- After commit the command never reports a refusal. A failed readback gives
  `APPLIED_READBACK_UNAVAILABLE` with a receipt saying so; a failed receipt write
  gives `APPLIED_RECEIPT_NOT_WRITTEN` with the per-case hashes on stdout. A
  connection lost during COMMIT gives `COMMIT_OUTCOME_UNKNOWN` (rerun `plan` to
  see which cases are recorded); only an enabled origin/always trigger counts as
  installed.

## 5. Limitations to state honestly

- The case keys are a **write-once copy of the admission-time hash**, not
  independent evidence of the original file. Their value is durability: a
  later rewrite of the admission projection, or a changed file, becomes a
  detectable mismatch instead of passing silently.
- For Part B, the hash was recorded at original admission and is only
  re-verified against current bytes now. A case whose file is unavailable stays
  ineligible; this amendment does not reconstruct identity for it.
- Making the PRISM preview reachable is not PRISM qualification. AC-06 still
  needs an approved window, an actual protected run, SQL readback and the
  experimental-UWF notice. That compute decision is separate (section 8).

## 6. Acceptance criteria

Source/controls (fixtures and in-memory or test PostgreSQL only):

1. A new admission writes both keys equal to the admission hash; invalid,
   mismatched, `SOURCE_MISSING` or changed-source records write neither.
2. Rescanning an existing case without the keys does not add them; manual
   admission edits, modality confirmation, grade/annotation edits and
   inference saves never change them.
3. `apply_case_defaults`/`new_case` add no default for either key.
4. With a fake bound provider, a newly admitted case passes the recorded-
   attestation step of the preview, and `WorkspaceAuthority._read` and the M1
   context reader accept it. A case without the keys still gets 503.
   Changing the source bytes after recording still yields the existing
   mismatch refusal.
5. Part B: dry run performs no write; apply with a different plan hash,
   changed revision/payload, active entry fence or running app is refused
   with no partial write; only the two keys, `revision` (+1) and one event
   change; a rerun finds zero eligible.
6. Full backend suite, Ruff, root Node smoke tests and `scripts/docs/check_docs.py`
   pass on the branch and on main after merge.

Live, only after separate approvals:

7. The Part B dry-run plan for the TEST_ONLY workspace is reported to the owner
   before apply, and the apply receipt and readback afterwards.
8. A protected PRISM preview and run on an eligible case happen only inside a
   newly approved window under the existing runbook rules.

## 7. Rollback

- Part A: revert the code on a bounded `fix/` branch. Keys already written on
  cases created meanwhile remain; they are consistent with every existing gate.
  Removing them would be a separate owner-approved data operation.
- Part B: no automatic reverse write. Reverting means restoring the pre-apply
  backup, which needs its own owner decision because it also discards any later
  review work in that workspace.

## 8. Deferred and out of scope

- A new QA_SERVER window or reuse of the three unsent server PRISM operations
  (accounting/compute decision; the `HOSPITAL_M1_QA_SERVER_20261023` window is
  closed).
- QA_LOCAL, other workspaces, legacy SQLite backfill and hospital production
  data.
- Any change to the PRISM transport, adapter, pins or preview semantics.

## 9. Owner decision record

| Decision | Answer | Date / channel |
| --- | --- | --- |
| Part A (write-once projection at case creation) | APPROVED | 2026-10-24, chat |
| Part B (one-time projection command) | APPROVED (implement, then dry run and report the plan hash before any apply) | 2026-10-24, chat |
| Part B workspace scope | `ws_m1_63ed86c7d44f46d59479` only | 2026-10-24, chat |
| Part B plan SHA-256 approved for apply | pending (after dry run) | |
