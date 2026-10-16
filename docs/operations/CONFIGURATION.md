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
| `DR_SUPPORT_STATE` | review | empty; compatibility path only | no |
| `DR_SUPPORT_WORKSPACE_CATALOG` | review | empty; compatibility path only | no |
| `DR_SUPPORT_CASE_STORE` | review | `postgres` | no |
| `DR_SUPPORT_WORKSPACE_ID` | PostgreSQL case store | optional bootstrap workspace identifier | no |
| `DR_SUPPORT_DATABASE_URL` | PostgreSQL foundation | empty for the project-owned local Docker path; set a private external URL when required | **yes** |
| `DR_SUPPORT_DATABASE_SCHEMA` | PostgreSQL foundation | `dr_support` | no |
| `DR_SUPPORT_DATABASE_CONNECT_TIMEOUT` | PostgreSQL foundation | `5` seconds | no |
| `INFERENCE_DEVICE` | Model API | `cuda:0` | no |
| `MODEL_CPU_THREADS` | local runtime | `4` | no |
| `MODEL_REQUIRE_VERIFIED_ASSETS` | Model API | `1` in `start.sh`; `0` in example for tests | no |
| `MODEL_API_PROVIDER_SET` | Model API | `legacy`; `legacy`, `retfound`, `prism`, `uspec`, or `combined` | no |
| `MODEL_API_PYTHON` | Model API launcher | `.venv/bin/python`; optional isolated runtime interpreter | no |
| `DR_SUPPORT_RELAX_DEVICE` | development/tests | `0` | no |
| `RETFOUND_SOURCE` | Model API | `local-state/bridge/sources/RETFound` | no |
| `RETFOUND_WEIGHTS` | Model API | `local-state/bridge/retfound-aptos.pth` | no |
| `PRISM_SOURCE` | Model API | `local-state/bridge/sources/PRISM-DR` | no |
| `PRISM_WEIGHTS` | Model API | `local-state/bridge/prism` | no |
| `PRISM_THRESHOLDS` | review evidence | `{}` | no |
| `USPEC_MODEL_DIR` | USPEC Model API | empty; external read-only artifact directory | no |
| `USPEC_ENABLE_CANDIDATE_LOAD` | USPEC Model API | `0`; explicitly set to `1` for controlled candidate qualification | no |
| `REVIEW_MAX_PER_CLASS` | review evidence | `25` | no |
| `REVIEW_MAX_TOTAL` | review evidence | `80` | no |
| `CVAT_URL` | optional CVAT | `https://app.cvat.ai` | no |
| `CVAT_PROJECT_ID` | optional CVAT | empty | no |
| `CVAT_TOKEN` | optional CVAT | empty | yes |

The review profile requires `MODEL_RUNTIME=remote` and never loads local weights. The Model API profile requires `MODEL_RUNTIME=local`. `INFERENCE_DEVICE=cuda:0` is the production default; an explicit CPU setting is for local development and contract testing only. `MODEL_REQUIRE_VERIFIED_ASSETS=1` is required for the normal server path. The review profile remains usable in manual mode when `REMOTE_MODEL_URL` is empty or the remote is unavailable.

## Runtime profiles

| Profile | `APP_PROFILE` | `MODEL_RUNTIME` | Purpose |
| --- | --- | --- | --- |
| Review workstation | `review` | `remote` | Clinician UI, local review state, and proxy calls to the hospital Model API. |
| Hospital Model API | `model_api` | `local` | GPU inference endpoints with verified RETFound and PRISM-DR assets (`MODEL_API_PROVIDER_SET=legacy`). |
| RETFound-only Model API | `model_api` | `local` | CFP-only research comparator with pinned RETFound assets verified (`MODEL_API_PROVIDER_SET=retfound`). |
| PRISM-only Model API | `model_api` | `local` | Lesion assistance with pinned PRISM assets verified (`MODEL_API_PROVIDER_SET=prism`). |
| USPEC-only Model API | `model_api` | `local` | UWF grading candidate with only the exact external USPEC artifact verified (`MODEL_API_PROVIDER_SET=uspec`). |
| Combined Model API | `model_api` | `local` | RETFound, PRISM-DR, and USPEC (`MODEL_API_PROVIDER_SET=combined`); every enabled provider is verified independently. |
| Combined local demo | `full` | `local` | Development-only combined surface for synthetic smoke work. |

The application rejects incompatible profile/runtime combinations. The review profile may start without a configured Model API; model actions remain unavailable until a compatible capability is healthy and advertised.

The default `legacy` Model API selection preserves the existing RETFound CFP and PRISM CFP setup and verification path. For USPEC qualification, use a separate Python environment compatible with the recorded USPEC runtime, point `MODEL_API_PYTHON` to it, set `MODEL_API_PROVIDER_SET=uspec`, and set `USPEC_MODEL_DIR` to the external artifact directory. The USPEC directory is read-only and must remain outside this repository. `USPEC_ENABLE_CANDIDATE_LOAD=1` is an explicit opt-in for controlled inference; CUDA is required, and this opt-in does not change the capability's disabled release status or establish clinical validation or production rights. Repository `.[models]` pins are not the USPEC runtime and must not be installed over a qualified USPEC environment.

