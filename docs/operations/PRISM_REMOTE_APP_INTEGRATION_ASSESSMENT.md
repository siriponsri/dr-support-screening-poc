# Remote candidate: bounded app integration assessment

Historical f371809 assessment below. The subsequent offline implementation in
PRISM_FIXED_QA_SESSION.md closes the fixed-session app authority/lifecycle gaps
using injected storage and MockTransport. A broader production writer/RBAC design
is not a prerequisite for that bounded engineering path. Runtime registration,
live transport and worker/model qualification remain disabled/unqualified.

Disposition: **source-entry hook integrated; actual remote app execution BLOCKED**.
The named qa-prism-bound-remote-v2-disabled profile is declared and rejected by
the real app profile resolver before factories/DB/provider construction. Registration
always raises; no environment switch enables it. Existing profiles are unchanged.
The standalone transport/facade candidate was not copied in and relabelled as an
authoritative app implementation. No network, credentials or DB were used here.

## Concrete mutation inventory and missing authority

| Actual owner/path | Mutation scope requiring one authority |
|---|---|
| workflow.py admission_record/case_with_admission, GET cases/detail | Admission projections and automatic case hydration; GET is not intrinsically read-only. |
| workflow.py review/queue/lesion-review/admission/resolver/confirm-image | Case revisions, clinical and admission/integrity state. Store locks are scoped to the current store. |
| workflow.py annotations/completeness/from-ai/CVAT/manual-sync | Human/AI annotation state and revisions; asynchronous source changes must invalidate the prepared plan. |
| api/workspaces.py scan/create/update/open/delete + services/workspaces.py _swap_store | Input scans, image/admission registries, active Workspace and store replacement; WorkspaceManager has a different lock. |
| api/_factory.py scan/reconcile + refresh_remote_state | Source objects, admission caches, preparation and provider replacement. GET models/capabilities can refresh remote state. |
| api/_factory.py save_result + prism_preview_runtime.py | Original-store late-result saving and provider/source revalidation; existing inference_lock is not an all-writer mutation fence. |

A lock around before_forward or POST routes alone misses these writers. A lock
on one old store cannot fence replacement of app.state.store. The candidate's
SyntheticFenceAuthority owns only its own snapshots, not these real objects.
No shared gate has been implemented in this checkpoint and none is claimed.

The actual prepare sequence also lacks the candidate's two authority lifecycle
hooks: ReviewPrismPreview.snapshot calls provider preparation before a frozen plan
exists, while PrismPreviewService.prepare stores the final server binding without
calling authority.register_plan. An authoritative pre-prepare stage must precede
wire transmission and final plan registration must follow server freezing; a UI
checkbox or echoed remote JSON cannot supply either. The current runtime expects
get_prism_preview_candidate for cache-only refresh, whereas the candidate names
refresh_prism_preview_candidate. An alias alone does not close these lifecycle gaps.

Smallest next app design decision: a dedicated one-user/one-worker QA session
must either (A) fix the admitted immutable sources/Workspace/store/provider set
and explicitly reject every corresponding scan/replacement/refresh path, or (B)
route all HTTP and non-HTTP writers, including GET hydration and result saving,
through one app-owned authority with documented lock order. The real server must
register the frozen prepared plan, revalidate under that authority after remote
loading/queueing and retain quarantine until authenticated entry/terminal proof.
Do not use thread RLock ownership across an async middleware/worker-thread handoff.
No cross-process or arbitrary external file-writer guarantee is offered.

## Existing authentication/transport interfaces and blocker

api/_factory.py remote_transport() already exposes app.state.model_gateway_transport
or RemoteModelProvider._transport for injected httpx transport. ModelConnection
contains name/url/token; RemoteModelProvider._headers() supplies one Bearer identity.
probe_model_connection likewise accepts an explicit transport. These are the reuse
points; no parallel credential store is necessary or introduced.

The remote candidate requires a trusted Principal mapping for review-client,
prepare-source and forward-authority, plus an explicit no-retry private transport
and authenticated old-epoch status proofs. Existing bearer configuration does not
define which principal can grant forward authority. Merely forwarding the same
token or adding role strings would invent privileges. No credential value was read
and no mapping was manufactured. A reviewed server-side mapper and the intended
single-session writer policy are the exact missing integration decisions.

The candidate's httpx I/O timeout is not a total execution deadline. An owned host
executor with resource/deadline/termination proof remains separately unqualified.
The app factory currently constructs its Workspace/store and, in PostgreSQL mode,
can migrate during startup. Full factory/DB integration was not run or replaced
by a synthetic facade and labelled as actual app coverage.

## Safely completed source boundary

The reviewed two-file fatal-entry proposal was applied to the real PRISM provider
and bound adapter. Rejection immediately before self.roi propagates outside the
recoverable native-ROI catch; it cannot become a fallback lesion inference.
The new remote method requires both callbacks. The remote path also refuses this
method's legacy lazy model load/device resolution if the runtime becomes unloaded
or loses its device after before_forward. Default local behavior is unchanged.

Tests execute the actual imported PRISM/bound Python loop with synthetic PNGs and
fake ROI/folds, forbidding real load, Torch/CV2, sockets and SQL. They cover fatal
rejection/no fallback, successful entry order, plan replay, missing callbacks and
unloaded/device-loss rejection. A loaded boolean/device is not evidence that a
real Ultralytics ROI callable has no internal lazy setup/warmup; that remains
NOT_QUALIFIED and the profile cannot run. Native crop is still not precomputed.

Static-extracted startup-resolver tests establish only early disabled-profile
rejection, not a production factory or DB qualification. Existing synthetic remote
candidate95 and independent31 checks are separate evidence, not rerun here or
represented as all-writer integration acceptance. No live request allocation exists.

## Review/rollback

Review the bounded source commit independently. A reviewed revert of that commit
restores the preceding timing tip; preserve its timing/browser evidence and earlier
folder/integrity fixes. Never unlock a real remote fence on timeout, cancellation
ACK or new epoch, and do not register the candidate before closing the authority,
principal mapping and owned-executor gates above. No live recovery is attempted.
