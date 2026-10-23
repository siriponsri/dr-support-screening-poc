# M1 explicit workspace PRISM remote provider

Status: internal unregistered provider. Synthetic protocol controls do not qualify
an actual model server, tunnel, PostgreSQL binding, GPU execution or clinical use.
The original `RemoteBoundTransportCandidate` remains unqualified and unchanged.

## Explicit interface

```python
provider = WorkspaceRemotePRISM(
    channel,  # exact ExplicitHttpChannel, explicitly supplied transport/auth
    source_authority=authority,  # exact WorkspaceAuthority
    expected_pins=independently_reviewed_pins,
    wait_seconds=120,
    poll_seconds=.01,
)
provider.negotiate()
```

No factory, environment selector, API route, source-origin permission or automatic
registration is added. The constructor does not negotiate, load or infer. It
copies the independently supplied exact five-field pin mapping: model_id,
source_revision, preprocessing, config_sha256 and checkpoint_sha256. Model ID is
`prism-dr-5fold`; hashes are lowercase SHA-256. Mutable caller dictionaries cannot
replace those expected values. Exact channel and authority object bindings remain
required for preparation and execution.

Negotiation clears prior evidence and tickets before making requests. It requires
authenticated `GET /v1/prism-bound/capabilities` with the existing transport and
binding protocol, a nonempty bounded worker epoch, and exactly the expected pins.
It additionally requires the exact `workspace_runtime` object:

```text
profile: HOSPITAL_M1
modalities: [CFP, UWF]
authorized_source_origins: list of nonempty bounded origin strings
native_entry_protocol: prism-wire-binding.source-attested.v2
load_state: LOADED
```

It then requests the existing authenticated `/v1/prism-bound/readiness` using the
same epoch and requires the exact LOADED attestation with matching epoch/pins.
Only success of both requests publishes cached evidence. A health response alone
cannot establish this state. Negotiation performs no automatic retry; failure
leaves identity unavailable and invalidates old prepare tickets.

## Cached identity and execution

`metadata()` and `prism_preview_identity()` perform no RPC, model import or load.
After successful negotiation the descriptor has task `lesion-roi`, capability
`core_lesion_localization`, status LOADED and ready true. This is technical loaded
identity evidence, not an inference result: `inference_validation` remains
NOT_RUN. PRISM retains RESEARCH_ONLY, NOT_AUTHORIZED for production, trained domain
CFP, UWF EXPERIMENTAL and NOT_VALIDATED_FOR_UWF clinical semantics. Empty lesions
are never evidence that lesions are absent.

Descriptor source origins are the server-advertised list intersected with the
existing PUBLIC/SYNTHETIC/HOSPITAL_AUTHORIZED policy names. They never authorize a
source, rewrite admission or grant hospital access; existing application/source
policy and the workspace authority independently remain mandatory.

The provider retains the existing prepare ticket, wire/mask freeze, execute-once,
challenge, final source/database lease, authenticated native-entry/terminal proof,
result provenance and receipt verification path. Its `infer_bound_prism` first
requires current cached evidence and calls the exact workspace authority's
`authorize_execute(binding, plan_sha256)` before the inherited single execute
dispatch. This predispatch check creates no final entry lease and does not replace
after-load acquisition. There is no client budget counter or competing ledger;
the separately reviewed existing owner-ledger consumer must still precede native
execution when runtime wiring is qualified.

Wait is positive and at most 120 seconds; polling remains bounded by the existing
transport. Explicit channel control timeout stays two seconds, redirects and
environment proxies remain disabled. No inference retry, alternate endpoint,
legacy fallback or automatic model selection is introduced. A lost execute/grant
outcome retains the existing uncertain/quarantine behavior.

`WorkspaceStatusReader(channel)` is a separate cache-independent internal read
port. Its callable accepts the durable old-job binding, validates safe identifiers,
the old plan hash and reviewed pins, then sends one authenticated GET to that job
with the binding's old epoch. It requires all six existing authority STATUS_KEYS
and boolean proof flags to match. It never negotiates new capabilities, loads,
executes, retries or substitutes the current provider epoch. Missing/unknown old
jobs, a new epoch and unavailable authentication remain errors for the authority
to quarantine; the reader itself cannot release a lease. Constructor and each
call also bind the exact channel client, transport, auth callback and destination,
so a later in-place route change cannot redirect recovery.

## Qualification boundary

Tests use MockTransport, synthetic source documents and controlled authority ports.
They establish local validation/order and protocol behavior only. Live server
capability/readiness authentication, SSH mapping, full app/DB/export flow, native
GPU inference, accounting consumer wiring and clinical validation remain NOT_RUN.
Tests also exercise the real workspace authority with synthetic context/database
ports through predispatch, registered plan, challenge, lease, authenticated status
and result verification; these do not establish PostgreSQL or native inference.