`REVIEW_THRESHOLDS`, `REVIEW_MAX_PER_CLASS`, and `REVIEW_MAX_TOTAL` bound the visual/pre-label subset only. They do not alter raw PRISM output or model confidence values. Changing environment configuration requires a process restart.

## PostgreSQL foundation configuration

`DR_SUPPORT_DATABASE_URL` is a server-side PostgreSQL connection URL. Store the real value in a private `.env`, service environment, or approved secret manager. Do not expose it through React, browser storage, API responses, or logs. When blank on Windows, the release launcher provisions project-owned PostgreSQL with credentials in ignored `local-state/release/postgres.env`.

The packaged Windows workstation does not treat `FIRST_RUN.bat` or `CHECK_SYSTEM.bat` as normal review readiness unless external or project-owned PostgreSQL is present and a credential-safe `SELECT 1` connectivity check succeeds. `DR_SUPPORT_CASE_STORE=sqlite` is an explicit legacy compatibility mode and is reported as not ready for normal managed review; the launchers never silently fall back to SQLite.

Case-store mode precedence follows `_resolve_case_store_mode`: an explicit `DR_SUPPORT_CASE_STORE` is used first; otherwise `DR_SUPPORT_DATABASE_URL` selects PostgreSQL; otherwise function-level `case_store_mode` or `state_path` compatibility arguments apply; if none is supplied, the default remains PostgreSQL. `DR_SUPPORT_STATE` and `DR_SUPPORT_WORKSPACE_CATALOG` alone do not implicitly select SQLite. Set `DR_SUPPORT_CASE_STORE=sqlite` for an explicit legacy compatibility run, with the legacy paths supplied for that run. Managed PostgreSQL workspace creation and switching do not require or open a local SQLite database path; any legacy path retained on an imported profile is provenance only.

PostgreSQL integration tests are opt-in and require both `DR_SUPPORT_TEST_DATABASE_URL` and `DR_SUPPORT_TEST_DATABASE_NAME`. The configured URL's database name must exactly match the explicit name, which must contain a distinct `test` token such as `dr_support_test`. Tests create and remove only uniquely named `dr_support_test_*` schemas; they never drop, truncate, or recreate the configured database.


## Authorized Windows managed readers

The owner-approved Windows private-evaluation policy can retain an existing
platform-managed read-only reader without changing Windows ACLs or sandbox
protections. This is opt-in and server-only. Never authorize a group by display
name alone: independently verify its SID, membership, purpose and effective
rights, and obtain approval for the exact hospital roots.

`DR_SUPPORT_HOSPITAL_WINDOWS_READ_ONLY_SIDS` is a private JSON object mapping
exact authorized root paths to one verified machine/domain group SID each:

```json
{"C:/approved/uwf":["<verified-managed-reader-SID>"],"C:/approved/cfp":["<verified-managed-reader-SID>"]}
```

Both roots must already be authorized by the existing hospital-root configuration.
The reader mapping also requires `DR_SUPPORT_HOSPITAL_SCOPE=PRIVATE_PROJECT_EVALUATION`.
No entry means no extra reader is accepted. Invalid JSON, relative/unavailable/
redirected or unapproved roots, duplicate canonical bindings, display names and
well-known broad-group SIDs fail closed. This setting does not grant access or
modify ACLs; it recognizes only an existing approved read grant.

On Windows, the approved reader can have at most ReadAndExecute plus Synchronize.
Write, append, delete, ownership and permission-change grants remain rejected,
including grants on descendants. Operator, SYSTEM and Administrators keep their
existing administrative role. Unknown principals remain rejected. POSIX hosts
ignore this Windows setting and retain the private mode-bit requirement.

Keep actual paths/SIDs in private configuration. They are not image provenance,
export authorization or clinician confirmation, and must not be accepted from
browser requests or persisted in the review database. Do not remove a managed
sandbox group, alter its membership, or disable execution protections to pass
admission. Synthetic permission tests must never change real image-root ACLs.


## Authorized hospital transmission from a Windows Review workstation

Hospital admission and remote model transmission have separate opt-ins. After
explicit authorization to send the named hospital roots to the selected private
research Model API, configure both the Review hospital-root settings and this
model boundary in the workstation's private environment:

```dotenv
MODEL_HOSPITAL_SCOPE=PRIVATE_PROJECT_EVALUATION
MODEL_ALLOW_AUTHORIZED_HOSPITAL=1
```

The same model-boundary opt-in is required on the Model API host. A nonempty
`REMOTE_MODEL_TOKEN` and verified `REMOTE_MODEL_URL` are also required; keep the
token in private operator configuration. The remote adapter checks this model
boundary on Windows before transmission, even when the Review has already
admitted the roots. Missing settings must remain fail-closed. Admission alone
does not authorize transmission, and these flags do not authorize export.

Keep `HOSPITAL_AUTHORIZED` provenance. Do not relabel real hospital inputs as
public or synthetic to pass the gate. Images marked as needing admission review
remain blocked until the existing human review flow resolves them. Update only
private configuration after authorization and restart the existing workstation;
never weaken source/privacy checks or change source images to make a run pass.
