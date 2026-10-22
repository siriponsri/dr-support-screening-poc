# Optional annotation-assist visibility

Disabled by default: `DR_SUPPORT_ANNOTATION_ASSIST_ARTIFACT_ROI=0`. Local opt-in
`=1` in the review profile selects the generic CPU image-only provider unless
`DR_SUPPORT_ARTIFACT_ROI_REPLAY_MANIFEST` explicitly selects cached replay.
This is preview/post-result ROI assistance, not an external pre-mask of model
inputs. Original images, raw predictions and human labels remain separate.
There is no mandatory mask-confirmation step. Retain uncertainty and do not
claim validated retinal anatomy, reduced errors or clinical efficacy.

The doctor has no mask approval step or per-box confirmation popup. On the
annotation page, optional controls show filtered artifact ROIs, show an orange
overlay on the Original, and restore all filtered suggestions in one operation.
The original model input and raw detections remain unchanged. Other review and
grading canvases do not use the annotation-assist visibility override.

## Distinct methods and historical providers

The current generic image field is computed before model readiness and shows
empirical core/uncertain regions on a detached display image. Its post-result
decisions remain source/result/method/scope bound and reversible. Cached replay
is a separate shadow path with all ROIs initially visible; optional hiding
preview never issues new inference. Historical generic evidence hid0/92 ROIs;
P4 replay proposed1/92. Neither is a generalization or efficacy result.

The following padding and empirical-rim notes describe the earlier providers
preserved in the package, rather than the default generic implementation:

- **Technical padding:** task-2 core0.1.1, copied unchanged. Only a host-provided,
  genuinely established exporter/canvas profile can enable its hard post-filter.
  Empty registry retains everything and has no demonstrated rubber-rim effect.
  No such real-image profile is configured here. Its whole-expanded-box rule
  and margins are owned by the copied core, not reimplemented by the app.
- **Empirical rim proposal:** task-2 proposer0.1.1, copied unchanged. It may
  propose bright peripheral real tissue; output is always SHADOW_ONLY and all
  ROIs stay visible. The UI says empirical proposal, not validated retina or
  confidence. No profile is fabricated to pass empirical masks into the hard
  padding filter. Known misses and false tissue proposals remain limitations.

The earlier empirical OpenCV module is imported lazily, only when its opted-in prepare
request actually invokes its provider. This lane did not import/run it because
the existing interpreter's cv2/config.py has a recorded access denial. Adapter
tests inject a generated proposer. An import/core failure retains all ROIs with
an explicit unavailable status, with no dependency install or alternate path.

## Data and binding

`case.lesion` remains immutable raw output. Existing stable detection IDs come
from the current presentation policy; duplicate ambiguous IDs retain all boxes.
`case.artifact_roi_assist` and append-only `artifact_roi_history` hold separate
derived decisions, method/config versions, source/raw-result hashes, original
coordinates, actual encoded-mask hash, mask semantics and restoration history.
Binary PNG is stored once per hash in a server-side case audit archive; older
mask bytes survive later re-preparations. Public DTO/export sidecar omit its
base64; no new dataset mask-file export is enabled. Source, result,
method/config, mask mutation, unknown transforms or stale workspace invalidate
the view and retain suggestions. No absent metadata is set to clinically pass.

Prepare and restore require current case revision and an opaque workspace/store
scope hash. Their manager/store lock order fences workspace switching; bindings
also contain that scope. A late response is ignored after the annotation case
session retires. Restoring changes visibility metadata/revision only; it never
creates ACCEPT/REJECT, a human annotation, reviewed-negative or gold label.
Any existing explicit clinician decision or derived human annotation is protected
from automatic hiding. Re-preparing the same binding preserves restores.

Routes (local review only,404 with flag off):

```text
POST /v1/cases/{id}/artifact-roi/prepare
  { revision, scope_sha256 }
POST /v1/cases/{id}/artifact-roi/restore
  { revision, scope_sha256, binding_sha256, detection_ids }
GET /v1/cases/{id}/artifact-roi/overlay?binding_sha256=...
```

The annotation page prepares a missing/stale view automatically once while
loading. This is a derived CPU operation, not Analyze or an inference request.
Overlay retrieval is optional and source/binding checked, with no-store headers.
On overlay/restore failure the UI retains suggestions instead of silently hiding
them. No repeated inference, new ROI approval task or external telemetry exists.

## Export and training distinction

Existing snapshot architecture is reused. When a case has artifact-view state,
an optional hashed `artifact_roi_assist.json` sidecar preserves current decision
and history with `NON_GOLD_AI_VISIBILITY_ONLY` and
`negative_labels_from_suppression=false`. Stale/changed evidence is explicitly
marked and has no active suppressed set. Current `state` uses the same effective
projection policy as UI/restore/overlay with snapshot image/admission metadata,
provider and scope; missing current image authority retains all. The original
saved decision is kept separately as `historical_decision` plus immutable history,
so an old READY audit is never confused with active suppression after source
conflict or SOURCE_CHANGED. Raw `ai_evidence.csv` remains intact.
Automatic decisions do not enter `lesion_labels.csv`, clinician completeness,
annotation confirmation or gold selection. Existing eligible physician labels
are unchanged. The current owner authorization permits local copies of already
authorized hospital sources, with integrity/path checks. Unknown sources stay
blocked; this does not grant network transfer.

## Historical evidence, qualification and rollback

The paragraphs below preserve the earlier candidate's evidence boundary. Current
integrated-source tests and local PostgreSQL/installed-Chrome smoke are recorded
separately in the 22 October operational log. The latter uses fixture AI only,
with zero model calls or clinical labels. Actual AI E2E is a separate gate.

This is a separate file-copy candidate under task-3/artifact-roi-app-review,
because Git's native worktree ownership denial was respected. No trust/ACL
change, Git retry, merge, push, deployment, real DB action, GPU or new model call.
The frozen noon runner/package and integration source were not edited.

Application tests use generated image/mask bytes, fake/injected core results,
actual app routes/local test storage and existing training-export fixtures.
They cover provenance, persistence, restoring, confirmed-state preservation,
cross-workspace stale requests, source/mask/config mutation, optional overlays,
non-gold snapshot distinction and hospital409/no files. TypeScript checking is
separate from browser execution. Frontend runtime tests and screenshots are
NOT_RUN: Vitest configuration loading hit esbuild filesystem access denial;
that operation was stopped and not retried or bypassed.

Task-2's20-image gallery/area figures are historical empirical evidence, not
clinical accuracy, lesion retention or doctor-time measurements. Two distinct
saved PRISM sources match that frozen set and provide92 raw ROIs for the mask
lane's shadow intersection study. The app lane did not duplicate its geometry
algorithm or run new inference. Refer to the external review handoff for exact
source/patch hashes and validation receipts.

Rollback: leave the flag off and retain raw results/human labels. Remove/revert
only this reviewed bounded patch after integration; do not delete prior case
data, snapshots or audit history. Old experimental fields are inert with flag
off. Activate no actual empirical hiding before focused review/evidence.
