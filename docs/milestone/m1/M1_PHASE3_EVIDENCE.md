# M1 Phase 3 Execution Evidence

**Execution revision:** r3.0
**Execution date:** 2026-10-04
**Starting SHA:** `50cf7124ec95c56b9821d34e57141a1d8d3919a4`
**Current execution state:** `DONE / OWNER_ACCEPTED`

This receipt records the bounded Phase 3 execution against the owner-directed
`M1_PHASE3_EXECUTION_R3.md`. The execution evidence historically stopped at
`READY_FOR_OWNER_REVIEW`; the owner has now accepted that evidence and this
documentation-only closeout records Phase 3 as `DONE / OWNER_ACCEPTED`. It does
not authorize production/clinical deployment, hospital-data use, native UWF
model qualification, or Phase 4 work.

## Integrated foundation

Chunk A is integrated in feature commit `8830608`:

- Bridge v1 remains strict and unchanged; Phase 3 adds a versioned `bridge.v2` context/result envelope.
- Capability discovery is deterministic and separates provider identity, artifact, runtime, domain, rights, and release status.
- `/v1/models` retains the legacy response shape; `/v1/capabilities` exposes the full registry, including blocked/deferred capabilities.
- Model Gateway accepts a valid capability descriptor set without requiring the historical RETFound/PRISM pair.
- Remote capability construction preserves specialized legacy providers and supports task-declared generic providers.
- `PUBLIC` and `SYNTHETIC` are the only origins allowed across the current Model API lane. `WORKSPACE` and `UNKNOWN` remain blocked.
- Review inference history records invocation, capability, source/analysis hashes, transform, request revision, raw result, and status.
- Duplicate invocation IDs do not create duplicate authoritative runs. Stale runs are retained as `STALE_RESULT` and cannot replace a current projection or human decision.
- Review and Models & Audit select/display capability metadata without adding a model-debug console to the primary workflow. Raw outputs are described as model scores, not calibrated probabilities.

## Capability terminal states

| Capability | Artifact | Runtime/API | Domain | Rights/clinical | Release |
| --- | --- | --- | --- | --- | --- |
| USPEC UWF grading | `BLOCKED_ARTIFACT`; expected identity recorded, observed bytes unavailable | contract `PASS`; load/fixture/live API `NOT_RUN` | `UWF_RESEARCH_CANDIDATE` | rights `UNVERIFIED`; clinical validation not established | `DISABLED` |
| RETFound CFP grading | historical/provider identity preserved | legacy contract regression `PASS`; target runtime not requalified here | `CFP_DOMAIN`, not UWF validated | research/non-commercial and no clinical claim | `RESEARCH_ONLY` |
| PRISM CFP localization | historical 21/21 byte evidence preserved; no new load | legacy contract regression `PASS`; target runtime not requalified here | `CFP_DOMAIN`, not UWF validated | academic-use review required; no clinical claim | `COMPARATOR_ONLY` |
| Native UWF lesion localization | no qualified candidate | `NOT_PRESENT` | `DEFERRED_NO_QUALIFIED_CANDIDATE` | not established | `DEFERRED` |
| Longitudinal change | no model | `DISABLED` | not established | not established | `DISABLED` |
| MONAI | framework-only evaluation | no runtime adoption | not a model qualification | no wrapped-model rights transfer | `EVALUATED_DEFERRED` |
| Clef/Clef-Flash | comparator not run | resource/runtime receipt absent | not validated for UWF | not established | `COMPARATOR_ONLY` / deferred |

Detailed receipts are in `phase3/capability_registry_receipt.json`,
`phase3/artifact_receipt.md`, `phase3/security_runtime_receipt.md`,
`phase3/adapter_contract_receipt.md`, `phase3/monai_decision.md`,
`phase3/comparator_decision.md`, `phase3/performance_profile.md`, and
`phase3/final_phase3_receipt.md`.

## Validation evidence

