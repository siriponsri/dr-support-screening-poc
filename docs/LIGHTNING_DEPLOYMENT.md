# Lightning AI Studio deployment — DR Support Screening POC v0.6.0

This document is the operator runbook for hosting the
`APP_PROFILE=model_api` Remote Model API contract on a
[Lightning AI Studio](https://lightning.ai/docs/platform/build/ai-studio)
GPU workspace. It is the third deployment path alongside the existing
Hugging Face Docker Space (`docs/PROFILES.md`) and the Modal adapter
(`docs/MODAL_DEPLOYMENT.md`).

The clinician UI, the Bridge v1 contract, the CVAT round-trip, the model
semantics, and the existing pytest suite are unchanged. Lightning is the
**deployment adapter**, not a new product surface.

This runbook is for the project owner's first GPU acceptance pass on the
Lightning Free Studio GPU tier. It deliberately does not claim a specific
free-GPU-hours budget — Lightning credit availability varies by account,
and the acceptance flow is designed to spend the minimum possible GPU
time.

---

## 1. Scope

What the Lightning adapter ships:

- `scripts/setup_lightning.sh` — one-time, idempotent Studio-side setup
  (virtualenv, project install, model-source / weight acquisition +
  SHA256 verification).
- `scripts/start_lightning.sh` — runtime launch script that pins the
  production env, refuses to silently fall back to CPU, and starts
  `python -m dr_support.run` on `0.0.0.0:8000`.
- `docs/LIGHTNING_DEPLOYMENT.md` — this runbook.

What the Lightning adapter **does not** ship:

- No Docker. Lightning Studios already provide a Linux runtime with GPU
  access — no container engine is required.
- No LitServe rewrite. The existing FastAPI surface from
  `dr_support.app.create_app()` is served verbatim; the contract is
  unchanged.
- No new model code. RETFound and PRISM continue to use the existing
  provider classes from `dr_support/providers/`.
- No new contract. The deployment serves the same `/health`,
  `/v1/models`, `/v1/predict/dr`, `/v1/predict/lesions` endpoints as the
  HF Docker Space and Modal targets.
- No UI. The clinician workstation is a separate deployment that proxies
  to this Studio URL with `MODEL_RUNTIME=remote`.
- No training, fine-tuning, calibration, scientific benchmarking, or
  clinical claims. Public/synthetic POC only.

---

## 2. Architecture

```
Local clinician workstation (Windows)
        |   HTTPS  (Authorization: Bearer ${REMOTE_MODEL_TOKEN}, optional)
        v
Lightning AI Studio (GPU T4)
        |   public URL exposed by Studio "Port" plugin on port 8000
        v
existing FastAPI model_api
        |
        +-- RETFound (dr_support/providers/retfound.py)
        +-- PRISM-DR  (dr_support/providers/prism.py)
        |
        v
GPU
```

The Lightning "Port" plugin (right-side panel of the Studio UI) exposes
the local uvicorn listener on port `8000` to a public URL. The clinician
workstation points `REMOTE_MODEL_URL` at that URL. Auth, schema, and
device semantics are unchanged from the v0.4.0 / v0.5.0 contract.

---

## 3. Hardware

| GPU  | VRAM | Use                                                |
|------|------|----------------------------------------------------|
| T4   | 16 GB | **Default.** Matches the HF Docker Space and Modal targets. The released RETFound + PRISM checkpoints fit comfortably under the api-level `RLock`. |
| L4 / A10 | 24 GB | Optional fallback if PRISM activations exceed T4 headroom. The owner reports `OWNER_HARDWARE_ACTION_REQUIRED` and only escalates after observing an actual OOM in the Studio logs — never preemptively. |

The Lightning Studio GPU tier is selected at Studio creation time. T4 is
the documented default for this POC. Hardware is never silently changed.

---

## 4. Asset strategy

**Persistent on the Studio's home directory.** `setup_lightning.sh`
downloads the pinned RETFound + PRISM-DR sources and weights into
`local-state/bridge/` once and verifies every checkpoint against the
SHA256s in `dr_support/providers/{retfound,prism}.py` and
`dr_support/providers/prism_assets.json`. Subsequent runs of
`setup_lightning.sh` are no-ops because `setup_models` is idempotent and
the Studio's persistent disk survives restarts.

The model_api profile refuses to start without the build-time asset
directory present (`dr_support.run._ensure_pinned_assets_exist`), so a
Studio where the home directory was wiped simply re-runs
`setup_lightning.sh` and recovers. The contract is the same as the HF
Docker Space (baked into the image) and Modal (also baked at image build
time).

Asset locations — single predictable path, no second cache layout:

| Env var           | Path                                     |
|-------------------|------------------------------------------|
| `RETFOUND_SOURCE` | `local-state/bridge/sources/RETFound`    |
| `RETFOUND_WEIGHTS`| `local-state/bridge/retfound-aptos.pth`  |
| `PRISM_SOURCE`    | `local-state/bridge/sources/PRISM-DR`    |
| `PRISM_WEIGHTS`   | `local-state/bridge/prism`               |

`scripts/start_lightning.sh` does not set these; the existing
`dr_support.run.configure()` helper wires them from the project root
when `python -m dr_support.run` boots.

---

## 5. Auth

`REMOTE_MODEL_TOKEN` continues to be the bearer-token secret for the
`POST /v1/predict/*` endpoints. The token is **never** hardcoded,
echoed, logged, or committed.

Set it inside the Lightning Studio's **Environment variables** panel
before running `scripts/start_lightning.sh`. The token is read by the
existing `dr_support.services.model_api._require_bearer` helper at
request time, compared with `hmac.compare_digest` semantics
(constant-time), and dropped without being recorded.

When `REMOTE_MODEL_TOKEN` is unset, the bearer-protected endpoints
accept anonymous requests; this matches the behaviour documented for the
HF Docker Space and Modal deployments and lets the owner smoke-test
without distributing a secret.

---

## 6. Operational policy (cardless / cost-aware)

This milestone is for **first GPU acceptance**, not production hosting:

- Start with **T4** if available on the Studio's machine picker.
- **Do not keep the GPU running unnecessarily.** Use the Studio's
  sleep / auto-sleep toggle when acceptance is complete.
- **First acceptance order** (one public/synthetic image per model):
  1. `GET /health`
  2. RETFound on one public/synthetic image
  3. PRISM on one public/synthetic image
- **Stop the GPU** after acceptance.
- **No benchmarks or batches.** A single forward pass per model is
  enough to prove the wiring; do not consume additional credits.
- **Do not claim an exact free-GPU-hours budget.** Lightning credit
  availability varies by account; the runbook deliberately stays
  silent on the number.

If PRISM activations exceed T4 VRAM during the first forward pass, the
owner reports `PASS_WITH_WARNINGS / OWNER_HARDWARE_ACTION_REQUIRED` and
does NOT silently select another GPU — escalate manually.

For PRISM specifically:

- Thresholds, fold ensemble, class mapping, and model semantics are
  unchanged.
- The api-level `RLock` keeps peak activation memory bounded by a single
  forward pass.
- `torch.cuda.empty_cache()` is invoked on the resolved device after
  every inference to release intermediate tensors.

---

## 7. Operator workflow (first-time acceptance)

The full first-time acceptance from a clean Lightning account. Steps A
through N are the canonical sequence; the owner does not skip steps.

### A. Create / open a Lightning Studio

- Sign in to [lightning.ai](https://lightning.ai).
- From the dashboard, click **New Studio** (or open an existing one).
- Name the Studio after the deployment (e.g. `dr-support-model-api`).

### B. Select GPU / T4

- In the Studio creation dialog, choose a **GPU** machine type.
- Prefer **T4** (the documented default for this POC).
- If only CPU is available, do not start the GPU acceptance flow —
  re-schedule when a GPU machine type is offered.

### C. Clone the GitHub repository

Open the Studio's terminal and run:

```bash
cd ~
git clone https://github.com/siriponsri/dr-support-screening-poc.git
cd dr-support-screening-poc
```

The persistent home directory is the canonical asset location; do not
clone into `/tmp` because that path is not persistent across Studio
restarts.

### D. Install dependencies

Run the idempotent setup script:

```bash
bash scripts/setup_lightning.sh
```

The script:

1. Creates (or reuses) a Python virtualenv under `.venv/`.
2. Upgrades `pip`, `wheel`, `setuptools`.
3. Installs the project in editable mode with the `[models,test]` extras.
4. Runs `python -m dr_support.setup_models --model all` to acquire the
   pinned RETFound + PRISM-DR sources and SHA256-verify every weight
   file under `local-state/bridge/`.

Subsequent runs are cheap no-ops because `setup_models` is idempotent
and the Studio's persistent disk keeps the downloaded checkpoints.

If the Studio's default torch wheel is the CPU build, install the
CUDA 12.1 wheels first before the project install:

```bash
pip install --extra-index-url https://download.pytorch.org/whl/cu121 \
    torch==2.5.1+cu121 torchvision==0.20.1+cu121
```

then re-run `bash scripts/setup_lightning.sh`. The Studio log surfaces
the exact missing-wheel error if this step is needed.

### E. Download / verify model assets

Already done by `scripts/setup_lightning.sh` (step D). Confirm by
listing the cache:

```bash
ls -la local-state/bridge/sources/RETFound local-state/bridge/sources/PRISM-DR
ls -la local-state/bridge/retfound-aptos.pth local-state/bridge/prism
```

Every file should be present and non-empty; `setup_models` raises on
hash mismatch, so any missing entry means the setup script failed.

### F. Set `REMOTE_MODEL_TOKEN`

In the Studio's **Settings → Environment variables** panel, add:

```
REMOTE_MODEL_TOKEN=<synthetic-deploy-token>
```

Use a fresh, random value (e.g. `python -c "import secrets;
print(secrets.token_urlsafe(32))"`). Never paste a real production
token into this runbook, into the project, into git, or into chat
transcripts.

### G. Run `scripts/start_lightning.sh`

In the Studio's terminal:

```bash
cd ~/dr-support-screening-poc
bash scripts/start_lightning.sh
```

The script:

1. Pins `APP_PROFILE=model_api`, `MODEL_RUNTIME=local`,
   `INFERENCE_DEVICE=cuda:0`, `HOST=0.0.0.0`, `PORT=8000`,
   `WORKERS=1`.
2. Runs a pre-flight CUDA probe — if `torch.cuda.is_available()` is
   false, the script exits with code 2 and a clear message instead of
   silently starting the server on CPU.
3. Execs `python -m dr_support.run`, which boots the FastAPI `model_api`
   on `0.0.0.0:8000`.

### H. Expose port 8000

In the Studio's right-side panel:

1. Open the **Port** plugin.
2. Click **Add port** → enter port `8000`.
3. Save; the plugin assigns a public URL of the form
   `https://<id>.lightning.ai`.

The first request to this URL pays the cold-start cost; subsequent
requests reuse the running container (within the Studio's idle window).

### I. Call `/health`

From the local Windows workstation (or any internet-connected host):

```bash
APP_URL="https://<id>.lightning.ai"
TOKEN='<synthetic-deploy-token>'   # only if you set REMOTE_MODEL_TOKEN

curl -fsS "$APP_URL/health" | python -m json.tool
```

Expected PASS criteria for `/health`:

```json
{
  "status": "PASS" or "PASS_WITH_WARNINGS",
  "lane": "PUBLIC_SYNTHETIC_REMOTE_MODEL_API",
  "providers": {"retfound-aptos5": "LOADED", "prism-dr-5fold": "LOADED"},
  "requested_device": "cuda:0",
  "effective_device": "cuda:0",
  "cuda_available": true,
  "cuda_device_count": 1,
  "cuda_device_name": "Tesla T4"
}
```

If `status` is `FAIL`, `cuda_available` is `false`, or the providers
report `ASSET_REQUIRED`, see the troubleshooting matrix in §9.

### J. Call `/v1/models`

```bash
curl -fsS "$APP_URL/v1/models" | python -m json.tool
```

Expected PASS criteria:

- Two entries: `retfound-aptos5` (task `global`) and `prism-dr-5fold`
  (task `lesion-roi`).
- Both report `status: "LOADED"` after the first inference call
  (lazy-loading).
- Both echo `requested_device: "cuda:0"`, `effective_device: "cuda:0"`,
  `cuda_available: true`.

### K. Smoke RETFound

```bash
python - <<'PY'
import base64, hashlib, json, urllib.request
from dr_support.images import synthetic_image

fixture = synthetic_image()
img_bytes = fixture.data
payload = {
    "image_id": "SYNTH_001",
    "modality": "CFP",
    "model_id": "retfound-aptos5",
    "image_b64": base64.b64encode(img_bytes).decode("ascii"),
    "image_sha256": hashlib.sha256(img_bytes).hexdigest(),
    "source_type": fixture.source_type,
    "width": fixture.size[0],
    "height": fixture.size[1],
}
headers = {"Content-Type": "application/json"}
if TOKEN:
    headers["Authorization"] = f"Bearer {TOKEN}"
req = urllib.request.Request(
    "$APP_URL/v1/predict/dr".replace("$APP_URL", APP_URL),
    data=json.dumps(payload).encode("utf-8"),
    headers=headers,
    method="POST",
)
with urllib.request.urlopen(req, timeout=60) as response:
    print(json.dumps(json.loads(response.read()), indent=2))
PY
```

Expected PASS criteria:

- HTTP 200.
- `state: "AI_SUGGESTION"`, `grade` ∈ `[0..4]`,
  `probabilities` is a 5-element list, `confidence` ∈ `[0..1]`.

### L. Smoke PRISM

Same envelope, swap `model_id` to `prism-dr-5fold` and the path to
`/v1/predict/lesions`:

```bash
# replace "/v1/predict/dr" with "/v1/predict/lesions" and
# "retfound-aptos5" with "prism-dr-5fold" in the script above.
```

Expected PASS criteria:

- HTTP 200.
- `state: "AI_SUGGESTION"`, `lesions` is a (possibly empty) list of
  lesion rectangles in original-image pixel coordinates,
  `provenance.image_sha256` matches the request, `provenance.source_revision`
  is the pinned PRISM revision.

If PRISM raises an out-of-memory error in the Studio logs, do NOT
silently select another GPU. Report
`PASS_WITH_WARNINGS / OWNER_HARDWARE_ACTION_REQUIRED` and stop the
Studio.

### M. Connect the local review workstation via `REMOTE_MODEL_URL`

On the local Windows clinician workstation, update `.env`:

```env
APP_PROFILE=review
MODEL_RUNTIME=remote
REMOTE_MODEL_URL=https://<id>.lightning.ai
REMOTE_MODEL_TOKEN=<same synthetic-deploy-token>
```

Start the review profile:

```cmd
START.cmd
```

(or `python -m dr_support.run` directly).

Verify the round-trip by opening the Worklist in the browser and
running the **Analyze** action on any admitted sample. The clinician
UI proxies through `REMOTE_MODEL_URL` and surfaces the GPU results from
the Lightning Studio.

### N. Stop the GPU when finished

In the Studio:

1. Stop `scripts/start_lightning.sh` (Ctrl-C in the terminal).
2. Stop / sleep the Studio from the dashboard so Lightning credits are
   not consumed.

A re-run simply restarts `scripts/start_lightning.sh`; `setup_models`
is idempotent and the persistent asset cache survives.

---

## 8. Expected PASS criteria (consolidated)

PASS only when **all** of the following are true:

- `/health` returns `cuda_available: true`, `effective_device: "cuda:0"`,
  `providers.retfound-aptos5` and `providers.prism-dr-5fold` both
  `LOADED`.
- `/v1/models` returns the two expected descriptors with `LOADED` status
  and the same device fields.
- `/v1/predict/dr` returns `state: "AI_SUGGESTION"` with a 5-element
  probability vector.
- `/v1/predict/lesions` returns `state: "AI_SUGGESTION"` with lesion
  rectangles in original-image pixel coordinates.
- The local review workstation proxies successfully via
  `REMOTE_MODEL_URL`.
- The Studio is stopped after acceptance; no GPU time is left running.

If any criterion fails:

| Symptom                                              | Action |
|------------------------------------------------------|--------|
| `/health` returns `cuda_available: false`             | The Studio was provisioned without a GPU; recreate with a T4 (or other GPU) machine type. |
| `/v1/models` reports `ASSET_REQUIRED`                  | Re-run `scripts/setup_lightning.sh`; the persistent asset cache was wiped. |
| `/v1/predict/dr` returns 503 with "RETFound assets not configured" | Same as above — re-run setup. |
| PRISM OOM during the first forward pass              | Report `PASS_WITH_WARNINGS / OWNER_HARDWARE_ACTION_REQUIRED`; stop the Studio; escalate manually. Do NOT auto-escalate. |
| `REMOTE_MODEL_TOKEN` mismatch                         | The owner set a different token in the Studio env panel than in the local `.env`; reconcile. |
| `401 Bearer token required`                           | `REMOTE_MODEL_TOKEN` is set on the Studio but the request omitted `Authorization`. |

---

## 9. Owner actions required on the Lightning cloud

These are operations the codebase cannot complete from a CPU-only
Windows host:

- **First-time Studio creation.** The owner creates the Studio and
  selects a GPU machine type.
- **First-time GPU acceptance run.** The owner executes steps A–N
  above against the live Studio.
- **Lightning credit management.** The Studio's GPU usage consumes
  Lightning credits; the owner monitors credit availability and stops
  the Studio when not in use.
- **`REMOTE_MODEL_TOKEN` rotation.** Rotating the token is a Studio
  env-panel action; the local `.env` must be updated to match.

None of these are governance or implementation issues — they are
operations the owner executes against the Lightning cloud.

---

## 10. What this milestone deliberately does not change

- **Bridge v1 schema.** No `GlobalResult` or `LesionResult` field has
  been renamed, added, or removed.
- **Provider classes.** `RETFound` and `PRISM` are unchanged; they
  continue to load their pinned checkpoints, do
  `torch.inference_mode()` forward passes, and release CUDA activations
  in the same way.
- **Profile invariants.** `APP_PROFILE=model_api` + `MODEL_RUNTIME=remote`
  is still rejected; `APP_PROFILE=review` + `MODEL_RUNTIME=local` is
  still rejected. Lightning is only an additional deployment path.
- **UI surface.** The V2 clinician UI is not in the Lightning Studio.
  The review workstation remains the existing browser / HTML experience.
- **Scientific behaviour.** No threshold changes, no class-mapping
  changes, no calibration, no clinical guidance.
- **Other deployment paths.** The v0.4.0 HF Docker Space and the v0.5.0
  Modal adapter are untouched; the owner can still use either as a
  fallback.
- **Tests.** The existing 102 backend tests + 3 frontend tests still
  pass on a CPU-only host. New tests in
  `tests/test_lightning_adapter.py` cover the launch script and
  contract stability without requiring Lightning cloud execution.

---

## 11. Local Windows-owner helper

For the project owner (Windows, low-dev), the practical workflow is:

1. In the Lightning Studio, copy the public URL printed by the **Port**
   plugin (e.g. `https://abcd1234.lightning.ai`).
2. In the local project folder, open `.env` (create from
   `.env.example` if missing) and set exactly these four keys:

   ```env
   APP_PROFILE=review
   MODEL_RUNTIME=remote
   REMOTE_MODEL_URL=https://abcd1234.lightning.ai
   REMOTE_MODEL_TOKEN=<same value the owner set in the Studio env panel>
   ```

3. Start the review workstation:

   ```cmd
   START.cmd
   ```

4. Open the browser to the Worklist and click **Analyze** on any
   admitted sample to confirm the round-trip through Lightning.

**Never** paste a real production token into this runbook, the
project, git, or any chat transcript. The values above are placeholders
only.
