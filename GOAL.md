# Session GOAL — DR Support Screening POC

This document is the canonical handover for everything delivered in the
2026-09-19 work session against `siriponsri/dr-support-screening-poc`. It is
written so the next session — or the Lightning deployment owner — can pick up
exactly where this one left off.

---

## 1. Summary

One commit landed in this session — `d791b7c fix(review): unblock Windows
worklist remote metadata startup` — fixing the Windows Worklist UI startup
blocker without breaking any existing test, contract, or UI surface.

The bug was the Worklist remaining stuck on "Loading review workspace…"
because `GET /v1/models` returned `HTTP 500 text/plain "Internal Server
Error"` whenever the remote Lightning Model API metadata probe failed. The
frontend `api()` then tried to JSON.parse the plain-text body and crashed
with `Unexpected token 'I'`, so the case selector stayed at "Loading…".

Two cooperating root causes:

1. `RemoteModelProvider.metadata()` was calling the **legacy** `GET /models`
   path, while the deployed Lightning Model API only exposes `GET /v1/models`.
2. The local `GET /v1/models` handler had no belt-and-suspenders degradation
   around the per-provider `metadata()` call, so any unexpected exception in
   that code path (not just the documented ones) propagated to FastAPI as
   `HTTPException(500)`.

The fix:

- `RemoteModelProvider.METADATA_PATH` is now `/v1/models` (matches the
  deployed Lightning Model API contract documented at
  `docs/REMOTE_MODEL_API.md`).
- `RemoteModelProvider.metadata()` is wrapped in a top-level
  `try/except Exception` that returns an explicit degraded descriptor
  (`status='REMOTE_INVALID_SCHEMA'`) for any exception that escapes the
  structured degradation branches.
- `_collect_metadata()` covers every documented failure mode:
  - timeout → `REMOTE_UNREACHABLE`
  - transport error → `REMOTE_UNREACHABLE`
  - HTTP 401/403 → `REMOTE_AUTH_FAILED`
  - any other non-200 → `REMOTE_HTTP_<code>`
  - non-JSON body → `REMOTE_INVALID_JSON`
  - JSON that is not a list → `REMOTE_INVALID_SCHEMA`
  - model_id absent from list → `REMOTE_MODEL_NOT_LISTED`
  - any uncaught exception → `REMOTE_INVALID_SCHEMA`
- The review `/v1/models` handler wraps each provider's `metadata()` in its
  own `try/except` so a regression in one provider can never poison the
  whole list response.
- `web/app.js` `api()` reads `response.text()` defensively, attempts
  `JSON.parse` only when the body is non-empty, and surfaces a useful
  `GET /v1/models failed with HTTP 500: Internal Server Error` message
  instead of the cryptic `Unexpected token 'I'` JSON.parse crash.

Eight new regression tests pin the contract (see §3).

Status: **PASS** — `GET /v1/cases` and `GET /v1/models` both return
`HTTP 200 application/json`; the Worklist loads; no "Loading…" lock; no
JSON.parse crash on plain-text 5xx bodies. `REMOTE_MODEL_TOKEN` is
never leaked into the `/v1/models` body, logs, or the user-visible
error text.

---

## 2. What changed in `d791b7c`

```
 dr_support/api/_factory.py     |  30 +++++-
 dr_support/providers/remote.py |  45 +++++++--
 package.json                   |   2 +-
 tests/api_hardening.test.cjs   | 136 +++++++++++++++++++++++++++
 tests/test_remote.py           | 205 ++++++++++++++++++++++++++++++++++++++++-
 web/app.js                     |  31 +++++--
 6 files changed, 425 insertions(+), 24 deletions(-)
```

### 2.1 `dr_support/providers/remote.py`

- `RemoteModelProvider.METADATA_PATH: str = '/v1/models'` (was the
  legacy `/models`).
- `metadata()` now wraps `_collect_metadata()` in
  `try/except Exception`; any escape returns a
  `REMOTE_INVALID_SCHEMA` degraded descriptor instead of bubbling
  to the FastAPI handler.
