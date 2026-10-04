# M1 Phase 4 Execution Evidence

**Execution revision:** r3.0  
**Execution date:** 2026-10-04  
**Starting SHA:** `80e7460252518a63c88f4ae7d73fb6f0bb5a4d37`  
**Feature candidate SHA:** `1dca82d8cb6818f5457c85d928772190be816bf2`
**Integrated main SHA:** `8a001b1c4d957dade0c887c5b3105af125ae60d3`
**Final evidence SHA:** `d09d748a2a1ad20ac97a962e80f364e036a36fa7` (historical r3.0 documentation evidence)
**Corrected current main SHA:** `85c4325b5fab87925ef3c1e877c5ff6aefc9c57e`
**Final documentation closeout SHA:** `60300dfff4911385b20e3a0c47b26a043fda51fc`
**Current state:** `READY_FOR_OWNER_REVIEW`

This document records the Phase 4 execution candidate against the owner-directed
`M1_PHASE4_EXECUTION_R3.md`. It is an implementation/evidence candidate, not
owner acceptance. Phase 4 does not authorize training, hospital-data export,
production/clinical deployment, model qualification, or Phase 5.

The original r3.0 candidate and integrated-main evidence remain historical. Before
owner review, three bounded corrections were integrated into the synchronized main
candidate `85c4325`: imported lesion readiness now remains independent of DR-grade
readiness, the legacy v1 manifest/grouped export compatibility paths enforce the
same `PUBLIC`/`SYNTHETIC` engineering authorization boundary as the canonical
Phase 4 snapshot path, and canonical snapshot files are re-read and hash-verified
after writing before a successful response is returned.

## Implemented scope

- Additive PostgreSQL-aware Workspace Data reads use a short-lived read-only
  `REPEATABLE READ` transaction when the active store is PostgreSQL; SQLite
  compatibility uses a bounded local read.
- Versioned `v2` read-only Workspace Data routes provide bounded pagination,
  readiness/review/source filters, safe search, record detail, Processing
  details, and Explainability/AI-evidence projections.
- Canonical snapshots use `s4.dataset-snapshot.v3` with `records.csv`,
  `dr_labels.csv`, `lesion_labels.csv`, `review_completeness.csv`,
  `ai_evidence.csv`, `manifest.json`, and `receipt.json`.
- Existing `s4.dataset-manifest.v2` and grouped-by-grade export remain
  compatible; the grouped export is an operational/manual utility, not the
  canonical training snapshot.
- Snapshot output is metadata/label evidence only; source image bytes are not
  copied. Blocked `WORKSPACE` and `UNKNOWN` origins remain visible locally but
  cannot create a canonical snapshot.

## Frozen policies and invariants

```text
Snapshot schema: s4.dataset-snapshot.v3
Eligibility policy: s8.2-task-specific-v2
Negative policy: p4-negative-training-deferred-v1
Source-state digest: p4-source-state-v1
Coordinate system: original_image_pixels
```

- Gold DR rows require the existing physician review, provenance, confirmation,
  and readiness gates.
- Gold lesion rows are limited to `HUMAN`, `HUMAN_CORRECTION`, and confirmed
  imported annotations. Untouched or rejected AI suggestions remain non-gold.
- `REVIEWED_NONE_FOUND` is preserved as completeness evidence only;
  `negative_training_authorized=false` by default.
- A patient grouping key requires `patient_resolution_state=RESOLVED` and a
  normalized pseudonymous patient key. No automatic train/validation/test split
  is created.
- Processing details and Explainability/AI evidence remain separate from gold
  labels. Phase 4 does not recompute inference or create explanation evidence.
- `PUBLIC` and `SYNTHETIC` are allowed for engineering snapshots;
  `WORKSPACE` and `UNKNOWN` are blocked by default.
- Source availability and integrity remain visible even when source bytes are
  unavailable. Missing bytes do not erase persisted review metadata.

## Validation evidence

