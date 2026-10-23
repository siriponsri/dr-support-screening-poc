# Hospital M1 release candidate: supervised evaluation and annotation

Status: owner-directed acceptance contract, 23 October 2026. NOT COMPLETE.
This extends the existing codebase and its frozen clinical, admission, model,
coordinate and provenance contracts. It does not authorize autonomous diagnosis,
production/clinical claims, external data transfer, privilege changes, or replay
of the closed480-job batch. Existing owner artifacts and denied writes stay intact.

## Deployment contract

One codebase has an explicit `DR_SUPPORT_DEPLOYMENT_PROFILE` of `QA_SERVER` or
`QA_LOCAL`. This is separate from existing `APP_PROFILE`/`MODEL_RUNTIME`.
The review app remains `review`/`remote` in both modes: remote here means an HTTP
Model API process, including loopback, not necessarily an external server.
Legacy developer configuration remains compatible when the selector is absent;
Hospital M1 installation examples must set it explicitly.

- QA_SERVER: app, PostgreSQL and originals use hospital/workstation-configured
  storage. Model serving may use dr-train through an explicitly IT/data-owner
  approved private route. Validate actual backend connectivity, authentication
  and model protocol. A closed VLAN is not assumed to reach dr-train.
- QA_LOCAL: all serving, weights, app, database and images stay on the hospital
  hardware. Ordinary use makes no internet/dr-train request. The configured model
  endpoint must be loopback or the existing `model-gateway` Compose service;
  fail closed on an external endpoint, redirect or attempted manual override.
  Never silently fall back from local to server mode.
- Preserve existing review/model_api profile invariants and the tracked
  `deployment/dual-mode` architecture. Keep qualified provider environments
  isolated or explicitly qualify any recorded dependency assembly.

## Acceptance A: service lifecycle

Reusable no-code start/status/stop must distinguish asset verification, actual
model load, real inference, database availability, queue/in-flight state and
logging failures. Bound concurrency/queue length, request deadlines and resource
usage. Recovery never replays a sent/uncertain request and preserves labels,
history and accounting. Test cleanup must not close a service promised to a
physician during an active session. A temporary finite QA binding is evidence,
not the installed Hospital M1 service.

## Acceptance B: installation and workstation startup

Prepare secret-free deployment packages/config examples and an offline inventory
of dependencies/container images/weights kept outside Git. Normal no-code launch
starts or guides startup of the approved owned DB runtime without requiring the
user to open Docker manually each time. Preserve volumes. Verify cold start and
restart, and provide actionable failures. Machine service/autostart installation
requiring privileges is a distinct IT/owner approval step, never implicit.

## Acceptance C: physician workflow and data

For UWF and CFP: import, compatible actual AI, inspect/correct DR grade and lesion
ROIs, save, reopen/edit and export training data plus physician-confirmed grading
folders. Preserve originals, original coordinates, source hashes and model/
preprocessing versions. Keep raw AI predictions, physician annotations and
review status separate. AI does not create physician/gold labels automatically.
Engineering test labels/workspaces must not enter the physician dataset.

## Acceptance D: reversible mask/post-filter

Masking is an M1 requirement, not merely a preview. Show the region actually used
at the selected stage and clearly identify model-input pre-mask versus reversible
ROI post-filter. Keep original bytes, raw ROIs, uncertainty and undo. Do not demand
mask confirmation on every image. Compare baseline and the chosen method using
observed false peripheral ROIs and true lesions potentially hidden, with human
adjudication where needed. A suppression count alone is not improved accuracy.
Reconcile any change with existing protected edge/clinical semantics explicitly;
do not silently weaken the frozen policy or invent clinical/gold labels.

## Acceptance E: persistence and recovery

Test migration checksums, database/image backup and isolated restore, suitable
roles/access, label revision history and secret-safe logs. Restore must refuse
the source database, occupied targets, path collisions, missing image hashes or
incompatible migration history. Do not drop/reset a DB/volume or overwrite old
data. Backups include immutable originals and workspace/release identity; dataset
export alone is not a full recovery backup. Administrative schema migration and
least-privilege application startup must be separately verifiable.

## Acceptance F: two-profile evidence matrix

For each profile record PASS/FAIL/BLOCKED/NOT_RUN, revision and artifact pointers
for fresh install, cold start/restart, all three real models by supported modality,
save/readback/reopen/export, network/API failure, duplicate/uncertain recovery,
backup/restore and resource behavior. Synthetic tests verify controls only;
they never substitute for inference. Current workstation/dr-train evidence is
separate from hospital-target acceptance when that hardware/network is absent.

## Compute, access and release gates

The original ledger is525/529, with all480 original jobs terminal and unchanged.
Four requests remain for explicitly scoped interactive smoke/owner use. Before
exceeding that cap, propose exact additional request counts and GPU/session time
for failure repair, mask comparisons and two-profile acceptance. Preserve all old
ledger and budget clocks. No automatic inference retries or paid services.
Use only approved GPU0; do not touch GPU1/Ollama, firewall, credentials or public
exposure. Do not bypass policy/access denials.

The earlier rejected HANDOFF/runtime-summary/operational-log write remains
stopped; new implementation and this owner-requested M1 specification do not
reissue it. Release candidate delivery includes version, clean/pushed integrated
source, package/config examples, install/start/stop/backup/restore/rollback manual,
actual acceptance evidence and remaining limits. Clinical validation is separate.
