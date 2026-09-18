# Remote Model API Contract (v0.2.1)

This document describes the externally deployed **Remote Model API** that the
backend proxies to when `MODEL_RUNTIME=remote`. It is the contract the
deployment team must implement; the backend ships only the HTTP client side.

This delivery **does not deploy any models**. It only defines the contract and
ships a mocked integration test suite so a future deployment can be validated.

## Transport

- HTTPS in production; HTTP only permitted for local development.
- Bearer-token authentication is optional. When the deployment requires
  authentication, set `REMOTE_MODEL_TOKEN` in the backend runtime environment.
  The token is sent only as `Authorization: Bearer <token>` and is never logged,
  persisted, or returned to the UI.
- The backend never follows redirects from the remote.
- Default request timeout: 30 s for inference, 5 s for `/models`.
- Failures are translated to HTTP status codes by the backend:
  - Timeout → `504 Gateway Timeout`
  - Remote 4xx/5xx (other than auth) → `502 Bad Gateway`
  - Auth failure (401/403) → metadata surfaces `REMOTE_AUTH_FAILED`; the backend
    inference call surfaces the same `502` with a sanitized message.
  - Malformed JSON / schema mismatch → `502 Bad Gateway`

## Endpoints

### `GET /health`

Informational. Returned by the deployment, not consumed by the backend proxy.

### `GET /models`

Returns a JSON array of model descriptors. The backend reads
`model_id`, `task`, `revision`, `checkpoint_sha256`, `modalities`, `status`,
`warnings`, and `preprocessing` from each entry.

```json
[
  {
    "model_id": "retfound-aptos5",
    "task": "global",
    "revision": "remote-rev-aaaa",
    "checkpoint_sha256": {"retfound-remote": "aabbcc..."},
    "modalities": ["CFP"],
    "status": "LOADED",
    "warnings": ["research-only"],
    "preprocessing": "RGB; resize short edge 256 bicubic; center crop 224"
  },
  {
    "model_id": "prism-dr-5fold",
    "task": "lesion-roi",
    "revision": "remote-rev-bbbb",
    "checkpoint_sha256": {"prism-remote": "11ff..."},
    "modalities": ["CFP"],
    "status": "LOADED",
    "warnings": ["research-only"],
    "preprocessing": "ROI cropper; per-lesion five-fold inference"
  }
]
```

The backend caches the latest observed `revision` and `checkpoint_sha256` from
inference responses (which carry `provenance`) and merges them with this list
in the Models & Audit metadata.

### `POST /v1/predict/dr`

Grade-only inference. Accepts the JSON envelope below and returns a
**Bridge v1 `GlobalResult`** (see `dr_support/contracts.py`).

### `POST /v1/predict/lesions`

Lesion ROI inference. Accepts the same envelope and returns a
**Bridge v1 `LesionResult`** (see `dr_support/contracts.py`).

### Request envelope

```json
{
  "image_id": "<id>",
  "modality": "CFP" | "UWF",
  "model_id": "retfound-aptos5" | "prism-dr-5fold",
  "image_b64": "<base64 of admitted image bytes>",
  "image_sha256": "<hex>",
  "source_type": "PUBLIC" | "SYNTHETIC",
  "width":  <px>,
  "height": <px>
}
```

The image bytes are exactly the same bytes served by the backend's
`/v1/images/{image_id}` endpoint. The remote must validate that `image_sha256`
matches `sha256(base64.b64decode(image_b64))` and reject the request otherwise.

### Response shape

For `/v1/predict/dr`:

```json
{
  "schema_version": "bridge.v1",
  "model_id": "retfound-aptos5",
  "model_version": "<remote revision>",
  "modality": "CFP",
  "state": "AI_SUGGESTION" | "UNCERTAIN" | "UNGRADABLE" | "UNSUPPORTED",
  "grade": 0,
  "probabilities": [0.05, 0.10, 0.70, 0.10, 0.05],
  "confidence": 0.70,
  "warnings": ["..."],
  "provenance": {
    "image_sha256": "<hex>",
    "source_type": "PUBLIC" | "SYNTHETIC",
    "preprocessing": "...",
    "checkpoint_sha256": {"...": "<hex>"},
    "source_revision": "<remote revision>"
  }
}
```

For `/v1/predict/lesions`:

```json
{
  "schema_version": "bridge.v1",
  "model_id": "prism-dr-5fold",
  "model_version": "<remote revision>",
  "modality": "CFP",
  "state": "AI_SUGGESTION" | "UNSUPPORTED",
  "width":  <px>,
  "height": <px>,
  "lesions": [
    {
      "source_label": "MA" | "HE" | "EX" | "SE",
      "canonical_label": "MICROANEURYSM" | "HEMORRHAGE" | "HARD_EXUDATE" | "SOFT_EXUDATE",
      "rectangle": [x1, y1, x2, y2],
      "score": 0.0,
      "state": "AI_SUGGESTION"
    }
  ],
  "warnings": ["..."],
  "provenance": { "...": "see above" }
}
```

Lesion rectangles are in **original-image pixel coordinates** (not crop-local).
A rectangle must satisfy `0 <= x1 < x2 <= width` and `0 <= y1 < y2 <= height`.
Empty detections are valid; they do not prove absence of lesions.

## Model identifiers (stable)

| `model_id`         | task         | path                      |
|--------------------|--------------|---------------------------|
| `retfound-aptos5`  | `global`     | `POST /v1/predict/dr`     |
| `prism-dr-5fold`   | `lesion-roi` | `POST /v1/predict/lesions`|

The backend UI already references these identifiers. Adding or renaming a
remote model requires updating `dr_support/providers/remote.py` and the
Models & Audit metadata contract.

## What this contract does not include

- No raw image upload endpoint on the remote (image bytes travel in the
  inference envelope to avoid a second round-trip).
- No clinical record persistence on the remote (the backend SQLite is the
  source of truth for review state).
- No CVAT integration on the remote (CVAT Online remains the geometry editor).
- No scientific performance or calibration claims — those belong to the
  separate model release notes and are not made here.
