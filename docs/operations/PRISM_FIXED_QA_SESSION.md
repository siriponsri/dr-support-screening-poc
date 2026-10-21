# Fixed-session QA app integration — offline only

Status: actual review factory, workflow projection, preview runtime/service and
original inference saver integrated with injected memory storage and MockTransport.
This is not the detached snapshot facade or a claimed live deployment. Ordinary
mode remains selected when qa_fixed_session is absent. The named runtime profile
still rejects startup; register_isolated_remote_profile always raises.

## Restricted engineering session

The internal _factory.create_app(qa_fixed_session=...) seam runs before persistence
construction. It accepts an app-owned FixedQASession with existing storage methods,
immutable selected BridgeImage objects, authoritative admission/case hashes and a
FixedSessionRemoteProvider. That provider accepts only httpx.MockTransport. No
environment variable or HTTP payload constructs it, no credentials are loaded,
and no real HTTPTransport can instantiate this injected port.

Initial scope is at most16 SYNTHETIC UWF records, one app worker and one fake host
job. CFP, public/hospital origins and live transports are outside this checkpoint.
WORKERS and WEB_CONCURRENCY must remain1. The exclusive journal writer lock rejects
a second owner; this is not a general distributed/process-supervision guarantee.

The actual workflow selected-case projection is hydrated once before sealing.
The real WorkspaceManager has an explicit persistence-free constructor for this
owned injected store. Normal constructors and their DB behavior are unchanged.
Fixed mode seals the app's image/admission/provider maps and protected state
replacement/deletion; the store proxy rejects writes except a scoped permit for
the actual existing inference saver. Direct scans, legacy infer and Workspace/store
swap helpers reject. No background writers are installed.

HTTP policy is an allowlist. Cases, images, workspaces and model/capability GETs
use selected cached projections, never mutable GET hydration or remote refresh.
Only protected preview prepare/assets/submit and static frontend files pass to
their existing handlers. Other reads and all review/admission/scan/Workspace/
model-connection/export/picker/legacy-infer mutations return423 before execution.
The session is deliberately read-only for clinical review; it grants no clinician
privilege and does not enable hospital export. Cached model descriptors remain
not-ready; the test-only preview capability does not promote them clinically.

Trusted in-process components must honor session ownership. Private raw injected
backing references, direct mutation of implementation internals, external files,
other processes and unrelated writers are not made universally immutable. Observed
case/source/config drift fails closed before wire preparation or grant. These
limits are explicit rather than an unsupported claim about arbitrary file writers.

## Actual lifecycle

1. ReviewPrismPreview validates existing recorded case/admission identities and
   obtains detached wire bytes through the existing derivative service.
2. Before provider preparation/transmission, authorize_prepare(wire,context) stages
   the server's actual recorded context and immutable original/wire bytes. The
   client then performs its independent source authorization. No UI hash grants
   authority and no missing recorded digest is synthesized from fresh bytes.
3. PrismPreviewService freezes its existing identity/plan and invokes
   register_preview_plan before caching/returning READY. Failure leaves no new
   usable server plan. Cache-only refresh uses get_prism_preview_candidate and
   cannot rerun preparation/detection. Existing one-use/replay checks remain.
4. After host loading/queueing, the client calls acquire(binding,challenge,
   before_forward). The app authority validates pinned Workspace/store/provider/
   source/config and case state, then invokes the existing actual before-forward
   validator under its session gate. The reused journal persists FENCED and
   consumed plan identity before grant can be sent. No thread-owned lock is held
   across ASGI/thread boundaries or network waits; excluded writers remain rejected.
5. Only matched authenticated entry/terminal status releases the lease. Lost grant
   ACK plus unavailable status quarantines the journal. Restart does not clear it;
   a new epoch, timeout or cancel ACK is insufficient. No automatic recovery or
   live operator intervention is introduced.
6. A validated result uses the existing original-store/provider saver through a
   scoped write permit. A simulated out-of-band human edit after entry stays
   preserved, gets STALE_RESULT history, and retires that session. The normal
   result mapping, clinical thresholds and human/export guards are unchanged.

The candidate transport client/host and bounded fsynced journal are reused rather
than a parallel inference/export pipeline. Fake tests supply one explicitly matched
service principal through MockTransport; these are protocol capabilities, not human
roles. No real token, server role mapping or credential configuration is created.

## Qualification boundaries

Tests instantiate the actual _factory.create_app, with SQLite/PostgreSQL connections
and persistence construction forbidden. They exercise real installed routes through
in-memory TestClient, the actual preview classes, candidate client/host and original
saver. Only host executor load/ROI are fake; all fake threads are joined. No TCP
listener or model backend starts; TestClient uses its normal internal event loop.
Torch/CV2 imports are forbidden. Synthetic source files and journal files stay in
test basetemps. No real patient data or inference allocation is consumed.

Coverage includes prepare/register/submit/replay, cached GET no-write/no-refresh,
fixed mutations and direct helpers, source/revision/integrity drift, malformed
recorded hashes, failed registration, after-load revalidation, lost ACK/status,
cooperative restart quarantine, exclusive ownership, original-store stale saving,
real-transport refusal and hard-disabled runtime registration. Existing ordinary
preview/bound/fatal/bridge tests remain separate regressions in the combined run.

Still NOT_RUN: real DB integration, OS crash/power loss, Linux journal behavior,
actual authenticated private channel with total streaming/control deadlines,
owned-process RAM/VRAM/termination proof, real checkpoint/FOV/model load or forward,
and verification that native ROI has no internal lazy setup/warmup after entry.
No live host adapter, real registration or zero-inference QA service session is
attempted here. The47-request allowance remains exhausted. This checkpoint closes
the bounded offline app hooks, not those remaining live-qualification gates.

Rollback is a reviewed revert of this bounded commit on the isolated review branch;
preserve earlier fatal-entry, timing/browser, folder and integrity changes. Never
delete or reset a real quarantine journal to enable work; none was created here
outside disposable synthetic test directories. No main merge, push or deployment.