| Check | Result |
| --- | --- |
| Phase 4 focused backend tests | `PASS` - 23 passed, 2 warnings |
| Backend full suite | `PASS` - 230 passed, 28 skipped, 50 warnings |
| Ruff | `PASS` - `python -m ruff check dr_support tests` |
| Frontend tests | `PASS` - 19 files / 125 tests |
| Frontend typecheck | `PASS` |
| Frontend production build | `PASS` - existing large-chunk warning remains |
| `git diff --check` | `PASS` |
| Documentation QA | `PASS` - Markdown sources inspected; no generated evidence/log dump added |
| Live PostgreSQL Phase 4 qualification | `NOT_RUN` - no approved DSN/server available |
| Playwright/browser matrix | `NOT_RUN` - no Phase 4 browser run claimed |
| 1920px browser inspection | `NOT_RUN` |
| Independent review | `UNAVAILABLE` - MAIN self-audit only |

The frontend dependency install completed from the pinned lockfile. The local
package audit reported existing dependency advisories; no dependency versions
were changed by Phase 4.

## Required policy regression evidence

- Untouched AI lesion suggestions remain absent from `lesion_labels.csv`, even
  after case-level annotation confirmation.
- Explicitly corrected AI lesions retain source-detection lineage and enter the
  gold lesion file only after applicable confirmation.
- Identical case state produces the same source-state digest; a revision change
  changes the digest.
- Resolved identity produces a patient group; an unconfirmed candidate does not.
- `WORKSPACE` origin remains locally inspectable but canonical snapshot creation
  returns a structured blocked response.
- Snapshot files are written under the configured Workspace output root, with a
  unique snapshot identifier and a manifest/receipt containing row counts,
  source-state identity, authorization summaries, and file hashes.

## Follow-up correction evidence

- `20e5f6d` / merge `9d0ea21`: imported CVAT-confirmed lesion rows use the
  lesion-readiness gate rather than the independent DR-case gate; regression
  coverage includes an imported lesion with no final DR grade, blocked origins,
  completeness-only reviewed-none handling, missing-source metadata, and the
  snapshot AI-evidence row count.
- `d7d980b` / merge `efef25b`: legacy `/v1/dataset/export` and
  `/v1/dataset/export/grouped-by-grade` now reject `WORKSPACE` and `UNKNOWN`
  origins, with regression coverage alongside the canonical snapshot block.
- `311cd84` / merge `85c4325`: canonical snapshot output re-reads each generated
  data file and verifies its final SHA-256 before success; a mismatch removes the
  partial snapshot and returns a structured failure. Regression coverage verifies
  the cleanup behavior.
- The frontend Datasets regression now explicitly opens the Processing tab before
  asserting the recorded-evidence wording; no application UX behavior changed.

## Known limitations

- Live PostgreSQL repeatable-read/concurrent-revision qualification is `NOT_RUN`
  because no approved DSN/server was available. The code path is implemented,
  but this is not a live PostgreSQL PASS.
- Playwright/browser matrix, responsive visual inspection, and owner UAT are
  not claimed in this execution candidate.
- The feature-worktree `.venv` limitation and historical root-smoke fixture
  limitation remain inherited historical evidence; they are not converted into
  fabricated Phase 4 PASS results.
- Reviewer account independence was unavailable; review status is MAIN
  self-audit only.
- No hospital-origin data, model weights, GPU/Tailscale host, training job, or
  production/clinical deployment was accessed or authorized.
- P3.1 runtime/model-host qualification remains deferred and non-blocking.
- The owner-review candidate has not been accepted yet; Phase 4 remains
  `READY_FOR_OWNER_REVIEW`.

## Phase handoff

```text
Phase 1 = DONE
Phase 2 = DONE
P3-0 = DONE / UX FREEZE ACCEPTED
Phase 3 = DONE / OWNER_ACCEPTED
P3.1 Runtime Qualification / Model Host Qualification = DEFERRED / NON-BLOCKING
Phase 4 = READY_FOR_OWNER_REVIEW
Phase 5 = NOT_STARTED
```

**Candidate marker:** `PHASE 4 READY_FOR_OWNER_REVIEW`
