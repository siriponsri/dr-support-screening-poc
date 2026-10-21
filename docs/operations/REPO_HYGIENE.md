# Review application packaging and repository hygiene

This guide covers the CPU review application only. Existing Model API owners retain their Dockerfiles, gateway, GPU profiles, source/checkpoint contracts and services. No model service is created by these checks. Container recipes are statically reviewed; this hygiene change has **not** built/pulled an image, started Docker, connected to a DB, changed networking or deployed anything.

## Keep source and runtime separate

| Location | Contents and treatment |
|---|---|
| Git source | Application code, documentation, public `.env.example`, `uv.lock`, npm locks and hashed review dependency export. Stage explicit paths only. |
| Private environment, outside checkout | PostgreSQL URL, Model API/CVAT tokens, service/password files. Inject at runtime; never use build arguments or frontend environment for credentials. |
| `/data/input` | Authorized immutable originals mounted read-only. Never bake hospital images into an image or copy them into frontend/public. |
| `/data/state`, `/data/output` | Separate writable operator-owned mounts for compatibility state/output. Normal case/catalog storage remains PostgreSQL; no automatic SQLite fallback. Qualify UID10001 access before rollout. |
| External model paths | Verified read-only mounts owned by the separate model deployment. Review image has no model extras, weights or GPU requirement. |
| Backup/export destinations | Approved external storage with access/retention controls; never Git or build context. Original image files are outside the DB backup. |

`.gitignore` adds private env variants, DB journals/dumps, credentials, weights and standard local output/cache paths. It does not untrack existing files or delete owner artifacts. Arbitrary source images still require deliberate provenance review; ignore rules cannot determine whether pixels contain identifiers.

The review Dockerfile has its own default-deny `Dockerfile.review.dockerignore`. Only required application/frontend inputs and two existing source-labelled synthetic preview PNGs are admitted. Presentation screenshots, upstream retinal examples, portraits, docs, tests, local-state, dependencies, built dist and private/model artifacts are excluded. Other Dockerfile contexts continue using their existing/root policy. Requalify the actual Docker engine's Dockerfile-specific ignore handling before any build; the audit's context inventory is a static policy check, not a daemon receipt.

## Offline checks before sharing or building

Generate a tracked path list in a normally authorized Git context (PowerShell 7 for native byte redirection below), then run:

```powershell
git ls-files -z > <outside-repo-evidence>/tracked-paths.bin
python -B scripts/audit/check_repo_hygiene.py --tracked-paths-file <outside-repo-evidence>/tracked-paths.bin --json-out <outside-repo-evidence>/hygiene.json
python -B -m pytest -q -p no:cacheprovider --basetemp=<fresh-evidence-directory> tests/test_repo_hygiene_audit.py
```

The checker reads tracked text and the **public template only**; it never loads a private `.env`, image pixels, DB, checkpoint, credentials, network or environment values. It reports key/path/line/reason, never matched token values. High-confidence token patterns and filename checks are not exhaustive secret or PHI certification. Existing screenshots/retinal examples still need the owner's source/publication-rights review before source/presentation publication.

At the reviewed baseline there are no checked-in GitHub/GitLab/Azure/Jenkins CI workflow files. External repository apps, hooks, organization workflows and deployment connections were not inspected. Before a later push, review remote CI/deployment settings and credentials with the owner; absence of tracked YAML does not prove a push cannot trigger deployment. This task does not push or add CI.

## Reproduce dependencies without upgrading

`uv.lock` and both npm locks remain unchanged. Use `uv sync --frozen` and `npm ci`, not unconstrained install/update commands. The review runtime export was made from the existing lock, offline, without packages being installed or downloaded:

```text
uv export --frozen --offline --no-dev --no-emit-project --no-header --no-annotate --format requirements-txt > deployment/dual-mode/review-requirements.lock
```

The Dockerfile installs this full core closure with `--require-hashes --only-binary=:all: --no-deps`; model/test/browser and optional DICOM-codec extras are absent, as in the previous core-only image. Qualify required hospital formats separately; any added codec closure needs its own reviewed hashed export. It runs copied source via `python -m dr_support.run`, avoiding an unlocked editable-build backend installation. Regenerate/check the export whenever the project lock changes. Offline deployment additionally needs approved preloaded base images, wheels/npm cache or a previously built application image; this export alone is not an offline installation bundle.

