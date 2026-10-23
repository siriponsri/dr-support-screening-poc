# M1 native admission consumer

Status: internal control implementation; no service registration or live activation.
This consumes the existing BatchLedger continuation and exact BatchBudget Server
window. It does not create a new counter, session, process, orchestration, token,
database or inference route. Read M1_ACCOUNTING_CONTINUATION.md first.

The existing owned parent constructs M1AdmissionConsumer with its ledger,
budget, WorkerSupervisor, exact spawned child and already funded lifetime lease.
All process identity, resource and native supervision proofs remain the existing
adapter's responsibility. This consumer cannot qualify them from method presence.

An owned child request supplies its exact immutable operation facts, request
digest and child identity. The parent matches every fact with the frozen manifest,
checks its live supervisor/funded window, then calls the existing ledger.admit.
Only after durable intent and high-water persistence may it admit the same ID to
the supervisor and issue the native ACK. A failed or uncertain handoff is consumed,
never pending/retried. The adapter must retain ACK receipts and authenticate every
inference surface; this module alone does not integrate an HTTP server.

Preparation, status, challenge/grant and PostgreSQL confirmation are control RPCs.
For bound PRISM, execute HTTP202 is not a model completion. The owned adapter must
wait for the matching authenticated old-job terminal proof before record_response.
Ordinary predictions require complete actual HTTP/model responses. Successful
responses remain RESPONSE_RETAINED until a separately qualified app adapter reads
PostgreSQL independently, verifies the invocation/result/provenance and protected
physician state, then acknowledges that readback. HTTP200 is not PASS_READBACK.

Model, persistence, supervision and accounting outcomes are separate. Logging
failure after a real response or confirmed DB readback closes further admissions
and preserves its actual result/status. It must not turn successful inference into
a model error or permit an automatic retry. An unknown request/ACK, different child,
unfunded/expired lease, source/pin/parameter drift or terminal ID blocks admission.

Synthetic file/clock/child ports verify control ordering only. Actual native owned
child, service middleware, Windows app/PostgreSQL confirmation, GPU0 and browser
acceptance remain NOT_RUN until separately composed and exercised.
