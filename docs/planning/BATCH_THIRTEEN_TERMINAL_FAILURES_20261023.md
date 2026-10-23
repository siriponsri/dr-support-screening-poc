# Closed batch: nine failures and four premodel blocks

Read-only analysis of retained evidence, 23 October 2026. No job was resubmitted.
This report is separate from the policy-blocked HANDOFF/log write. It records
known boundaries and missing evidence; a successful later job is not a replay
or proof that an earlier unknown failure was fixed.

Evidence roots under the owner's existing private artifact directory:
`demo-evidence-session04-20261023/PER_JOB_EVIDENCE.json`,
`demo-batch-evidence-20261022-b03/failures/`, per-lease receipts and the existing
read-only `CLI_DEMO_OPERATIONAL_LOG_20261022.md`. Full job IDs are listed below;
original filenames, patient context and credentials are deliberately absent.

| Terminal job ID | Model / status | Retained evidence and supported cause | Repair / verification plan |
| --- | --- | --- | --- |
| `d5e8689c2d3cfe55ee1e68466997f161d879adff3d08890f76930ce6d98e0f5d` | RETFound / FAILED | App boundary rejection; original response HTTP/body not retained. Remote request list empty and all recorded forwards0. Exact historical cause UNKNOWN. | Verify loaded CFP provider, source authorization, request/response and UI deadline before any newly scoped acceptance case. Do not invent an old HTTP status. |
| `4f81b1385489b04251e4c173eb0de81c532bf20a0a6dd26bd7cba9bdaf2d81d1` | USPEC / FAILED | App503 MODEL_UNAVAILABLE_AT_APP_BOUNDARY. Underlying RPC code/time not retained; no worker execute/forward for that job. CPU serialization rehearsal reached transport with source bytes unchanged, no model call. | Retain unknown root cause; verify bounded upload/discovery/authorization and correlated errors in a new smoke scope. Serialization success alone is not inference success. |
| `b55fcbf6712895c293e0af22ddfbfb30fd095d7a23453cff99b4be9d4be55e0b` | USPEC / FAILED | BATCH_HTTP_REJECTED_NO_RETRY503 after5172ms, payload8,355,507bytes; no worker execution. Existing generated streaming test reproduced gateway5s ingress rejection. | Existing batch repair extended its upload allowance; ordinary interactive transport must separately prove a bounded large-body path. Do not infer the same cause for the previous USPEC failure. |
| `cca990e31bc512bc8c9ce6d4466f8ae092a4c8be909f13a403e15c9098bb72de` | PRISM / FAILED | App502 before recorded model forward. A concrete FORWARD_HOOK_ATTACH_ONCE second-load reproduction explains the instrumentation defect: executor legally reuses a loaded provider while hooks tried to attach twice. | Existing batch fix made instrumentation attach once and retained later load revalidation. Preserve regression; ordinary main still needs the protected preview adapter. |
| `f62327e97fc9ef10f789ec7351b4575bcbd6d945ca7bb5ead478c5d26b623be0` | PRISM / FAILED | App502; remote ADMITTED, recorded forwards0, source fence OPEN. Actual ROI entry/completed model response not observed; exact failure UNKNOWN. | Preserve closed intent; keep source/entry boundary and correlated phase diagnostics. No claim that admission means inference completed. |
| `b4ae1fec4374fc33b44f3649c42eac89e0ae2e39e9fd9a698d4160bdcc295591` | PRISM / FAILED | EXECUTOR_FAILED_NO_RETRY409, recorded image-forward count1, execution5160.99ms. Normal contract hid underlying exception. Historical warmup/image split is not reliable. | Retain UNKNOWN exception; later instrumentation records safe error class/reason. Verify finite forward budget without changing weights/thresholds or replaying this job. |
| `d00b79a3552e8c82a00f5a099f51e99c71e08e58bbbe29438a2cd61721210baf` | PRISM / FAILED | FatalForwardBudget / PRISM_INTERNAL_FORWARD_CAP; recorded warmup21/image1, execution11331.7ms. Legacy phase split may misclassify warmup; total hook count retained. | Existing repair uses actual AutoBackend warmup callsite. Preserve strict caps, test phase accounting with synthetic controls; historical job remains failed. |
| `067b04056744fb3d5ea472792b59cfcaa5945ed41bea6c7a29b0568538be20a8` | PRISM / FAILED | Lease WORKLOAD_DEADLINE at271.08s after seven completed jobs; eighth only ADMITTED with17 image forwards and no complete response. Actual callsite phase accounting retained. | Admission must reserve enough native request/drain time within the remaining lease/session; ordinary interactive service needs an active per-request native watchdog and no unbounded queue. |
| `78f185de151948112d06f8983354edd2afa57004e15e817e93fdfcc830318ce1` | PRISM / FAILED | App502; PRISM_INFER503 / UNCLASSIFIED_TRANSPORT_FAILURE after171.999ms. No correlated remote record retained here. Exact root cause UNKNOWN. | Preserve consumed intent; record correlation/phase and no-retry status. Do not classify this as a model execution failure without forward evidence. |
| `132dd9deb578d6afd3053e7273d62624b24149a4d95fb4bd2ec0fc6826ce4596` | PRISM CFP / PREMODEL | Original representative preparation/automated acknowledgment did not reach execute/forward. Exact per-job diagnostic body not retained. | Test one-use preview confirmation/timeout behavior without a forward; do not bypass required preview acknowledgment. |
| `0bc5cd24a6b5dc2d6f892c3f9c17d7d99a14fb7ff2aead65b283e862c90ba56b` | PRISM UWF / PREMODEL | APP_REJECTED before inference; older driver retained no exact preparation reason. | Existing later body-span regression demonstrates a bottleneck, not this job's proven historical cause. Preserve unknown; verify preparation/control deadlines offline. |
| `3291bcd6279445a2f10d58d5b9e0a75b7bcfe5ea7fdb7cc488d7d7f6936511f7` | PRISM UWF / PREMODEL | APP_REJECTED, no per-job failure diagnostic/remote execution retained in final evidence. Exact cause UNKNOWN. | Retain premodel terminal state; validate phase-specific failure persistence and refusal before dispatch. No new inference needed for the control regression. |
| `f60eef2c84c2b45ad8021520ec6af138111818856789cd9e866ff8956b03263a` | PRISM UWF / PREMODEL | Preparation TransportError before second job's inference in a two-job lease; exact transport reason NOT_RETAINED. | Existing repair persists allowlisted preparation diagnostics and BLOCKED_PREMODEL before rethrow. Confirm with synthetic regression; no historical cause asserted. |

## Accounting and interpretation

The original ledger SHA256 remains
`ebc4f23ac5b9d89f136ada7a36b08350ddacf186e338a50c0ea5ba6f5ba14d98`.
It contains476 ATTEMPT_INTENT,467 RESPONSE_RETAINED,467 PASS_READBACK,
9 FAILED_NO_RETRY and4 BLOCKED_PREMODEL records. With historical49, global
usage is525/529 and original pending0. PREMODEL is not an inference failure.
An app/transport failure, model-forward failure, persistence failure and logging
failure must be reported separately. Original historical uncertainty is retained.

All thirteen terminal states remain unchanged. Any later authorized verification
requires a new purpose/intent and exact budget, never an automatic retry or an
old job-state reset. Hardware/clinical performance cannot be inferred from these
engineering failures or from the number of suppressed ROIs.
