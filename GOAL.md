# Session GOAL — DR Support Screening POC

This document captures everything delivered in the 2026-09-18 work session
against `siriponsri/dr-support-screening-poc`. It is written as a self-contained
handover for the project owner so the next session (or the GPU deployment host)
can pick up exactly where this one left off.

---

## 1. Summary

Three commits landed in this session, taking the project from `v0.2.0` to
`v0.3.0` without breaking any existing test, contract, or UI surface:

| Commit    | Title                                                                                          | Version |
|-----------|------------------------------------------------------------------------------------------------|---------|
| `5e66b35` | `polish(ui): V2 clinician-first audit and polish pass`                                         | 0.2.1   |
| `0ebe017` | `feat(remote): provider-neutral REMOTE inference adapter with mocked tests`                    | 0.2.1   |
| `a9ccdfb` | `refactor: single-repo multi-runtime-profile architecture (review / model_api / full)`        | 0.3.0   |

Status: **PASS_WITH_WARNINGS**. Real GPU inference paths exist but were not
exercised on this CPU-only host — see §5.

---

## 2. Milestone A — V2 audit + polish pass (`5e66b35`)

Goal: small, high-impact UI improvements without redesigning the V2 clinician
surface.

Changes:

- Action-bar hierarchy — the four primary review actions (Accept, Adjust Grade,
  Needs Annotation, Escalate) are visually grouped; **Advanced Edit / CVAT** is
  separated by a divider and de-emphasized with a `.subtle` style plus an
  external-link hint. Discoverable without competing with clinical decisions.
- Simplified clinical copy — `Model & provenance` → `Model details`,
  `Preprocessing` → `Image preparation`, tighter lesion-help text, clearer
  empty-state guidance in the AI Review panel.
- Improved accessibility — better focus visibility on the skip link, refactored
  to use the standard visually-hidden pattern.
- Bug fix — removed a redundant disabled-condition in the Advanced Edit button
  template (`${advancedUrl ? '' : ''}` was always empty).

Preserved:

- V2 UI, all element IDs (`#rows`, `#run-analyze`, `#advanced-edit`,
  `#grade-adjust`, `#grade`, `.grade-number`, `.canvas svg rect`,
  `[data-review]`), backend contracts, persisted review state, CVAT round-trip,
  AI-vs-clinician overlay distinction.

Files touched:

- `web/app.js` (22 lines changed)
- `web/style.css` (11 lines changed)
- `CHANGELOG_V2.md`

---

## 3. Milestone B — provider-neutral REMOTE inference (`0ebe017`)

Goal: add a remote inference mode without breaking existing local/mock modes.

Architecture:

```
DR Support Screening POC (review workstation)
        |   HTTPS
        |   Authorization: Bearer ${REMOTE_MODEL_TOKEN}   (optional)
        v
Remote Model API
        |- GET  /health
        |- GET  /v1/models
        |- POST /v1/predict/dr
        `- POST /v1/predict/lesions