| Check | Result |
| --- | --- |
| Backend full suite | `PASS` - 218 passed, 28 skipped, 50 warnings; executed with global Python because the feature-worktree `.venv` was unavailable |
| Phase 3 foundation tests | `PASS` - 5 passed within the full backend suite |
| Ruff | `PASS` for `dr_support` and tests |
| Frontend tests | `PASS` - 19 files / 124 tests; the UWF intake flow uses an explicit 30-second JSDOM timeout because its Chakra/Framer interaction path takes about 16 seconds |
| Frontend typecheck/build | `PASS` - typecheck and Vite production build |
| Playwright/browser matrix | `NOT_RUN` - no Phase 3 browser evidence was claimed |
| PostgreSQL Phase 3 persistence | `NOT_RUN` - no approved DSN/server |
| Root legacy UI smoke | `NOT_RUN / BLOCKED` - the runner starts with the available `main` `.venv`, but the ten public HRF sample files required for its historical 11-row DOM assertion are not present; this remains a historical fixture limitation, not a fabricated PASS |
| Documentation QA | `PASS` - 99 Markdown/Quarto sources |
| `git diff --check` | `PASS` after final branch changes |

Phase 2 and P3-0 acceptance evidence remains historical and authoritative; it
was not rewritten into a Phase 3 PASS. The P3-0 UX contracts remain frozen:
one-primary-action, image-first hierarchy, compact/progressive annotation
controls, hidden backend terminology, optional Advanced behavior, compact
reviewer treatment, color-role separation, responsive/accessibility baseline,
and manual AI-off operation.

## Security, privacy, and scientific limitations

- No weights, secrets, bearer tokens, DSNs, PHI, or runtime databases were added to Git.
- No checkpoint was loaded under the legacy optional PyTorch environment.
- No hospital-origin bytes were sent to a model endpoint; no hospital-data authorization was inferred.
- Raw score/confidence fields remain compatibility data and are not presented as calibrated clinical probabilities.
- CFP providers are not promoted to native UWF models. Empty lesion output is not a negative finding, and attention evidence is not lesion localization.
- Historical external package evidence remains historical; it does not establish runtime, L4, clinical, rights, or production readiness.
- Reviewer account independence is unavailable in this runtime; all Phase 3 review activity here is MAIN self-audit, not independent review.

## Reviews and owner decisions

Independent Chunk A/B/C/D reviews: `NOT_RUN / unavailable in this runtime`.
This is reported explicitly rather than simulated. Owner decisions remain
pending for artifact access/trust, exact loader security, target-host profile,
live Model API Gate C, UWF release policy, rights, and clinical validation.

## Formal owner closeout

On 2026-10-04, the owner accepted the Phase 3 execution evidence and authorized
formal closeout. The integrated Phase 3 implementation/merge evidence remains
`857f048da76e438c04422b8c0978daa780c19879`; owner acceptance was recorded against the clean, synchronized
pre-closeout `main` at `90724222ab2cd1ccf1a993484776649296cd0937`. The
historical `READY_FOR_OWNER_REVIEW` execution marker is retained above and in
the final execution receipt; it is not rewritten as a historical test result.

The accepted terminal states are:

```text
USPEC = BLOCKED_ARTIFACT / runtime NOT_RUN / disabled
Native UWF lesion = DEFERRED_NO_QUALIFIED_CANDIDATE
PRISM = CFP comparator only / NOT_VALIDATED_FOR_UWF
MONAI = EVALUATED_DEFERRED
Clef = comparator deferred
Longitudinal learned model = DISABLED
Live Model API Gate C = NOT_RUN
Target GPU/performance/VRAM/recovery = NOT_RUN
Phase 3 PostgreSQL runtime = NOT_RUN
Playwright Phase 3 browser matrix = NOT_RUN
Independent review = unavailable; MAIN self-audit only
```

The owner accepted these limitations without treating them as qualification
passes: the feature-worktree `.venv` was unavailable in the final audit
environment; no PostgreSQL DSN/server was available; the Phase 3 browser matrix
was not run; and the recorded legacy root-smoke limitation remains historical
evidence rather than a fabricated PASS. No USPEC artifact/runtime
qualification, live Model API success, target GPU/performance qualification,
native UWF lesion model, PRISM UWF validation, hospital-data authorization, or
production/clinical deployment approval is implied.

`P3.1 Runtime Qualification / Model Host Qualification` is recorded as
`DEFERRED / NON-BLOCKING`. P3.1 is not implemented here and does not block
Phase 4.

## Authoritative phase state

```text
Phase 1 = DONE
Phase 2 = DONE
P3-0 = DONE / UX FREEZE ACCEPTED
Phase 3 = DONE / OWNER_ACCEPTED
P3.1 Runtime Qualification / Model Host Qualification = DEFERRED / NON-BLOCKING
Phase 4 = NOT_STARTED
Phase 5 = NOT_STARTED
```

**Final closeout marker:** `PHASE 3 CLOSED — READY FOR PHASE 4 RECONCILIATION`
