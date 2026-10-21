# Fixed-session owned PRISM runtime candidate

Base: da164ac38bec96cc35a27f7ebb7b7a522bee56d5. Additive candidate only; no
task-3 edits, live registration, server access, real model import/load/forward,
patient images, credentials, DB, GPU, packages or new QA session were used.
The actual app lifecycle/fence is already independently reviewed; this patch
does not replace it. Existing da164ac ordinary behavior and factories are intact.

## Concrete wiring

* Windows: FixedQASession remains SYNTHETIC-UWF-only. Its explicit injected
  OwnedFixedSessionRemoteProvider subclasses the existing fixed-session provider.
  PrivateGatewayChannel first verifies authenticated LOADED/epoch/model pins,
  then uses the existing prepare/execute/challenge/grant/status client and journal.
  Existing backend credentials stay injected and never enter preview JSON/UI.
* Transport: DeadlineHttpExchange is fixed to Windows loopback17860 or QA
  loopback7862, with exact route/method allowlist, no redirects/environment proxy,
  no retries, bounded bytes, absolute deadline checks and remaining-time I/O
  bounds. The existing SSH tunnel maps Windows17860 to QA17860. No tunnel is
  created here. Raw HTTPTransport retries must be zero or construction rejects.
* QA gateway: owned_gateway_application uses the existing PrivateGatewayAuth
  around the entire ASGI boundary. It verifies auth before reading any body,
  limits total receive/dispatch time/bytes and forwards via OwnedWorkerChannel.
  That channel rechecks owned listener identity and supervisor resources on every
  RPC, admits serial execution before forwarding, and matches actual remote job,
  epoch, ticket, plan and pins before releasing the supervisor admission slot.
* QA process: linux_owned_controller binds the existing LinuxOwnedChild pidfd
  adapter and WorkerSupervisor, GPU0 UUID,270-second soft lifetime,25-second drain,
  300-second hard child alarm,30-second job deadline,10GiB VRAM/24GiB RAM/40GiB disk.
  IndependentWatchdog ticks every250ms separately from inference/RPC. No PID
  attachment, PID scan/kill, process-group signal, GPU reset or restart exists.
* Child: injected_worker assembles the authenticated BoundTransportHost with
  LoadedPrismExecutor and the actual da164ac BoundLocalPRISM API. Lifespan loads
  once before readiness/listening; a global Torch pre-forward hook rejects and
  counts any warmup/forward during load, even if the loader swallows its error.
  Offline tests inject a fake guard and never import Torch. Later jobs reuse the
  loaded pins and the provider's cached preparation. No second load or fallback
  to legacy inference is allowed.
* Input/entry: immutable ticket wire/mask bytes go unchanged to
  infer_remote_fenced_prism. The source-authority callback is after load/queue;
  on_native_roi_entry runs at da164ac's fatal seam outside ROI recovery. Identity
  drift after grant aborts before ROI. Native ROI still runs inside execution;
  preview does not know its final crop/tensor. No new mask/pixel policy is added.
* Failure: failed load/model/RPC, uncertain transport, foreign listener, resource
  limit or timeout closes new work; the existing app journal retains unresolved
  grants through restart. Authenticated old-job status is still required to
  release quarantine. No timeout, cancel ACK, new epoch or journal reset grants
  permission. Late human edits still use the original da164ac saver.

## Explicit assembly, not live registration

scripts/qa/prism_owned_profile.py supplies injected_worker,
injected_server_gateway and injected_windows_provider. The server caller starts
OwnedRuntimeSession, waits for exact owned LOADED proof, then mounts only the
prefix under the existing authenticated gateway; it closes the session and
requires STOPPED plus close_confirmed before recording termination. Startup
readiness probing does not retry an inference or spawn. A foreign listener raises
and closes only the owned child; an absent listener waits only to its deadline.

worker_factory and register_fixed_owned_runtime always raise. There is no
environment/HTTP/approval boolean that bypasses this. Deploying this candidate
requires review of the exact frozen patch and an explicit temporary activation
patch/configuration for the approved QA session. No live factory currently reads
credentials or starts a listener. Deployment must pin the installed runtime
files/argv in addition to the existing model/config pins and use the existing
permitted private token reader; do not read canonical.env or private-key content.

## Reproduce now (offline only)

From the task folder, use the frozen da164ac source fixture plus candidate overlay:

```powershell
$env:PYTHONPATH='C:\Users\User\Documents\Codex\2026-10-21\task\owned-runtime-da164ac-reference'
& 'C:\Users\User\Desktop\myProject\dr-support-screening-poc\.venv\Scripts\python.exe' -B -m pytest -q -p no:cacheprovider --basetemp=.\owned-runtime-review-NEXT .\owned-runtime-da164ac-reference\tests\test_prism_owned_runtime.py .\owned-runtime-da164ac-reference\tests\test_prism_remote_transport.py
```

The fixture forbids Torch/CV2, sockets and SQL. ASGI unit tests use immediate fake
awaits/manual coroutine driving without creating a Windows socketpair/event loop.
All actual candidate host job threads are fake-model threads and joined. Fake
child resources/signals/clocks do not qualify Linux process behavior. Supplied
support scripts retain their prior qualified identities; they were not host-run.

## Small future qualification, NOT authorized or executed

Retain the existing47/47 inference allocation and749.580 cumulative observed
worker seconds. Proposed additional allowance: exactly TWO serial synthetic API
requests, one worker/provider load, GPU0 only, worker total<=300seconds including
startup/drain, request<=30seconds, same resource caps. No retries. No demo/new
dataset transfer. Each API request contains native ROI plus the unchanged
21-checkpoint/fold/SAHI pipeline; count and record internal forward/tile calls
separately. There is no warmup request or candidate-mask ablation allowance.

Proposed session/code directory after review:
/home/siripon/projects/dr-model-api-qa/deployments/prism-fixed-owned-da164ac-q01
and a fresh Windows results/journal directory. Never reuse any prior stage or
quarantine journal as a clean session. Existing prism-qa-torch213 interpreter,
official source/21 verified weights and baseline parameters remain unchanged.

The exact worker command shape (CURRENTLY FAILS CLOSED at worker_factory) is:

```text
/home/siripon/projects/dr-model-api-qa/environments/prism-qa-torch213/bin/python -m uvicorn scripts.qa.prism_owned_profile:worker_factory --factory --host 127.0.0.1 --port 7862 --lifespan on --no-access-log --log-level critical
```

Run that command ONLY inside the owned pidfd controller after a separately
reviewed temporary factory binds the exact pins/provider/epoch and existing token.
The existing gateway mounts only /v1/prism-bound on127.0.0.1:17860; the Windows
app uses the existing approved private SSH forward. Nothing adds public/VLAN
listeners or new credentials. Installing/mounting/activating is a future grant.

For each injected synthetic app case, the exact HTTP sequence is:

1. GET /v1/cases/{synthetic_id}; POST
   /v1/cases/{synthetic_id}/prism-input-preview with its actual revision.
2. Fetch the returned original/input/overlay URLs; compare byte hashes and retain
   source/wire/RGB/mask/transform/plan/model pins and authoritative recorded source.
3. Submit ONCE to the returned plan's /infer route using revision,source_sha256,
   wire_sha256,plan_sha256,mask_sha256,transform_sha256,model_version verbatim.
   Retain remote gate/entry/completion evidence and actual saved processing state.
4. Reject stale source/config, duplicate submit and malformed plans BEFORE model
   admission; these negative checks consume zero approved model requests. A
   timeout/uncertain outcome stops the qualification and retains quarantine.

Request1 is the NO_APPLIED_MASK path: unchanged baseline preflight must be
UNCERTAIN/UNAVAILABLE with mask=None, then record Original input/fallback honestly.
This alone does not validate applied-mask consumption.

Request2 is conditional APPLIED_MASK validation: use a separately reviewed
synthetic fixture whose unchanged CPU baseline actually returns READY. If it does
not, mark NOT_RUN/BLOCKED before inference. Even READY is insufficient: if native
ROI fails and the adapter discards the mask, record full-Original fallback and
APPLIED_MASK_NOT_VALIDATED. Only matching actual applied-mask pixels/hash plus
native-ROI/processing evidence qualifies that path. No extra request is silently
added to obtain a preferred outcome. No clinical false-positive/sensitivity claim.

## Still NOT RUN / limitations

Real HTTP/socket total deadlines, Linux pidfd/resource/termination under this
PRISM integration, real preload/warmup guard, native ROI/SAHI internals, and both
live frozen-input paths remain NOT_RUN. The existing RETFound readiness pass is
not PRISM qualification. Streaming deadline unit tests use fake chunk times;
real I/O scheduling and hard-alarm behavior need host qualification. OS-crash,
power-loss journal recovery and independent backing-store writers are still
outside the fixed-session guarantee. The patched provider is a reviewed trusted
execution path, not physical GPU first-instruction attestation. Inference,
temporary listeners/activation and any hospital VLAN changes need separate scope.
