# Retinal Review Workbench

**Software version:** `0.7.0`

<p align="center">
  <img src="assets/dr-support-logo.svg" width="104" alt="Retinal Review Workbench logo">
</p>

Retinal Review Workbench is a clinician-controlled retinal screening review and dataset workspace. It supports retinal image admission, patient/eye context review, optional AI-assisted evidence, clinician confirmation, annotation review, provenance tracking, and dataset export.

It is a **public/synthetic research and clinical-support proof of concept**. It is not an autonomous diagnostic or referral system and is not presented as a regulated medical device.

![Hospital deployment architecture](assets/system-architecture.png)

---

## Clinician workflow

The application follows a clinician-led review path:

1. Select or create a local **Workspace**.
2. Scan the input folder and review cases in **Worklist**.
3. Confirm image context with **Confirm Image**.
4. Open **Review** and inspect the retinal image.
5. Optionally request model assistance:
   - **RETFound** for a DR grade suggestion.
   - **PRISM-DR** for lesion ROI suggestions.
6. Use **Clinician Review** to record the final DR grade.
7. Use **Edit Annotations** only when a human annotation or AI ROI correction/removal is needed.
8. Use **Confirm Annotation** when the active annotation set is ready.
9. Review **DR-ready** and **Lesion-ready** states in **Datasets** before export.

![Clinician workflow](assets/clinician-workflow.png)

The normal clinician UI is available at `/app/`. The legacy `/ui/` surface remains for compatibility with existing local integrations.

---

## Image selection boundary

Hospital-controlled source images remain under hospital control.

The intended workflow is:

```text
Hospital-controlled image storage
        ↓
Clinician / authorized hospital user selects a candidate image
        ↓
Hospital-approved staging / transfer
        ↓
Retinal Review Workbench Workspace
        ↓
Clinical review and labeling
```

The project team does **not** pre-select images from hospital storage.

The current source classification available to the project is:

```text
Refer
Not-refer
```

Dataset coverage across Refer/Not-refer, sex, and laterality is a **team monitoring responsibility**. Clinicians are not expected to manage sampling quotas during routine image selection.

See:

- [Clinician Image Selection Guide (PDF)](docs/pdfs/CLINICIAN_IMAGE_SELECTION_GUIDE.pdf)
- [Team Image Sampling Requirements (PDF)](docs/pdfs/IMAGE_SAMPLING_REQUIREMENTS.pdf)
- [Sampling requirements source](docs/image-sampling-requirements/index.qmd)
- [Sampling requirement traceability](docs/image-sampling-requirements/REQUIREMENTS_TRACEABILITY.md)

---

## Architecture

The review workstation and model runtime are intentionally separated.

| Component | Role |
| --- | --- |
| Review workstation | React/Vite clinician UI served by FastAPI at `/app/`; owns local review/workspace state. |
| Workspace storage | Input/output folders and local SQLite-backed review state. |
| Model API | Provider-neutral FastAPI service used by the review workstation. |
| RETFound | Five-class DR grade suggestion through `retfound-aptos5`. |
| PRISM-DR | Lesion ROI suggestions through `prism-dr-5fold`. |
| Dataset export | Provenance-preserving `manifest.json`, `images.csv`, and `annotations.csv`. |
| CVAT Online | Optional dense-annotation workflow; not required for normal offline review/export. |

The review workstation uses the `review` profile and does not load production model weights. The GPU host runs the `model_api` profile with verified local model assets.

Architecture sources and rendered diagrams are maintained under:

- [Architecture overview](docs/adr/architecture/README.md)
- [System Context](docs/adr/architecture/01-system-context.mmd)
- [Container view](docs/adr/architecture/02-container.mmd)
- [Image staging boundary](docs/adr/architecture/03-image-staging-boundary.mmd)
- [Image admission flow](docs/adr/architecture/04-image-admission-flow.mmd)
- [Remote inference flow](docs/adr/architecture/05-remote-inference-flow.mmd)
- [Dataset provenance flow](docs/adr/architecture/06-dataset-provenance-flow.mmd)
- [Deployment topology](docs/adr/architecture/07-deployment-topology.mmd)

---

## Supported input intent

The supported retinal input intent is:

- JPEG
- PNG
- TIFF
- supported single-frame ophthalmic photography DICOM

The current retinal-model path is intended for fundus/color retinal photography inputs.

Out of scope for current model support include MRI, OCT, PACS objects, non-fundus DICOM, unsupported SOP classes, multi-frame objects, and unsupported/untested transfer syntaxes.

A recognized non-fundus DICOM is reported as an unsupported modality. Codec, decode, or multi-frame problems retain their specific technical status.

RETFound and PRISM-DR outputs are **model evidence**:

- model scores are not presented as calibrated clinical probabilities;
- an empty PRISM result does not prove absence of lesions;
- clinician review remains authoritative.

---

## Review workstation quick start

### Prerequisites

- Python `>=3.11,<3.13`
- Node.js / npm
- Optional DICOM dependencies when DICOM support is required

### Setup

```powershell
git clone https://github.com/siriponsri/dr-support-screening-poc.git
cd dr-support-screening-poc

py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test,dicom]"

npm.cmd ci

cd frontend
npm.cmd ci
npm.cmd run build
cd ..
```

Start the workstation:

```powershell
.\START.cmd
```

Open:

```text
http://127.0.0.1:8000/app/
```

`START.cmd` configures the review workstation for remote model use. Set `REMOTE_MODEL_URL` and, when required, `REMOTE_MODEL_TOKEN` in the private runtime environment before starting.