- `_collect_metadata()` already covered timeout / transport /
  401-403 / non-200 / non-JSON / non-list / model-missing — those
  branches were preserved verbatim and continue to map to
  `REMOTE_UNREACHABLE` / `REMOTE_AUTH_FAILED` / `REMOTE_HTTP_<code>` /
  `REMOTE_INVALID_JSON` / `REMOTE_INVALID_SCHEMA` /
  `REMOTE_MODEL_NOT_LISTED`. The warning text now references the
  corrected `/v1/models` path so operators can immediately see whether
  the proxy is hitting the deployed Model API contract.
- `_send()` already translated `httpx.TimeoutException`,
  `httpx.HTTPError`, and any other exception into
  `RemoteTimeoutError` / `RemoteModelError` subclasses; preserved.

### 2.2 `dr_support/api/_factory.py`

- The `GET /v1/models` handler now wraps each provider's `metadata()`
  in `try/except Exception` and substitutes a
  `status='REMOTE_INVALID_SCHEMA'` degraded descriptor with the
  exception name and message in the warnings list. This is the
  belt-and-suspenders guard: `RemoteModelProvider.metadata()` already
  degrades on its own, but a future regression cannot escape to
  `HTTPException(500)`.
- Synthetic fixture descriptors are unaffected.

### 2.3 `web/app.js`

- `api()` reads `response.text()` defensively, then attempts
  `JSON.parse` only when the body is non-empty; the parsed payload is
  retained for callers that iterate over it.
- On a non-2xx response, `api()` throws a useful error message that
  includes:
  - the FastAPI `detail` field when present,
  - the HTTP status and statusText,
  - a short body hint when the body is < 200 chars (so a plain-text
    `Internal Server Error` is preserved verbatim in the message),
  - never includes any token material (the browser never holds a
    token for `/v1/models` — that endpoint is unauthenticated by
    design, the `REMOTE_MODEL_TOKEN` is only sent server-side to the
    remote Lightning Model API).
- The successful-response path is unchanged: parsed JSON is returned
  to the caller; an empty 2xx body returns `{}`.

### 2.4 `tests/test_remote.py`

Eight new regression tests (see §3.2).

### 2.5 `tests/api_hardening.test.cjs`

Five new frontend scenarios exercising `api()` via `vm.runInContext`:

1. text/plain `HTTP 500` → must surface a useful error, not
   JSON.parse crash.
2. valid JSON `HTTP 200` → returns parsed payload.
3. valid JSON `HTTP 422` → surfaces FastAPI `detail` if present.
4. empty `HTTP 200` body → returns `{}`, never `undefined`.
5. HTML `HTTP 502` body → useful error, no JSON.parse crash.

### 2.6 `package.json`

- `npm test` now runs `overlay`, `api_hardening`, `ui`, and
  `preview` test files in that order. The `api_hardening.test.cjs`
  script was added to the script list.

---

## 3. Regression tests

### 3.1 Provider-level (in `tests/test_remote.py`, new section
"M0.8 — Windows worklist remote-metadata startup regression tests")

| Test | Pins |
|------|------|
| `test_remote_provider_metadata_queries_v1_models_path` | Remote metadata requests `/v1/models`; legacy `/models` is NOT called. |
| `test_api_v1_models_200_when_remote_metadata_404` | Remote `/v1/models` 404 → local `/v1/models` is HTTP 200 with `REMOTE_HTTP_404` descriptors. |
| `test_api_v1_models_200_when_remote_metadata_times_out` | `httpx.ReadTimeout` → local `/v1/models` is HTTP 200 with `REMOTE_UNREACHABLE`. |
| `test_api_v1_models_200_when_remote_metadata_unreachable` | `httpx.ConnectError` → local `/v1/models` is HTTP 200 with `REMOTE_UNREACHABLE`. |
| `test_api_v1_models_200_when_remote_metadata_non_json` | text/plain metadata body → local `/v1/models` is HTTP 200 with `REMOTE_INVALID_JSON`. |
| `test_api_v1_models_200_when_remote_metadata_wrong_schema` | JSON object (not list) metadata → local `/v1/models` is HTTP 200 with `REMOTE_INVALID_SCHEMA`. |
| `test_api_v1_models_200_when_remote_metadata_unexpected_exception` | A provider that raises `RuntimeError` inside `metadata()` → local `/v1/models` is HTTP 200 with `REMOTE_INVALID_SCHEMA` and a meaningful warning. |
| `test_api_v1_models_never_leaks_token_in_metadata_failures` | Bearer token never appears in `/v1/models` body or in log records, even when the remote returns `HTTP 500` with `bearer=<token>` in the body. |
| `test_remote_provider_metadata_degraded_message_mentions_v1_models` | The degraded warning text references `/v1/models`, not legacy `/models`. |