```

Contract documented at [`docs/REMOTE_MODEL_API.md`](docs/REMOTE_MODEL_API.md).

Implementation:

- New `dr_support/providers/remote.py` with `RemoteModelProvider`,
  `RemoteGlobalProvider`, `RemoteLesionProvider`. Reuses the existing provider
  protocol (`task`, `model_id`, `metadata()`, `infer(request, image)`).
- Wire format: JSON envelope with base64-encoded image bytes (testable with
  `httpx.MockTransport`).
- Tokens: `REMOTE_MODEL_TOKEN` from environment only, sent as
  `Authorization: Bearer ...`. Never logged, persisted, or echoed in
  responses / `/v1/models` output / errors.
- Per-call timing: `last_inference_ms` and `last_metadata_ms` exposed in the
  provider's `metadata()` so the Models & Audit page surfaces remote latency.
- Error mapping: timeout → `504`, non-2xx → `502`, malformed schema → `502`,
  local-mode path → `503` (unchanged).
- Case event log: when a remote provider is used, each `INFERENCE` event now
  records `runtime: "remote"` and `latency_ms`.

Tests (20 new in `tests/test_remote.py`):

- Provider-level: payload/token wiring, missing-token behaviour, timeout → 504,
  non-2xx → 502, malformed schema → 502, metadata surfacing of revision /
  hash / latency, unreachable remote, model-not-listed, missing/invalid URL
  rejection, token never leaks into metadata.
- API-level: routes inference through the proxy, latency recorded in events,
  504/502 status mapping, models endpoint reflects remote runtime, local mode
  unaffected, CVAT round-trip preserved, token never echoed.

Documentation:

- New `docs/REMOTE_MODEL_API.md` — full deployment contract (transport, auth,
  endpoints, request/response shapes, model identifiers, error mapping,
  explicit "what this contract does not include").
- `docs/LOCAL_RUNBOOK.md` — new "Remote runtime (provider-neutral)" section
  with configuration knobs and behaviour.
- `README.md` — brief section pointing to the contract.
- `.env.example` — added `MODEL_RUNTIME`, `REMOTE_MODEL_URL`,
  `REMOTE_MODEL_TOKEN`.

---

## 4. Milestone C — single-repo multi-runtime-profile architecture (`a9ccdfb`)

Goal: prepare the codebase for the GPU deployment of the Remote Model API
without creating a separate repository (owner override). One codebase, three
runtime profiles selected via `APP_PROFILE`.

### 4.1 Module layout

```
dr_support/
├── api/         # clinician review workstation (cases, review, CVAT, UI, remote proxy)
├── services/    # standalone deployment-side services (currently model_api)
├── providers/   # shared model adapters (RETFound, PRISM, mock, remote proxy)
├── contracts/   # Bridge v1 request/response schemas
└── app.py       # top-level profile dispatcher
```

### 4.2 Runtime profiles

| Profile       | `APP_PROFILE` | `MODEL_RUNTIME` | Surface                                                                  | Loads weights locally? |
|---------------|---------------|-----------------|--------------------------------------------------------------------------|------------------------|
| Review        | `review`      | `remote`        | UI, `/v1/cases`, `/v1/cases/{id}/review`, `/v1/cases/{id}/cvat/*`, `/v1/infer/*` (proxy) | **No** |
| Model API     | `model_api`   | `local`         | `GET /health`, `GET /v1/models`, `POST /v1/predict/dr`, `POST /v1/predict/lesions` | Yes |
| Full (demo)   | `full`        | `local`         | Everything from both profiles                                            | Yes |

Profile/runtime invariants are **strict and fail-fast**:

- `APP_PROFILE=review` + `MODEL_RUNTIME=local` → `RuntimeError` at startup
- `APP_PROFILE=review` + missing `REMOTE_MODEL_URL` → `RuntimeError` at startup
- `APP_PROFILE=model_api` + `MODEL_RUNTIME=remote` → `RuntimeError` at startup
- `APP_PROFILE=full` + `MODEL_RUNTIME=remote` → `RuntimeError` at startup

The `dr_support.api:app` shim is preserved so the historical
`uvicorn dr_support.api:app` invocation (used by `START.cmd` and the JS UI
smoke) keeps working without the strict checks — this is intentional so the
existing pytest suite and JS smoke don't churn.

### 4.3 Reuse, no duplication

The `model_api` service **does not duplicate model code**. It instantiates the
existing `RETFound` and `PRISM` provider classes from
`dr_support/providers/`. Weight-loading, preprocessing, class order, lesion
mapping, and Bridge v1 contract are all the same code path that runs in the
`full` profile and that the review profile proxies to.

### 4.4 Deployment artefacts

- `Dockerfile` — multi-stage CUDA 12.1 / cuDNN 8 image built for Nvidia T4 small
  (HF Docker Space target). Installs `.[models,test]` from the cu121 torch
  index, runs `python -m dr_support.setup_models --model all` at build time so
  cold-start doesn't pay the multi-GB download, defaults to
  `APP_PROFILE=model_api` and `PORT=7860`, includes a `HEALTHCHECK` against
  `/health`, and uses a single uvicorn worker so the GPU model is not loaded
  twice.
- `docker-entrypoint.sh` — re-verifies weights on container start; refuses to
  start if `review` profile is missing `REMOTE_MODEL_URL` or if `model_api/full`
  fail verification.
- `docs/PROFILES.md` — full matrix, local-dev instructions, HF deployment
  walkthrough, contract invariants, and an explicit "what this does NOT do"
  list (no training, no committed weights, no logged tokens, no raw image
  upload endpoint, no clinical claims).

### 4.5 Tests (19 new in `tests/test_profiles.py`)

- Profile dispatch: `review` / `model_api` / `full` mount the right routes,
  nothing else.
- Profile / runtime invariants: every incompatible combination raises
  `RuntimeError`.
- model_api surface: `/health` reports provider statuses, `/v1/models`
  advertises `ASSET_REQUIRED`, `/v1/predict/{dr,lesions}` return `503` with a
  contract-honest message, non-CFP returns `UNSUPPORTED`, unknown model_id
  returns `404`, envelope validation rejects bad base64 / mismatched
  `image_sha256`.
- Bearer-token enforcement: missing / wrong token → `401`; correct token →
  request passes auth (and surfaces a sanitized `503` when weights are absent);
  `/health` stays unauthenticated so the HF liveness probe is never gated;
  tokens never appear in any response body.
- M4 integration smoke: review profile's `RemoteModelProvider` actually
  proxies to a `model_api` profile app via `httpx.MockTransport`, proving the
  contract round-trips end-to-end without any real network.

---

## 5. What's NOT done — OWNER_DEPLOYMENT_REQUIRED

The M1 / M2 real GPU inference code paths exist and compile cleanly:

- `RETFound.infer()` (in `dr_support/providers/retfound.py`)
- `PRISM.infer()` (in `dr_support/providers/prism.py`)

But this session did **not** exercise them, by design:

- Local environment is Windows CPU-only with no GPU.
- No model checkpoints were downloaded or committed (RETFound ≈ 3.6 GB,
  PRISM-DR has 21 released weight files).
- `dr_support/providers/assets.py` still performs the same
  `verify_source` / `verify_weight` SHA256 checks at load time — corrupted or
  substituted checkpoints are still rejected, no silent fallback.
- `setup_models.py` and `docker-entrypoint.sh` are the only paths that touch
  the network for source / weight acquisition; they live on the GPU host.

When the owner is ready to deploy on the HF Docker Space:

1. Push the current `main` (already done — see §7).
2. The HF Space SDK must be set to `docker`. Hardware `t4-small`.
3. The Dockerfile's `setup_models --model all` step downloads
   `RETFound` source revision `ae9a9ecf37857cf47b8aa9f87cd6f710d75db287` and
   the `prism-weights.zip` archive with SHA256
   `966a38bade7ed9049d5bc4b91a3adebb8f4c92afba64386abf6ab13a537c3b49`,
   then verifies each of the 21 PRISM weight hashes against
   `dr_support/providers/prism_assets.json`.
4. Provide `REMOTE_MODEL_TOKEN` (optional) as an HF Space secret so the review
   workstations can authenticate to the model_api deployment.
5. End-to-end smoke: review workstation with `APP_PROFILE=review` +
   `MODEL_RUNTIME=remote` + `REMOTE_MODEL_URL=https://<hf-space>.hf.space`
   should hit `/v1/predict/dr` on the deployment, which in turn runs
   `RETFound.infer()` and returns a Bridge v1 `GlobalResult` whose
   `provenance.checkpoint_sha256.aptos5 == a96b9dbcb78eff373912fb0a48d316dc35ffb0715bb2a1b9128b096d780edbbf`.
6. The first real-model inference will populate `provider.last_inference_ms`,
   which then surfaces in `GET /v1/models` and in the case event log under
   `INFERENCE` → `latency_ms`.

---

## 6. Verification matrix

Run on the local Windows CPU host, before each commit:

| Tool                         | Command                                                | Result                       |
|------------------------------|--------------------------------------------------------|------------------------------|
| Backend unit + integration   | `python -m pytest -q`                                  | **56 passed**, 1 skipped     |
| Frontend JS contract + UI    | `npm test`                                             | 3/3 PASS                     |
| Lint                         | `python -m ruff check dr_support tests`                | All checks passed            |

Test inventory by file:

| Test file                       | Count | Covers                                                            |
|---------------------------------|-------|-------------------------------------------------------------------|
| `tests/test_bridge.py`          | 8     | Bridge contracts, CVAT online safety, weight hashing              |
| `tests/test_workflow.py`        | 8     | Review round-trip, manual sync, error paths                       |
| `tests/test_sync.py`            | 2     | CVAT send / pull idempotency                                      |
| `tests/test_remote.py`          | 20    | Remote provider, mocked integration, token isolation              |
| `tests/test_profiles.py`        | 19    | Profile dispatch, invariants, model_api surface, M4 proxy smoke   |
| `tests/test_browser_ui.py`      | 1     | Real-browser preview smoke (skipped on this host)                 |
| `tests/overlay.test.cjs`        | —     | Imported CVAT geometry overrides AI provenance                    |
| `tests/ui.test.cjs`             | —     | DOM + real API: navigation, Analyze, grade correction             |
| `tests/preview.test.cjs`        | —     | Offline PREVIEW.html, no API calls, controls disabled             |

Total new tests added in this session: **39** (20 remote + 19 profiles).

---

## 7. Git history (session-only)

```
a9ccdfb  refactor: single-repo multi-runtime-profile architecture (review / model_api / full)
0ebe017  feat(remote): provider-neutral REMOTE inference adapter with mocked tests
5e66b35  polish(ui): V2 clinician-first audit and polish pass
```

Remote state:

```
$ git push origin main
0ebe017..a9ccdfb  main -> main
```

---

## 8. Files added or modified in this session

```
.env.example                              +52 / -1     (review + model_api sections)
CHANGELOG_V2.md                           +68 / -6     (0.2.1 polish + 0.2.1 remote + 0.3.0 profiles)
Dockerfile                                +136 / -0    NEW (HF Docker Space, T4 small)
PREVIEW.html                              +1 / -1      (sidebar version string only)
README.md                                 +35 / -0     (provider-neutral REMOTE + profile sections)
docker-entrypoint.sh                      +51 / -0     NEW (multi-profile container entrypoint)
docs/LOCAL_RUNBOOK.md                     +34 / -0     (Remote runtime section)
docs/PROFILES.md                          +80 / -0     NEW (profile matrix, deployment)
docs/REMOTE_MODEL_API.md                  +169 / -0    NEW (deployment contract)
dr_support/api/__init__.py                +57 / -0     NEW (review-API package + backward-compat shim)
dr_support/api.py → dr_support/api/_factory.py  (file renamed; API unchanged)
dr_support/app.py                         +140 / -0    NEW (top-level profile dispatcher)
dr_support/contracts.py → dr_support/contracts/_schema.py  (file renamed)
dr_support/contracts/__init__.py          +24 / -0     NEW (Bridge v1 schemas re-exports)
dr_support/providers/remote.py            +272 / -0    NEW (RemoteModelProvider + RemoteGlobalProvider + RemoteLesionProvider)
dr_support/run.py                         +65 / -19    (console-script entry point, profile-aware configure)
dr_support/services/__init__.py           +7 / -0      NEW (services package doc)
dr_support/services/model_api.py          +322 / -0    NEW (model_api service for HF deployment)
dr_support/api.py                         -106         (removed; superseded by dr_support/api/_factory.py)
dr_support/contracts.py                   -89          (removed; superseded by dr_support/contracts/_schema.py)
pyproject.toml                            +5 / -2      (version 0.3.0, console-script entry, [models] extra)
tests/test_profiles.py                    +348 / -0    NEW (profile dispatch + invariants + model_api + M4 proxy)
tests/test_remote.py                      +432 / -0    NEW (remote provider mocked integration)
tests/ui.test.cjs                         +3 / -0      (uvicorn target → dr_support.app:app_factory; reverted to dr_support.api:app shim)
web/app.js                                +14 / -8     (action bar polish, subtle Advanced Edit)
web/index.html                            +1 / -1      (sidebar version string only)
web/style.css                             +8 / -3      (subtle button, action-separator, panel-kicker, skip-link)
```

---

## 9. Operator notes for the next session

- The `review` profile on a CPU-only host is the easiest local target: it
  doesn't need weights, only `REMOTE_MODEL_URL`. If no model_api deployment is
  available yet, run `APP_PROFILE=full` against the synthetic mock to drive the
  V2 UI end-to-end.
- For any change to the inference contract, update both
  `docs/REMOTE_MODEL_API.md` **and** `dr_support/contracts/_schema.py` in the
  same commit, and run `tests/test_remote.py` and `tests/test_profiles.py`
  together — they are the two sides of the contract.
- The `model_api` service reuses the existing `RETFound` and `PRISM` provider
  classes. Do **not** add model-specific code to `services/model_api.py`; route
  through the providers instead.
- `dr_support.api:app` is a legacy shim. New code should import
  `from dr_support.app import create_app` and pass `APP_PROFILE` explicitly.
- The HF Docker Space image rebuilds `setup_models --model all` on every
  container start. If the upstream `RETFound` source revision moves, the
  pinned revision in `dr_support/providers/retfound.py` (`REVISION`) and the
  pin in `.env.example` must be updated together, and a new image must be
  built.

---

## 10. Status

**PASS_WITH_WARNINGS**.

- All in-scope deliverables shipped; all tests pass locally on a CPU-only host.
- Real GPU model inference is `OWNER_DEPLOYMENT_REQUIRED` — the code paths,
  asset verification, Dockerfile, and contract tests are in place; the actual
  `torch + CUDA + T4 + RETFound checkpoint + 21 PRISM weights` run is the
  owner's responsibility on the HF Space hardware.
- No scientific claims, no calibrated-probability assertions, no clinical
  guidance. Public/synthetic POC only.