If PowerShell blocks `npm.ps1`, use `npm.cmd` as shown above instead of changing machine-wide execution policy.

---

## Hospital Model API

The supported long-running model deployment is a Linux GPU host.

One-time setup:

```bash
git clone https://github.com/siriponsri/dr-support-screening-poc.git /opt/dr-support-screening-poc
cd /opt/dr-support-screening-poc
./scripts/model-server/setup.sh
```

Normal startup:

```bash
cd /opt/dr-support-screening-poc
./scripts/model-server/start.sh
```

Health check:

```bash
./scripts/model-server/healthcheck.sh
```

The model server is intended to:

- verify pinned local model assets before startup;
- require CUDA for the supported production-style runtime;
- run with one worker by default;
- avoid downloading assets during normal startup;
- operate without internet after successful setup.

The Model API should remain inside a protected hospital network boundary and should not be exposed directly to the public internet.

---

## Documentation

### Clinicians and project team

- [Clinician User Manual (PDF)](docs/pdfs/CLINICIAN_USER_MANUAL.pdf)
- [Clinician User Manual source](docs/manual/index.qmd)
- [Clinician Image Selection Guide (PDF)](docs/pdfs/CLINICIAN_IMAGE_SELECTION_GUIDE.pdf)
- [Team Image Sampling Requirements (PDF)](docs/pdfs/IMAGE_SAMPLING_REQUIREMENTS.pdf)
- [Sampling requirements source](docs/image-sampling-requirements/index.qmd)
- [Sampling requirement traceability](docs/image-sampling-requirements/REQUIREMENTS_TRACEABILITY.md)
- [Clinician workflow](docs/USER_WORKFLOW.md)
- [Feature reference](docs/FEATURE_REFERENCE.md)
- [Dataset manifest](docs/DATASET_MANIFEST.md)

### Hospital IT and operators

- [Deployment & Operations Manual (PDF)](docs/pdfs/DEPLOYMENT_OPERATIONS_MANUAL.pdf)
- [Deployment & Operations Manual source](docs/manual/operator-manual/index.qmd)
- [Installation](docs/INSTALLATION.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Model Server](docs/MODEL_SERVER.md)
- [Operator Runbook](docs/OPERATOR_RUNBOOK.md)
- [Configuration](docs/CONFIGURATION.md)
- [Security & Privacy](docs/SECURITY_PRIVACY.md)
- [Backup & Restore](docs/BACKUP_RESTORE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [CVAT Online setup](docs/CVAT_ONLINE_SETUP.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)

### Developers

- [Developer Technical Guide (PDF)](docs/pdfs/DEVELOPER_TECHNICAL_GUIDE.pdf)
- [Developer Technical Guide source](docs/manual/developer-manual/index.qmd)
- [Developer Handoff](docs/DEVELOPER_HANDOFF.md)
- [Feature Implementation Map](docs/technical/FEATURE_IMPLEMENTATION_MAP.md)
- [Where to Change What](docs/technical/WHERE_TO_CHANGE_WHAT.md)
- [Architecture diagrams](docs/adr/architecture/README.md)
- [ADR log](docs/adr/README.md)
- [Design system](DESIGN.md)

### Presentations

- [Product presentation](docs/presentation/RETINAL_REVIEW_DEMO.html)
- [Thai product-presentation script](docs/presentation/PRESENTATION_SCRIPT_TH.md)
- [Presentation source map](docs/presentation/PRESENTATION_SOURCE_MAP.md)
- [Technical briefing](docs/presentation/TECHNICAL_BRIEFING.html)
- [Thai technical-presentation script](docs/presentation/TECHNICAL_PRESENTATION_SCRIPT_TH.md)

Presentation source files and assets are maintained under:

```text
docs/presentation/src/
docs/presentation/assets/
```

---

## Repository structure

```text
assets/                         project-level diagrams and branding
deployment/                     model-server service configuration
docs/
├─ adr/                         architecture decisions + architecture sources
├─ image-sampling-requirements/ team sampling specification sources
├─ manual/                      clinician manual + nested operator/developer manuals
├─ pdfs/                        published PDF artifacts
├─ presentation/                product + technical HTML presentations
└─ technical/                   feature/code handoff references

dr_support/                     Python/FastAPI backend and model-provider layer
frontend/                       React/Vite clinician UI
scripts/                        docs and model-server tooling
tests/                          backend/API/root smoke tests
web/                            legacy compatibility UI
```

Runtime state such as local databases, workspaces, model weights, and other local-state artifacts must not be treated as source code.

---

## Validation

Backend:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check dr_support tests
```

Frontend:

```powershell
cd frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
cd ..
```

Root smoke tests:

```powershell
npm.cmd test
```

Git whitespace/error check:

```powershell
git diff --check
```

---

## Privacy and safety

Use only approved synthetic/public fixtures in tests, screenshots, examples, and public documentation.

Do not commit:

- PHI;
- secrets or API tokens;
- CVAT credentials;
- model weights;
- runtime SQLite databases;
- local workspace state;
- local-state artifacts.

Original admitted images remain immutable within the intended provenance model. Source and derived analysis identities remain distinct, and exported data preserves the current pseudonymous/provenance-aware contracts.

---

## License

See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

RETFound, PRISM-DR, and their dependencies remain subject to their respective upstream licenses and usage terms. Deployment in a hospital environment requires the organization's own legal, security, privacy, and governance review.
