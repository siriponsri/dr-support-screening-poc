# Security and privacy audit, 31 October 2026

Read-only review of the tracked files on `main` (`41c8603`) and the phase 1 finish branch, followed by
fixes on `feat/phase1-finish`. Scope: secrets, sign-in and roles, data leaving the app, the dr-train
gateway, launchers, Docker packages. Clinical semantics and model identities were not changed.

## Fixed on the branch

| # | Finding | Fix |
| --- | --- | --- |
| 1 | Physicians and experts could change the AI server address at runtime | `PUT /v1/model-connection` and its test are administrator-only when sign-in is on |
| 2 | Referral webhook could send any server environment variable as its token | token variable names must start with `REFERRAL_`; checked again before sending |
| 3, 19 | Referral webhook and drop folder could point anywhere | operator lists webhook hosts in `DR_SUPPORT_REFERRAL_HOSTS` and the drop root in `DR_SUPPORT_REFERRAL_DROP_ROOT` (server environment, not the web page); UNC paths refused |
| 6 | Every role except researcher could create, edit or delete Workspaces | create, edit, delete and folder pickers are administrator-only; physicians and experts may still open a Workspace |
| 9 | A nurse could overwrite or un-sign a signed report | a signed report is amended only by a signing role, and the signed version is kept in `amended_versions` |
| 10 | Researcher accounts could read patient name and HN | researchers are refused `/v1/referrals*` and screening reports |
| 12 | Personal tokens could reach any gateway GET path and PRISM control without the workstation check | personal tokens reach only the service paths; PRISM prepare, grant and cancel need an allowed workstation |
| 13 | Revoking a personal token needed a gateway restart | the principals file is reread when it changes |
| 20 | Sending a referral held the case lock during the network call | the call runs outside the lock |
| 22, 23 | Last administrator could be demoted; a reset re-enabled a disabled account; a new password left other sign-ins active | all three fixed |
| 24, 25 | Accounts, server-mode, connector and principals files used the default file mode | written 0600 through one helper |
| 26, 27 | Launcher settings went into ssh and a remote shell unchecked | `DR_HOST`, `DR_KEY` and remote paths validated |
| 28 | Personal accounts (`command=/bin/false`) failed the launcher's SSH check | exit code 1 accepted in personal mode |
| 32 | CSV guard missed tab, CR and pipe | covered |
| 36 | Behind the HTTPS front the app saw `http` while the browser sent `https`, so saves could be refused | `FORWARDED_ALLOW_IPS` set for the review container in both packages |
| 4 (part) | Model API example bound to every address with the token optional | example binds 127.0.0.1 and the token is required |

Tests: `test_pilot_auth`, `test_referral_outbox`, `test_screening_report`, `test_server_mode`,
`test_regular_service`, plus the existing deployment and demo script tests.

## Open (recorded, not fixed in this round)

| # | Finding | Why open / next step |
| --- | --- | --- |
| 4 | Model API serves without a token when `REMOTE_MODEL_TOKEN` is unset | refusing to start changes the model server contract; needs an owner decision |
| 5 | Public-folder demo mode labels any folder as public | needs a signed public manifest or an allow list; the operator is the owner today |
| 7 | No Host check in no-sign-in mode (DNS rebinding on a workstation) | add a trusted-host list; affects every local launcher |
| 8 | `APP_PROFILE=full` (dev only) drops the sign-in middleware | fix the profile merge; never used for real data |
| 11 | Patient name and HN are plain text in case JSON and backups | backup encryption and file mode; field encryption needs a design |
| 14 | Model traffic may use plain http between hosts | allow http only to loopback or tunnels |
| 15 | No global login rate limit | per-address limit and a cap on the failure table |
| 16, 17 | Model containers run as root; the app uses the database superuser | non-root images; least-privilege role (`docs/operations/DATABASE_ROLES.md`) |
| 18 | `HN5071` appears in old receipts and resolver tests | owner to confirm it is synthetic |
| 21 | Session cookie has no `Secure` flag | set it when served over HTTPS |
| 29 to 31, 33 | Error text with paths, server-side folder picker, unbounded admission reads, model API body limit | hardening items |
| 34, 35 | Owner username and paths in examples; team portraits in presentation assets | owner to decide |
| 37 | With sign-in off, anyone can sign under a typed name | deployments run with sign-in; label or refuse later |
| 12 (part) | PRISM jobs are not bound to the person who prepared them | job ids are random; binding needs a gateway change |

## Checked and fine

Password hashing (PBKDF2, 310k iterations), session cookie flags, admin route checks, CSRF coverage with
sign-in on, SQL parameters, `torch.load(weights_only=True)`, no shell subprocesses, HTML escaping on the
print page, request body limit on the review API, origin gates for CVAT and model calls, loopback port
bindings in Compose, read-only image mounts, no secrets or private keys in tracked files.
