# Retinal Review Workbench

Software version: **0.7.0**

<p align="center"><img src="assets/dr-support-logo.svg" width="104" alt="Retinal Review Workbench logo"></p>

Retinal Review Workbench is a clinician-controlled retinal screening review and dataset workspace. It admits retinal images, resolves patient and eye context, keeps the original source and derived analysis traceable, and supports optional model evidence before human review and export.

It is a public/synthetic research and clinical-support proof of concept. It is not autonomous diagnosis, referral, or a regulated medical device.

![Hospital deployment architecture](assets/system-architecture.png)

## Clinician workflow

1. Start or select a local Workspace with an input folder, output folder, and SQLite review database.
2. Scan the input folder. The Worklist reports image readiness, patient/eye context, review status, and unsupported inputs in plain language.
3. Open an eligible image in Review. The original image stays primary; zoom, pan, and full-screen inspection remain available.
4. Run model assistance when needed. RETFound provides a DR grade suggestion; PRISM-DR provides optional lesion overlays. Overlay labels show class and score such as `HE - 0.90`.
5. Toggle or filter overlays. Review is read-only inspection; optional AI ROI correction or removal is available from **Edit Annotations**. No per-lesion confirmation is required before clinician review can be completed.
6. Open **Clinician Review** to confirm the final DR grade. Use **Edit Annotations** only when a human annotation or an optional AI ROI correction/removal is needed, then confirm the active annotation set when appropriate. Advanced geometry work may use CVAT.
7. Inspect Models & Audit for read-only model, inference, hash, and annotation provenance, then review the separate DR-ready and Lesion-ready states in Datasets before export.

![Clinician workflow](assets/clinician-workflow.png)

The legacy `/ui/` surface remains mounted for compatibility with existing local integrations. Normal users should open `/app/`.

## Architecture

The review workstation runs the `review` profile and never loads model weights. It calls the provider-neutral Model API over the configured hospital network. The GPU host runs `model_api` with `MODEL_RUNTIME=local`, verified local assets, and one worker by default. CVAT Online is optional and is not required for offline review or export.

| Component | Role |
| --- | --- |
| Review application | React/Vite clinician UI served by FastAPI at `/app/`; local SQLite review state and workspace catalog. |
| RETFound | Five-class DR grade suggestion through `retfound-aptos5`; score output is uncalibrated model evidence. |
| PRISM-DR | Lesion ROI suggestions through `prism-dr-5fold`; raw detections remain distinct from bounded display/pre-label evidence. |
| Model API | FastAPI endpoints `/health`, `/v1/models`, `/v1/predict/dr`, and `/v1/predict/lesions`. |
| Dataset export | Provenance-preserving `manifest.json`, `images.csv`, and `annotations.csv` written to the configured output folder. |

## Supported input intent

The supported retinal input intent is JPEG, PNG, TIFF, and standards-conformant single-frame ophthalmic photography DICOM handled by the DICOM extras. Ophthalmic DICOM remains on the existing display and provenance path. MRI, OCT, PACS objects, non-fundus DICOM, unsupported SOP classes, multi-frame objects, and untested transfer syntaxes are not added to model support. A recognized non-fundus DICOM is reported as `Unsupported modality`; a codec, decode, or multi-frame problem keeps its specific technical status.

RETFound and PRISM-DR accept fundus CFP inputs only. Empty PRISM detections do not prove that no lesion is present. Human review remains authoritative.

## Review workstation quick start

Prerequisites: Python 3.11 or 3.12, Node.js/npm, and (for DICOM) the optional DICOM dependencies.

```powershell
git clone https://github.com/siriponsri/dr-support-screening-poc.git
cd dr-support-screening-poc
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test,dicom]"
npm ci
cd frontend
npm ci
npm run build
cd ..
START.cmd
```

