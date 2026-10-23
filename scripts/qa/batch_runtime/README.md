# Finite QA accounting and application driver

These are public control sources from the existing owner-frozen B03 technical
demo package. The request ledger, GPU budget and application driver are copied
byte for byte. `batch_plan.py` contains the same pure `planned_leases` function.
The running owner package retains its existing launcher, transport and workers.

The modules perform no model or private-network calls on import. They are not
registered in the application startup path. Continue to start the clinician app
with `START_DR_SCREENING.bat` from the authoritative checkout.

The qualified owner package has its own frozen source layout and explicit
package hash. Its local inputs, image admission attestations, model pin
manifests, credentials, approval receipts, request ledger and PostgreSQL state
remain outside Git. An operator must verify that frozen package and the exact
owner authorization before running it. Copying these sources does not grant
GPU time, requests, credentials or permission to reopen a session.

## Preserved controls

- The existing hash-chained request ledger consumes intent before sending.
  Terminal and uncertain jobs cannot be replayed.
- One specifically approved named session can be activated under the existing
  single-writer lock. Approval, original budget, original ledger, pending jobs
  and model pins must match their anchored hashes. Concurrent, repeated and
  partial activation fail closed.
- The original budget bytes and journal prefix are retained. New charges and
  clocks are separate; summaries expose their aggregate. An uncertain worker
  retains its full reservation and quarantine.
- Each session is bounded to 10,800 GPU seconds and 14,400 wall seconds. Native
  worker, request and parent deadlines remain additional runtime constraints.
- PRISM groups contain at most two jobs following an observed four-job
  `WORKLOAD_DEADLINE`. Original job ordering and model parameters are preserved.
- Preparation exceptions retain safe diagnostic fields and remain terminal
  before any inference is sent. Raw exception text is omitted.

The named authorization in the source is the existing one-time owner decision.
Portable tests replace its hashes only inside disposable fixtures; they do not
authorize a real activation. They use no images, model fixtures as inference
evidence, GPU, credentials, network or database.

```powershell
python -m pytest -q tests/test_finite_qa_runtime.py
```

These controls establish technical accounting and persistence behavior.
Clinical validation, calibrated probabilities, clinician time savings and a
Lightning AI T4 comparison require separate measured evidence.
