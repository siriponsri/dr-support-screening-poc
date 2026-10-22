# Demo readiness continuation — 22 October 2026

This bounded continuation uses reviewed integration baseline
`78902afb46e6d9dec7bc2a1bda8a02656a4909bb` and the existing C02 source manifest
`a33f5422127a269e7147e7f66444f482295ca58a0fbee6a654d1c1c68deac11c`.
The owner authorizes one implementation writer and continuation of the existing
workflow. No new orchestration system is required.

## Local acceptance

- Preserve original image bytes, raw predictions, historical receipts and all
  existing workspaces. Do not import candidate runtime databases.
- Preserve the existing image confirmation, clinician grade and lesion-review
  workflow. AI predictions and derived visibility are separate from human labels.
- Provide optional CPU field preview and reversible ROI visibility assistance.
  Do not require mask confirmation on every image. Retain uncertain regions.
- Explicitly distinguish CPU preview/post-filter assistance from model-input
  masking and PRISM's own native ROI processing. No efficacy claim follows from
  showing a mask or hiding an ROI.
- Preserve task-specific training exports and source-bound clinician grading
  folders. AI-only/unreviewed content stays separate and cannot become gold.
- The owner's current authorization permits local copies of already authorized
  hospital demo sources; older candidate documentation describing an unconditional
  hospital export block is superseded for this local operation. Unknown sources,
  integrity failures, path redirection and unapproved transfer remain blocked.
- Verify the integrated source with relevant regressions, required branch checks,
  PostgreSQL save/fresh readback and the actual installed browser. Fixture AI is
  local workflow evidence only; automated tests must not create real clinical
  decisions on hospital images.

## Actual inference acceptance

After local readiness, use the existing private QA channel and credential readers
for `dr-train` at `100.77.149.83`. Use a fresh test workspace. Never bypass an
access denial or alter credentials, ACLs, firewall or persistent access.

The pinned manifest contains 240 unique inputs: UWF186 + CFP54. The complete
new allocation is PRISM240 + USPEC186 + RETFound54 = 480 requests, including
four representative browser requests. Historical usage is 49; cumulative cap
is 529. Inspect durable accounting before submission. Never reset accounting,
retry an uncertain send, or automatically retry inference.

Only GPU0 RTX2080Ti is authorized. GPU time is at most 10800 seconds and session
time at most 14400 seconds. GPU1, V100, Ollama, extra paid services and unbudgeted
ablation are outside scope. Preserve the existing finite runtime and cleanup.

For each actual request retain source/model/weight hashes, parameters, device,
stage timings, returned or failed state and PostgreSQL readback. Capture the
representative browser steps and an all-results gallery. Retain failures as
failures. Build the E2E HTML and Thai operating/deployment instructions from
those results after actual testing; a blocked run must not become an E2E pass.

## Completion and evidence

Fix the identified batch receipt-I/O cleanup defect and inherited image-scan
environment difference; test both before freezing B03. Preserve C02 unchanged.
Record causes, changes, commands, outcomes and next actions in the operational log.
Follow the repository branch/integration lifecycle. Report DONE, BLOCKED and
NOT_RUN separately, including skipped validations. Technical readiness does not
establish clinical validation. No Lightning AI T4 comparison is valid without
measured T4 evidence.