Open `http://127.0.0.1:8000/app/`. `START.cmd` sets `APP_PROFILE=review` and `MODEL_RUNTIME=remote`; configure `REMOTE_MODEL_URL` and, when required, `REMOTE_MODEL_TOKEN` in the private process environment before starting. The workstation remains usable for admission, review state, and export while the Model API is unavailable, but inference is disabled until the connection is healthy.

## Hospital Model API

Use a Linux GPU host for the supported long-running deployment. The one-time setup is online because it installs dependencies, clones the pinned upstream sources, downloads the approved checkpoint assets, verifies hashes, and runs synthetic smoke inference:

```bash
git clone https://github.com/siriponsri/dr-support-screening-poc.git /opt/dr-support-screening-poc
cd /opt/dr-support-screening-poc
./scripts/model-server/setup.sh
```

`setup.sh` ends with `READY` only after RETFound and PRISM-DR assets pass revision/checkpoint verification and the smoke checks. The pinned source revisions and hashes are declared in `dr_support/providers/retfound.py`, `dr_support/providers/prism.py`, and `dr_support/providers/prism_assets.json`.

Normal startup is read-only and does not download assets:

```bash
cd /opt/dr-support-screening-poc
./scripts/model-server/start.sh
# in another shell
./scripts/model-server/healthcheck.sh
```

The start script verifies all local assets, requires CUDA by default, sets `WORKERS=1`, and starts on `0.0.0.0:7860`. Missing or modified assets fail closed. After setup, normal startup and inference do not require internet access. For systemd, use `sudo ./scripts/model-server/install-service.sh`, then `sudo systemctl start dr-support-model-api`.

## Deployment topology

The review workstation and Model API should be on a protected hospital LAN. Do not expose the Model API directly to the public internet. Put TLS/authentication and firewall policy at the hospital boundary; the optional bearer token is supplied through environment/secrets management and is never committed.

The included service unit uses `/opt/dr-support-screening-poc`, user `drsupport`, `/etc/dr-support/model-server.env`, and port `7860`. The review workstation uses local workspace storage and connects to that service with `REMOTE_MODEL_URL`.

## Offline-after-setup behavior

Once setup succeeds, the Model API uses only the verified local source checkouts and checkpoint files. Startup invokes `python -m dr_support.setup_models --model all --verify`; it never calls a download path. Offline acceptance covers `/health`, `/v1/models`, and local inference. CVAT Online is intentionally optional and excluded from the offline requirement.

## Documentation

Each topic has one source of truth. The other documents link to it instead of repeating it.

**Clinicians and the project team**

- [Clinician User Manual (PDF)](docs/CLINICIAN_USER_MANUAL.pdf): application procedures. Source: [docs/manual/](docs/manual/index.qmd).
- [Clinician Image Selection Guide (PDF)](docs/CLINICIAN_IMAGE_SELECTION_GUIDE.pdf) and the [same guide as HTML](docs/image-selection/IMAGE_SELECTION_GUIDE.html): one page on choosing images.
- [Team Image Sampling Requirements (PDF)](docs/IMAGE_SAMPLING_REQUIREMENTS.pdf): sampling strategy, coverage monitoring, and open owner decisions. Source: [docs/image-sampling-requirements/](docs/image-sampling-requirements/index.qmd). Requirement provenance: [REQUIREMENTS_TRACEABILITY.md](docs/image-sampling-requirements/REQUIREMENTS_TRACEABILITY.md).
- [Clinician workflow](docs/USER_WORKFLOW.md), [feature reference](docs/FEATURE_REFERENCE.md), and [dataset manifest](docs/DATASET_MANIFEST.md) (the export-schema source of truth).

**Hospital IT and operators**