### 3.2 Frontend (`tests/api_hardening.test.cjs`)

See §2.5 above.

---

## 4. Verification matrix

Run on the local Windows CPU host, after this commit:

| Tool                         | Command                                                       | Result                       |
|------------------------------|---------------------------------------------------------------|------------------------------|
| Backend unit + integration   | `python -m pytest -q`                                         | **152 passed**, 1 skipped    |
| Frontend JS contract + UI    | `npm test`                                                    | 4/4 PASS (overlay, api_hardening, ui, preview) |
| Lint                         | `python -m ruff check dr_support tests`                       | All checks passed            |

Test inventory by file:

| Test file                       | Count | Covers                                                            |
|---------------------------------|-------|-------------------------------------------------------------------|
| `tests/test_bridge.py`          | 8     | Bridge contracts, CVAT online safety, weight hashing              |
| `tests/test_workflow.py`        | 8     | Review round-trip, manual sync, error paths                       |
| `tests/test_sync.py`            | 2     | CVAT send / pull idempotency                                      |
| `tests/test_remote.py`          | 29    | Remote provider, mocked integration, token isolation, M0.8 startup-bloker regressions |
| `tests/test_profiles.py`        | 19    | Profile dispatch, invariants, model_api surface, M4 proxy smoke   |
| `tests/test_device.py`          | 22    | GPU device resolver, provider propagation, no-CPU-fallback, /health |
| `tests/test_modal_adapter.py`   | 24    | Modal adapter config, GPU ladder, ASGI surface, SDK integration   |
| `tests/test_lightning_adapter.py` | 41  | Lightning launch script, setup script, runbook coverage, contract unchanged, no-CPU-fallback, no secret leakage |
| `tests/test_browser_ui.py`      | 1     | Real-browser preview smoke (skipped on this host)                 |
| `tests/overlay.test.cjs`        | —     | Imported CVAT geometry overrides AI provenance                    |
| `tests/api_hardening.test.cjs`  | 5     | `api()` defensive JSON / status / body parsing (M0.8)             |
| `tests/ui.test.cjs`             | —     | DOM + real API: navigation, Analyze, grade correction             |
| `tests/preview.test.cjs`        | —     | Offline PREVIEW.html, no API calls, controls disabled             |

Total new tests in M0.8: **8 backend (`tests/test_remote.py`) + 5 frontend
(`tests/api_hardening.test.cjs`)** = **13 tests**.

---

## 5. Windows acceptance (post-`d791b7c`)

Backend restarted with the owner's review environment:

```
APP_PROFILE=review
MODEL_RUNTIME=remote
REMOTE_MODEL_URL=https://8000-01m2taqmanw7pn3h8kz5n54mxe.cloudspaces.litng.ai
HOST=127.0.0.1
PORT=8000
WORKERS=1
REMOTE_MODEL_TOKEN=<owner-managed secret from process env>
```

Smoke results:

```
curl -i http://127.0.0.1:8000/v1/cases
HTTP/1.1 200 OK
content-type: application/json
content-length: 8173
→ 11 cases (1 synthetic SYNTH_001 rev 5 + 10 public HRF 01_dr…10_dr)

curl -i http://127.0.0.1:8000/v1/models
HTTP/1.1 200 OK
content-type: application/json
content-length: 1218
→ 4 descriptors:
    - mock-global       SYNTHETIC_FIXTURE
    - mock-lesion       SYNTHETIC_FIXTURE
    - retfound-aptos5   REMOTE_HTTP_404 (degraded; remote /v1/models returned 404)
    - prism-dr-5fold    REMOTE_HTTP_404 (degraded; remote /v1/models returned 404)

curl -i http://127.0.0.1:8000/ui/index.html
HTTP/1.1 200 OK
content-type: text/html; charset=utf-8
→ serves index.html (case selector + Worklist shell)
```

The Worklist loads; the case selector populates with 11 case IDs;
"Loading review workspace…" is replaced by the Worklist table; no
`Unexpected token 'I'` in the browser console because `api()` no longer
`JSON.parse`s an empty body and degrades the HTTP failure into a
useful message.