## Build and run after operator approval

Use the existing `deployment/dual-mode/Dockerfile.review`. Supply the exact reviewed 40-character `SOURCE_COMMIT`; the Dockerfile rejects an unset/placeholder identity. Override `FRONTEND_BASE_IMAGE` and `REVIEW_BASE_IMAGE` with approved platform-specific digest-pinned images for release. Their development defaults remain mutable tags; no digest was invented or fetched by this task. Record image/toolchain/architecture and source, lock, artifact hashes. Full bit-for-bit reproducibility and container build remain unqualified.

Example command shapes, **not executed here**:

```text
docker build -f deployment/dual-mode/Dockerfile.review --build-arg SOURCE_COMMIT=<reviewed-sha> --build-arg FRONTEND_BASE_IMAGE=<approved-node-image@sha256:digest> --build-arg REVIEW_BASE_IMAGE=<approved-python-image@sha256:digest> -t dr-screening/review:<reviewed-sha> .
docker run --name <owned-review-container> --read-only --tmpfs /tmp --env-file <external-private-environment> --mount type=bind,src=<approved-originals>,dst=/data/input,readonly --mount type=bind,src=<state>,dst=/data/state --mount type=bind,src=<output>,dst=/data/output -p 127.0.0.1:<approved-port>:8000 dr-screening/review:<reviewed-sha>
```

Prepare existing external PostgreSQL and approved remote-model/manual configuration separately; this container never provisions a database. The public native-workstation template deliberately retains `HOST=127.0.0.1`. In the private container environment, explicitly use `HOST=0.0.0.0`, `PORT=8000`, `WORKERS=1`, `APP_PROFILE=review`, `MODEL_RUNTIME=remote`, `DR_SUPPORT_CASE_STORE=postgres` and the server-side DB URL; the host publish address in the example stays loopback-only. Copying the native template unchanged would bind only inside the container's loopback. Mount ownership, source paths referenced by workspace metadata, read-only root operation and runtime compatibility require operator acceptance. Do not run the full GPU Compose preflight/start merely to check review packaging. Existing Compose health definitions can override Dockerfile health; qualify the selected launch path rather than assuming inheritance.

## Liveness, readiness, backup and rollback

The Dockerfile probe checks both HTTP success and `/health` status `PASS`/`PASS_WITH_WARNINGS`. It is **liveness only**: current `/health` does not verify DB connectivity or workspace completeness. Before use, separately verify the expected frontend build identity, operator-approved PostgreSQL readiness diagnostic, active workspace/source mounts and an authorized synthetic save/reload workflow. Check model capabilities/readiness separately; offline AI means manual review, never a normal grade. No such DB/runtime check ran in this hygiene task.

Before cutover, back up PostgreSQL, managed workspace metadata, approved outputs/snapshots and immutable originals outside DB, along with release/lock/build identity. Keep private environment material in the approved secret backup process, separate from repository/logs. For an approved DB operator, a service-file alias can avoid putting a DSN/password on the command line: `pg_dump --dbname=service=dr_review --format=custom --file=<external-backup>/review.dump`. Do not run this against the model team's DB to fill a missing acceptance result.

Restore qualification requires a fresh isolated approved target, e.g. `pg_restore --dbname=service=dr_review_isolated_restore --exit-on-error --no-owner --no-privileges <backup>`, plus restored original-file hashes, case/snapshot counts, revisions and source references. Confirm the alias points to that isolated target before executing; no restore was run here. See [deployment handoff](../audit/WEB_DEPLOYMENT_HANDOFF.md) for the complete originals-inclusive procedure.

This change contains no schema migration. Roll back only the owned review application to its previous compatible image/config digest; retain current clinical writes, DB volumes and originals. Do not use `down -v`, stale DB restore, blanket Git cleanup or process-name kills as application rollback. Full backup/restore, Docker build/start, ingress, mount permissions and clinical UAT remain **NOT_RUN**.
