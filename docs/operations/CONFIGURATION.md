# Configuration

Copy `.env.example` into a private environment file or configure variables through the process/service manager. Never commit the private file.

| Variable | Used by | Default/example | Secret |
| --- | --- | --- | --- |
| `APP_PROFILE` | all | `review`, `model_api`, or `full` | no |
| `MODEL_RUNTIME` | all | `remote` for `review`; `local` for `model_api`/`full` | no |
| `HOST` | server | `127.0.0.1` review; `0.0.0.0` service | no |
| `PORT` | server | `8000` review; `7860` Model API script | no |
| `WORKERS` | server | `1` | no |
| `REMOTE_MODEL_URL` | review | empty until Model API is deployed | no |
| `REMOTE_MODEL_TOKEN` | review | empty; optional bearer token | yes |
| `DR_SUPPORT_STATE` | review | local runtime default when empty | no |
| `DR_SUPPORT_WORKSPACE_CATALOG` | review | local workspace catalog default when empty | no |
| `DR_SUPPORT_DATABASE_URL` | PostgreSQL foundation | `postgresql://dr_support_app:change-me@127.0.0.1:5432/dr_support` | **yes** |
| `DR_SUPPORT_DATABASE_SCHEMA` | PostgreSQL foundation | `dr_support` | no |
| `DR_SUPPORT_DATABASE_CONNECT_TIMEOUT` | PostgreSQL foundation | `5` seconds | no |
| `INFERENCE_DEVICE` | Model API | `cuda:0` | no |
| `MODEL_CPU_THREADS` | local runtime | `4` | no |
| `MODEL_REQUIRE_VERIFIED_ASSETS` | Model API | `1` in `start.sh`; `0` in example for tests | no |
| `DR_SUPPORT_RELAX_DEVICE` | development/tests | `0` | no |
| `RETFOUND_SOURCE` | Model API | `local-state/bridge/sources/RETFound` | no |
| `RETFOUND_WEIGHTS` | Model API | `local-state/bridge/retfound-aptos.pth` | no |
| `PRISM_SOURCE` | Model API | `local-state/bridge/sources/PRISM-DR` | no |
| `PRISM_WEIGHTS` | Model API | `local-state/bridge/prism` | no |
| `PRISM_THRESHOLDS` | review evidence | `{}` | no |
| `REVIEW_MAX_PER_CLASS` | review evidence | `25` | no |
| `REVIEW_MAX_TOTAL` | review evidence | `80` | no |
| `CVAT_URL` | optional CVAT | `https://app.cvat.ai` | no |
| `CVAT_PROJECT_ID` | optional CVAT | empty | no |
| `CVAT_TOKEN` | optional CVAT | empty | yes |

The review profile requires `MODEL_RUNTIME=remote` and never loads local weights. The Model API profile requires `MODEL_RUNTIME=local`. `INFERENCE_DEVICE=cuda:0` is the production default; an explicit CPU setting is for local development and contract testing only. `MODEL_REQUIRE_VERIFIED_ASSETS=1` is required for the normal server path.

## Runtime profiles

| Profile | `APP_PROFILE` | `MODEL_RUNTIME` | Purpose |
| --- | --- | --- | --- |
| Review workstation | `review` | `remote` | Clinician UI, local review state, and proxy calls to the hospital Model API. |
| Hospital Model API | `model_api` | `local` | GPU inference endpoints with verified local RETFound and PRISM-DR assets. |
| Combined local demo | `full` | `local` | Development-only combined surface for synthetic smoke work. |

The application rejects incompatible profile/runtime combinations. The review profile may start without a configured Model API; model actions remain unavailable until the connection is healthy.

`REVIEW_THRESHOLDS`, `REVIEW_MAX_PER_CLASS`, and `REVIEW_MAX_TOTAL` bound the visual/pre-label subset only. They do not alter raw PRISM output or model confidence values. Changing environment configuration requires a process restart.

## PostgreSQL foundation configuration

`DR_SUPPORT_DATABASE_URL` is a server-side PostgreSQL connection URL. Store the real value in a private `.env`, service environment, or approved secret manager. Do not expose it through React, browser storage, API responses, or logs. The committed `.env.example` value is a placeholder only.

The Phase P1-F foundation does not yet switch the existing case store or Workspace Manager to PostgreSQL; those changes belong to P1-A and P1-B. Code that explicitly selects PostgreSQL calls `PostgresSettings.from_env()` and fails when `DR_SUPPORT_DATABASE_URL` is missing, invalid, or unavailable. It never chooses SQLite as an implicit fallback.

PostgreSQL integration tests are opt-in and require both `DR_SUPPORT_TEST_DATABASE_URL` and `DR_SUPPORT_TEST_DATABASE_NAME`. The configured URL's database name must exactly match the explicit name, which must contain a distinct `test` token such as `dr_support_test`. Tests create and remove only uniquely named `dr_support_test_*` schemas; they never drop, truncate, or recreate the configured database.
