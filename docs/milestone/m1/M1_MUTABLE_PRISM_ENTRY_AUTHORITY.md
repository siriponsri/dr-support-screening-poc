# Additive M1 PRISM authority for editable workspaces

Status: implementation contract under review; runtime registration NOT ENABLED.
Read with HOSPITAL_M1_RELEASE_CANDIDATE_SPEC.md. Existing fixed QA sessions and
the disabled remote profile retain their contracts. This document grants no
credentials, hospital access, source-origin permission or inference allowance.

The new authority must own one configured review process and its PostgreSQL
workspace state. Idle physician edits remain available. During the final source
check through authenticated native entry, every relevant writer must either
precede the grant and invalidate the plan, or be refused until entry is proven.
Unknown entry outcome remains durably quarantined; timeout, cancel ACK, a new
worker epoch or process restart is not permission to unlock or replay.

Bind the complete canonical case payload, admission/integrity, revision,
analysis preparation, workspace/store/provider/derivative identity, writer
generation, immutable source/wire/mask bytes, transforms, loaded model pins and
worker epoch. Revision alone misses same-revision automatic enrichment.
Reuse the existing prepare-once / execute / challenge / source lease / grant /
authenticated native-entry / terminal-proof protocol and result verification.
Keep original coordinates, raw model evidence, receipt consumption and stale
result saving. Never call the raw prediction route to bypass a preview rejection.

Writer coverage includes the whole workspace change plus scan publication,
image/admission and missing-source updates, GET case enrichment, resolver/image
confirmation, grade/annotation/completeness edits, post-filter restore, CVAT
state, inference persistence, model connection saves and GET provider refresh.
Slow scans may be staged outside the publication fence only with a captured
workspace generation checked again before publishing. Derivative cache additions
must not change immutable receipt bytes or service identity.

The common writer gate must acquire no thread lock across an ASGI await. Entry
admission fails immediately if writers are active, avoiding lock-order deadlocks.
Acquire the outer authority before existing manager/store locks. A short
PostgreSQL transaction protects final comparison, but row locks disappear on
connection loss. Cross-connection crash-to-entry coverage therefore also needs
a committed database-enforced write fence before sending the grant, checked by
every protected non-privileged DML path and retained after backend loss. Only
matching authenticated native-entry/terminal proof permits its release. The
runtime principal must not be able to disable the guard or arbitrarily clear
its fence. Compare full payloads. Python locks, cooperating advisory locks and
a local journal alone do not establish this database guarantee. Privileged
out-of-band administration is outside app ownership and is not covered.

Until the database fence and effective role/access boundary are implemented and
qualified, this mode remains unregistered. Preparing SQL/source/tests does not
authorize applying new role grants, credentials or persistent access: the owner's
existing prohibition on those changes still requires a separate concrete
approval/IT step. Do not silently narrow cross-connection coverage to get a pass.

Server authentication maps the existing approved backend principal to explicit
prepare/read/execute/forward-authority scopes. Request JSON or a boolean header
cannot create a principal. Preserve the existing token and private route; any
additional access or credential requirement is an owner/IT gate. Windows binds
only a verified local tunnel mapping, never the remote loopback URL directly.
Readiness distinguishes assets, actual load, bound-protocol qualification and
real inference. Health 200 and method presence do not establish qualification.

Charge the existing durable budget manager once before each new execute/predict
dispatch. Prepare/status/grant are control RPCs. Preserve the closed original
batch, original budgets and the stopped zero-inference preload session. Use the
separately approved cap549 and named session scopes; no automatic retry, reset,
session renewal or terminal-job replay.

Before registration, regression barriers must race grant-to-entry against every
writer category, workspace swap/scan gaps, provider refresh and same-revision
updates. Include two PostgreSQL connections, crash/quarantine recovery with the
old authenticated job, stale source/pins, replay, unknown grant outcome and
failure preserving actual HTTP/model results when evidence logging fails.
Synthetic tests qualify controls only. Actual GPU0 native entry, PostgreSQL
readback, main browser results/reopen/export and both deployment profiles remain
separate acceptance gates.