- [Deployment and Operations Manual (PDF)](docs/DEPLOYMENT_OPERATIONS_MANUAL.pdf). Source: [docs/operator-manual/](docs/operator-manual/index.qmd).
- Setup and operations: [Installation](docs/INSTALLATION.md), [Deployment](docs/DEPLOYMENT.md), [Model Server](docs/MODEL_SERVER.md), [Operator Runbook](docs/OPERATOR_RUNBOOK.md), [Configuration](docs/CONFIGURATION.md).
- Safety and recovery: [Security and Privacy](docs/SECURITY_PRIVACY.md), [Backup and Restore](docs/BACKUP_RESTORE.md), [Troubleshooting](docs/TROUBLESHOOTING.md).
- Optional and future work: [CVAT Online setup](docs/CVAT_ONLINE_SETUP.md), [Future Experiments](docs/FUTURE_EXPERIMENTS.md), [Release Checklist](docs/RELEASE_CHECKLIST.md).

**Developers**

- [Developer Technical Guide (PDF)](docs/DEVELOPER_TECHNICAL_GUIDE.pdf): architecture and internals. Source: [docs/developer-manual/](docs/developer-manual/index.qmd).
- [Developer Handoff](docs/DEVELOPER_HANDOFF.md): transfer of ownership.
- [Feature Implementation Map](docs/technical/FEATURE_IMPLEMENTATION_MAP.md): which code implements each feature.
- [Where to Change What](docs/technical/WHERE_TO_CHANGE_WHAT.md): practical guide to making changes.
- [Architecture diagrams](docs/architecture/README.md): Mermaid sources, following the C4 model.
- [ADR log](docs/adr/README.md): recorded architecture decisions.
- [DESIGN.md](DESIGN.md): UI design source of truth.

**Presentations** (offline, presenter-controlled: Space / → next reveal, ← previous, Home / End, F full screen)

- [Product demo](docs/demo/RETINAL_REVIEW_DEMO.html). Open it with `PRESENT_DEMO.cmd`. Accompanied by the [Thai presentation script](docs/demo/PRESENTATION_SCRIPT_TH.md) and the [presentation source map](docs/demo/PRESENTATION_SOURCE_MAP.md).
- [Technical briefing](docs/demo/TECHNICAL_BRIEFING.html). Open it with `PRESENT_TECHNICAL.cmd`. Accompanied by the [Thai technical script](docs/demo/TECHNICAL_PRESENTATION_SCRIPT_TH.md).
- Neither launcher needs Administrator rights, npm, a GPU, model weights, or the Workbench server. Each simply opens a self-contained HTML file.

**Rebuilding the documentation**

Rebuild everything from the repository root with `python scripts/docs/build_docs.py all`, or name targets instead of `all`: `clinician-manual`, `operator-manual`, `sampling`, `developer`, `image-guide`, `demo`, `briefing`, `diagrams`. Then check the result with `python scripts/docs/check_docs.py`.

The builds need these tools:

- **Quarto with XeLaTeX**, for the PDF books. Set `QUARTO_BIN` if Quarto is not on `PATH`.
- **Playwright**, for the image-guide PDF.
- **mermaid-cli**, for the diagrams.

The demo and briefing builds need only Python. After every rebuild, open and inspect every PDF page and every presentation scene.

## Validation

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check dr_support tests
cd frontend
npm test
npm run typecheck
npm run build
cd ..
npm test
python scripts/docs/check_docs.py
```

The root `npm test` UI smoke expects the ten public HRF samples; fetch them once with `.venv\Scripts\python.exe -m dr_support.fetch_samples`.

## Privacy and safety

Use only synthetic/public fixtures in tests, screenshots, and examples. Do not commit PHI, secrets, CVAT credentials, model weights, runtime databases, or local-state artifacts. Original admitted images remain immutable; exported manifests use the existing pseudonymous and provenance-aware contracts. Do not treat model scores as calibrated clinical probabilities, and do not interpret an empty model result as absence of disease.

## License

See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for project and third-party terms. RETFound and PRISM-DR remain subject to their upstream research/non-commercial and dependency licenses; hospital deployment must obtain its own legal clearance.
