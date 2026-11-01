# Configuration

Copy `.env.example` into a private environment file, or set the variables through the process or service
manager. Never commit the private file. Changing configuration needs a process restart.

## Variables

| Variable | Used by | Default / example | Secret |
| --- | --- | --- | --- |
| `APP_PROFILE` | all | `review`, `model_api`, or `full` | no |
| `MODEL_RUNTIME` | all | `remote` for `review`; `local` for `model_api`/`full` | no |
| `HOST` | server | `127.0.0.1` review; `0.0.0.0` service | no |
| `PORT` | server | `8000` review; `7860` Model API script | no |
| `WORKERS` | server | `1` (PRISM preview binding requires exactly one) | no |
| `REMOTE_MODEL_URL` | review | empty until a Model API is deployed | no |
| `REMOTE_MODEL_TOKEN` | review | empty; bearer token for the Model API | yes |
| `DR_SUPPORT_CASE_STORE` | review | `postgres` (`sqlite` is explicit legacy compatibility only) | no |
| `DR_SUPPORT_DATABASE_URL` | review | empty for the project-owned local Docker PostgreSQL; set a private external URL when required | **yes** |
| `DR_SUPPORT_DATABASE_SCHEMA` | review | `dr_support` | no |
| `DR_SUPPORT_DATABASE_CONNECT_TIMEOUT` | review | `5` seconds | no |
| `DR_SUPPORT_WORKSPACE_ID` | review | optional bootstrap workspace identifier | no |
| `DR_SUPPORT_STATE`, `DR_SUPPORT_WORKSPACE_CATALOG` | review | empty; legacy compatibility paths only | no |
| `DR_SUPPORT_AUTH_FILE` | review | path of the private accounts file; sign-in and roles are on when set (server mode and referral connector settings live beside it) | file holds password hashes only |
| `DR_SUPPORT_REFERRAL_HOSTS` | review | comma-separated host names a referral webhook may send to; empty means no webhook | no |
| `DR_SUPPORT_REFERRAL_DROP_ROOT` | review | folder every referral drop folder must sit inside; unset means no drop folder | no |
| `DR_HOST`, `DR_KEY`, `DR_TOKEN_FILE` | QA launcher (personal access) | the person's dr-train route, private key path and personal token file; see [DR_TRAIN_ACCESS.md](DR_TRAIN_ACCESS.md) | key and token are **yes** |
| `INFERENCE_DEVICE` | Model API | `cuda:0` | no |
| `MODEL_CPU_THREADS` | local runtime | `4` | no |
| `MODEL_REQUIRE_VERIFIED_ASSETS` | Model API | `1` in `start.sh`; `0` in the example for tests | no |
| `MODEL_API_PROVIDER_SET` | Model API | `legacy`; or `retfound`, `prism`, `uspec`, `combined` | no |
| `MODEL_API_PYTHON` | Model API launcher | `.venv/bin/python`; optional isolated interpreter | no |
| `DR_SUPPORT_RELAX_DEVICE` | development and tests | `0` | no |
| `RETFOUND_SOURCE`, `RETFOUND_WEIGHTS` | Model API | `local-state/bridge/sources/RETFound`, `local-state/bridge/retfound-aptos.pth` | no |
| `PRISM_SOURCE`, `PRISM_WEIGHTS` | Model API | `local-state/bridge/sources/PRISM-DR`, `local-state/bridge/prism` | no |
| `PRISM_THRESHOLDS` | review evidence | `{}` | no |
| `USPEC_MODEL_DIR` | USPEC Model API | empty; external read-only artifact directory | no |
| `USPEC_ENABLE_CANDIDATE_LOAD` | USPEC Model API | `0`; set `1` only for controlled candidate inference | no |
| `REVIEW_MAX_PER_CLASS`, `REVIEW_MAX_TOTAL` | review evidence | `25`, `80` (bound the visual subset only; raw PRISM output is unchanged) | no |
| `CVAT_URL`, `CVAT_PROJECT_ID` | optional CVAT | `https://app.cvat.ai`, empty | no |
| `CVAT_TOKEN` | optional CVAT | empty | yes |

## Runtime profiles

| Profile | `APP_PROFILE` | `MODEL_RUNTIME` | Purpose |
| --- | --- | --- | --- |
| Review workstation | `review` | `remote` | Clinician UI and review state; model calls go to `REMOTE_MODEL_URL` |
| Model API | `model_api` | `local` | GPU inference with verified assets; `MODEL_API_PROVIDER_SET` picks `legacy` (RETFound + PRISM), `retfound`, `prism`, `uspec` or `combined` |
| Local demo | `full` | `local` | Development only, synthetic fixtures and public samples |

The application refuses incompatible profile and runtime combinations; there is no silent fallback. The
review profile starts without a Model API and stays usable in manual mode. `INFERENCE_DEVICE=cuda:0` is the
production default; a CPU setting is for development and contract tests only.

USPEC needs its own Python environment (it uses a newer Torch than the repository `models` extra): point
`MODEL_API_PYTHON` at it, set `MODEL_API_PROVIDER_SET=uspec` and `USPEC_MODEL_DIR` to the read-only artifact
directory outside the repository. Never install the repository model pins over that environment.

## PostgreSQL

`DR_SUPPORT_DATABASE_URL` is server-side only: keep it in a private `.env`, service environment or secret
manager, never in React, browser storage, API responses or logs. When it is blank on Windows, the release
launcher provisions a project-owned Docker PostgreSQL with credentials in ignored
`local-state/release/postgres.env` and checks `SELECT 1`. The launchers never fall back to SQLite.

Case-store precedence (`_resolve_case_store_mode`): an explicit `DR_SUPPORT_CASE_STORE` first, then
`DR_SUPPORT_DATABASE_URL` selects PostgreSQL, then compatibility arguments; the default is PostgreSQL.
`DR_SUPPORT_STATE` alone does not select SQLite.

PostgreSQL integration tests are opt-in: set `DR_SUPPORT_TEST_DATABASE_URL` and
`DR_SUPPORT_TEST_DATABASE_NAME` (the database name must match exactly and contain a `test` token, such as
`dr_support_test`). Tests create and drop only `dr_support_test_*` schemas.

## Containers

The public template keeps `HOST=127.0.0.1` for the native workstation. In a private container environment
set `HOST=0.0.0.0`, `PORT=8000`, `WORKERS=1`, `APP_PROFILE=review`, `MODEL_RUNTIME=remote`,
`DR_SUPPORT_CASE_STORE=postgres` and the server-side database URL; keep the published host port on
loopback. The packages in `deployment/webapp` and `deployment/hospital-server` already do this.

## Hospital roots and transmission (private evaluation only)

Admission of real hospital folders and sending them to a Model API are separate opt-ins, both server-side:

- `DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS` (JSON) binds approved UWF and CFP roots. On Windows, admission needs
  ACLs restricted to the operator, SYSTEM, local Administrators and any reader SID approved in
  `DR_SUPPORT_HOSPITAL_WINDOWS_READ_ONLY_SIDS` (JSON: exact root path to one verified group SID, read and
  execute only; needs `DR_SUPPORT_HOSPITAL_SCOPE=PRIVATE_PROJECT_EVALUATION`). The app never changes ACLs.
- Transmission additionally needs `MODEL_HOSPITAL_SCOPE=PRIVATE_PROJECT_EVALUATION` and
  `MODEL_ALLOW_AUTHORIZED_HOSPITAL=1` on both the workstation and the Model API host, plus a token. Neither
  flag authorizes export.

Missing or invalid settings fail closed. Keep real paths and SIDs in private configuration; never relabel
hospital images as public to pass a gate.
