# M1 unregistered workspace PRISM executor

Status: additive implementation contract, 23 October 2026. This is not a
registered service, model qualification, hospital acceptance or clinical claim.
The fixed synthetic QA, Case16 and manifest-bound batch paths stay unchanged.

## Internal interfaces

`LoadedWorkspacePrismExecutor(provider, *, expected_pins, clock=time.monotonic,
load_guard=torch_load_forward_guard)` extends the existing loaded executor's
one-load lifecycle, forward-during-load guard, pinned identity and poison rules.
`provider` must be a fresh **exact** `BoundLocalPRISM`, with no batch authority;
subclasses, already-loaded providers and Case16/batch authority are refused.
Changing that provider/authority after construction is also refused. No new
checkpoint, parameters, preprocessing, source permission or model identity is
introduced.

`prepare(wire: bytes, modality: str)` accepts CFP/UWF only after verified load.
The existing pure preparation API has no source binding. It receives an
explicitly internal `BridgeImage` whose source type/origin are `UNKNOWN`; this
is CPU mask preparation only, never permission to infer. Wire bytes and modality
are preserved. CFP remains `NOT_APPLICABLE`; UWF uses the unchanged baseline
mask computation and keeps uncertainty. No preparation grants source access.

`execute(wire, mask, binding, plan_hash, *, before_forward, on_roi_entry)` checks
the frozen plan, immutable bytes, modality, exact loaded pins and ordinary
admission before constructing the execution `BridgeImage`. Its source type and
origin both come from the bound admission, never the preparation placeholder.
Only `source_allowed_for_model(origin, model_api=True)` grants source access:
PUBLIC/SYNTHETIC, or explicitly server-approved HOSPITAL_AUTHORIZED. Ordinary
WORKSPACE/UNKNOWN/other origins are refused. Admission must always be
`FUNDUS_ACCEPTED` and `GRADABLE`, with matching retinal modality. There is no
clinical override, Case16 exception or automatic label creation.

Execution calls the unchanged `BoundLocalPRISM.infer_remote_fenced_prism` API
with a copied binding and exact wire/mask. That provider continues to validate
recorded source hashes, transform, candidate cache, model identity, result
provenance and consumed plans. The wrapper rechecks identity/source policy
immediately before each supplied hook. The source hook runs after loading;
the native-entry hook remains outside the recoverable native ROI fallback.
Any execution failure poisons this executor; no automatic reload/retry occurs.
Results and processing evidence are returned unchanged.

`workspace_child_application(executor, *, token, issue_id, epoch,
clock=time.monotonic, load_seconds=60, job_seconds=120)` requires an exact
workspace executor and returns `(authenticated_asgi, host)` from the existing
`child_application`. It calls the parent-owned bootstrap method
`host.enable_workspace_executor(executor)` before exposing the result. That
method requires the same exact executor with no demo/batch authority and no
tickets, jobs or consumed state. Only this explicit opt-in permits ordinary CFP
preparation and its `NOT_APPLICABLE` candidate; default host paths are unchanged.
Missing bootstrap support fails closed. The wrapper then sets the host's
allowed origins from existing model-api source policy and sets a finite
`0 < job_seconds <= 120` (default 120). This is bootstrap-only; callers must not
change host configuration after requests begin. Hospital policy is rechecked
at execution, so a bootstrap snapshot is not a permanent permission grant.

Authentication still runs before body reads or dispatch. Lifespan still loads
exactly once before actual `LOADED` readiness. Readiness proves loaded pins,
not inference. The enabled host's authenticated capabilities require matching
actually loaded pins and add `workspace_runtime` with `profile: HOSPITAL_M1`,
CFP/UWF modalities, currently policy-authorized source origins,
`native_entry_protocol` and `load_state: LOADED`. `runtime_registered` remains
false: this metadata alone is neither client registration nor inference proof.
The old fixed-host capabilities stay unchanged. This module starts no listener/process, discovers no credentials,
selects no environment profile, changes no service lifetime and registers no
factory/provider/client readiness.

## Acceptance and limits

Synthetic tests exercise the exact provider/native loop with fake model ports:
CFP/UWF wire/origin preservation; public/synthetic/explicit hospital policy;
denied and ungradable admission; altered bytes, pins, source hashes and replay;
one-load/warmup/failure poisoning; fatal hook before native ROI and recoverable
ROI fallback; bootstrap deadline bounds and auth-before-body; actual loaded
capabilities versus unloaded/changed pins and revoked source policy; old host defaults.
No Torch/CV2, network/listener, DB, ACL, SSH or GPU execution is permitted in
these tests. Synthetic empty predictions are not clinical negative findings.

Live load/inference, native GPU behavior, app/DB save-reopen-export, durable
accounting, service supervision and actual hospital-target acceptance remain
NOT_RUN here. The app authority/binder and source/DB fences require independent
qualification; this executor or a successful health response cannot provide it.
