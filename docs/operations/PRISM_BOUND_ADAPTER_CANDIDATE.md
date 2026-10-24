# Frozen-wire PRISM adapter candidate: offline engineering only

`providers/prism_bound.py:BoundLocalPRISM` is not registered in a factory, remote
provider, Model API or UI. No runtime availability or real-model qualification is
claimed. The default PRISM class still lacks the preview executor protocol, so
the frozen web binding continues to fail closed. No legacy/admission/clinical
guard is removed. This patch adds a private frozen-input seam in the existing
PRISM loop, an unregistered local adapter, and synthetic/fake-internal tests.

## Integrated source-attested contract; runtime still unavailable

Frozen web tip50c21a7/`prism-wire-binding.v1` supplies fresh source/wire hashes and
an admission digest, but does not carry all authoritative recorded hashes or an
integrity status to the executor. A freshly computed source hash cannot authorize
replacing recorded case/admission/image identity. In particular, converted
TIFF/DICOM wire bytes cannot independently prove their original file identity.

The isolated review branch now recognizes
`prism-wire-binding.source-attested.v2`. It requires a field inside
the server-frozen identity and plan hash, `recorded_source_identity`:

```
case_source_sha256, admission_source_sha256, image_recorded_sha256,
integrity_status, source_origin, case_revision, admission_sha256
```

All three recorded hashes must exist and equal the accepted original
`source_sha256`; integrity must be `OK`. Revision/origin/admission digest must
match the other frozen fields. Unknown/missing attestations and SOURCE_CHANGED
are refused before native ROI. These values must come from the authoritative
server records that the corrected web binding independently checks, never from
client acknowledgement or freshly hashing changed files. Hashes are binding,
not authorization/signatures. The existing trusted server cache/admission and
one-use checks remain required. The independent9633c2c integrity gate remains in
place. case_source_sha256 comes from recorded case source/image hash;
image_recorded_sha256 comes from recorded case image or technical source metadata,
never BridgeImage.sha256 alone. Missing recorded projections remain503 without
writing them or manufacturing authority from current bytes. Admission records
them once at case creation, and existing cases only through the approved one-time
projection ([amendment](../milestone/m1/M1_RECORDED_SOURCE_IDENTITY_AMENDMENT.md)). Missing recorded
integrity also remains503. A validated unchanged DUPLICATE_CONTENT record can
normalize to integrity OK after the existing identity gate; its raw status and
all admission evidence remain bound by admission_sha256. This preserves manual
review semantics without treating duplicates as changed sources.

The server freezes these values under the store lock. A mandatory trusted-server
callback rechecks source, admission, Workspace/provider identity, revision and
preparation context after any model load and immediately before native ROI. A
concurrent edit after forward starts remains a stale result under the existing
saver, preserving human decisions. Old v1/candidate protocols cannot execute.
No flag/metadata shim enables this class against50c21a7. Remote forwarding needs an authenticated model-host
execution protocol preserving the server plan/authority and single-use semantics;
no remote route or such transport is implemented here.

## Prepared bytes and actual execution

- Static identity verifies all21 checkpoint digests, pinned source and a config
  fingerprint covering adapter/provider/FOV/loader code, upstream engine/config/
  YAML, thresholds and relevant installed package versions. It does not call
  model load, GPU metadata or network. A model configured differently from its
  preview is rejected, including after load. Real verification/loading remains
  untested by this change.
- CPU preparation uses only the exact baseline white-rim detector, never the v4
  candidate or USPEC mask. It freezes immutable wire bytes and binary mask PNG
  plus baseline FOV metadata in a16-entry/128MiB/300s process-local cache.
  Decode/size/type/semantic-mask hashes are checked. Restart/eviction/expiry fail
  closed; execution never reruns the detector to replace a missing candidate.
  Asset/submit validation uses cache-only candidate lookup, including CFP; it
  cannot renew an expired/evicted candidate by detection.
- Execution validates request/image/modality/source/admission/recorded integrity,
  wire encoded and decoded-RGB hashes, mask/version, transform and model/config
  identities. A nonblocking serial lock prevents concurrent work. A valid plan
  is consumed before loading/forward; failures do not permit replay.4096 consumed
  plans is a process ceiling, not permission or an inference workload grant.
- The actual PRISM loop consumes those frozen bytes/mask. Native ROI inference
  still runs **inside execution**. Its successful crop remains unknowable at
  preflight. On ROI failure the conditional mask is discarded and full decoded
  Original wire RGB enters baseline green/CLAHE/tiling. On uncertain FOV, native
  ROI is still attempted on Original. CFP retains legacy ROI preprocessing.
- No two-stage ROI preview, model retry, mask substitution or clinical fallback
  is added. Empty proposals remain AI suggestions, never clinician normal.
- The bound result uses a stable pipeline/config preprocessing pin; actual
  PREPARED/FALLBACK/native-ROI outcomes stay in typed processing evidence. The
  original legacy result string remains unchanged for the default provider.
  Bound ROI failure omits unapplied analysis-field geometry, as the frozen
  runtime requires; applied-mask PNG attests the original frozen binary pixels.
  This metadata distinction needs review alongside the shared contract.

## Evidence boundary and reproduction

Tests execute the real PRISM Python crop/dispatch loop with fake ROI/fold/FOV
internals and generated RGB/L PNGs only. No checkpoints, Torch forwards, CV2
imports, actual baseline detector, GPU, server, network, SQL or patient data are
used. FOV fixtures are explicitly fake algorithm outputs, not a workaround or
qualification of the previously denied `cv2/config.py` path.

The fixture now consumes the actual review-branch serializer, runtime and adapter.
Joint in-memory service tests verify the plan from server records through exact
mask/wire consumption, asset checks, replay and source/config/cache rejection.
After-load authority changes abort before fake ROI. The HTTP contract suite
remains separate; no production factory, SQL or listener is started.

```
python -B -m pytest -q -p no:cacheprovider tests/test_prism_bound_adapter.py tests/test_prism_preview_binding.py tests/test_prism_bridge_contract.py --basetemp=NEW_ISOLATED_TEMP
python -B -m ruff check dr_support/providers/prism.py dr_support/providers/prism_bound.py dr_support/services/prism_preview.py dr_support/services/prism_preview_runtime.py tests/test_prism_bound_adapter.py tests/test_prism_preview_binding.py
```

Remaining gates: independent joint-contract review; remote API adapter;
real CPU FOV/restricted-loader/GPU qualification under new approval; actual
local-app/DB/private-transport test. The47request allocation remains exhausted.
This offline patch neither starts the blocked user service nor changes its
root-owned configuration-directory prerequisite. Do not deploy/merge by inference
from fake tests.