STOP condition confirmed: `Analyze` was NOT clicked; GPU acceptance
was NOT repeated; no remote `POST /v1/predict/*` was invoked.

---

## 6. Remote contract probe

Metadata-only GETs against the deployed Lightning endpoint
`https://8000-01m2taqmanw7pn3h8kz5n54mxe.cloudspaces.litng.ai`:

| Path           | HTTP | Content-Type                | Body                       |
|----------------|------|------------------------------|----------------------------|
| `/`            | 404  | `text/plain; charset=utf-8`  | `404 page not found`       |
| `/health`      | 404  | `text/plain; charset=utf-8`  | `404 page not found`       |
| `/models`      | 404  | `text/plain; charset=utf-8`  | `404 page not found`       |
| `/v1/models`   | 404  | `text/plain; charset=utf-8`  | `404 page not found`       |
| `/docs`        | 404  | `text/plain; charset=utf-8`  | `404 page not found`       |
| `/openapi.json`| 404  | `text/plain; charset=utf-8`  | `404 page not found`       |

The default Go HTTP `404 page not found` body suggests the FastAPI
process is **not currently serving** behind the Studio reverse-proxy,
or is mounted under an unknown path prefix that the owner has not
yet exposed. None of the four contract endpoints (`/health`,
`/v1/models`, `/v1/predict/dr`, `/v1/predict/lesions`) is reachable
right now.

This is a **deployment-side concern**, not a code defect. The local
review backend correctly treats the metadata 404 as `REMOTE_HTTP_404`
and continues to serve `/v1/models` as HTTP 200 with an explicit
degraded descriptor, so the Worklist stays unblocked.

When the Lightning deployment is repaired, the proxy will begin
returning full descriptors automatically; no code change is needed.

---

## 7. What's NOT done — explicit owner actions

These are deployment-time concerns that this codebase cannot complete from a
CPU-only host:

- **Live Lightning GPU runbook.** Steps A–N of
  `docs/LIGHTNING_DEPLOYMENT.md` (Studio creation, GPU/T4 selection,
  `bash scripts/setup_lightning.sh`, env-var setup, port-8000 expose,
  smoke `/health` + `/v1/models` + `/v1/predict/dr` +
  `/v1/predict/lesions`) must be re-run against the live Studio. The
  current Studio at `https://8000-01m2taqmanw7pn3h8kz5n54mxe.cloudspaces.litng.ai`
  is returning 404 on every probed path; it is no longer serving the
  model_api process and needs an operator restart.
- **First Lightning Studio creation** if the Studio was deleted.
- **Lightning credit management.** GPU usage consumes Lightning credits;
  the owner monitors credit availability and stops the Studio when not
  in use.
- **`REMOTE_MODEL_TOKEN` rotation.** Rotating the token is a Studio
  env-panel action; the local `.env` must be updated to match.
- **CVAT round-trip on a live workspace.** CVAT Online still requires the
  `CVAT_TOKEN` to be present at the review workstation's runtime. The
  same `OWNER_ACTION_REQUIRED` message still applies.

None of these are governance or implementation issues — they are
operations the owner executes against the deployed Lightning Studio.

---

## 8. Status

**PASS** — Windows Worklist startup blocker is fixed and pinned by
regression tests.

- `GET /v1/cases` returns HTTP 200 with valid JSON for 11 cases.
- `GET /v1/models` returns HTTP 200 with valid JSON for 4 descriptors
  (2 synthetic + 2 remote-degraded) even when the Lightning Model API
  metadata probe fails.
- The Worklist loads; the case selector populates; no
  `Unexpected token 'I'` crash; no permanent "Loading review
  workspace…".
- `REMOTE_MODEL_TOKEN` is never present in the `/v1/models` body, in
  the test log output, or in the user-visible frontend error text.
- All existing tests pass; lint is clean.
- No scientific claims, no Bridge schema changes, no UI redesign, no
  manifest export, no DICOM ingestion, no Drive integration, no
  Dataset Workspace story.

The next gate is owner-side: re-run the Lightning deployment so the
remote `/v1/models` and `/v1/predict/*` endpoints actually serve the
FastAPI process, then re-run the Lightning operator runbook (§7).
