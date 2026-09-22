<p align="center">
  <img src="assets/dr-support-logo.svg" width="104" alt="DR Support logo" />
</p>

# DR Support Screening POC

**AI-assisted retinal image review and dataset preparation with clinician control.**

DR Support Screening POC combines a clinician-focused review workspace with provider-neutral model inference, retinal lesion overlays, provenance-aware dataset export, and optional dense annotation through CVAT. It is designed for public/synthetic development and controlled clinical-support workflows; it is **not an autonomous diagnostic or referral system**.

> **S8 draft:** Luna/Max must rewrite commands, versions, and deployment claims against the final release before replacing the repository README.

<p align="center">
  <img src="assets/system-architecture.png" width="100%" alt="Hospital deployment architecture" />
</p>

## What it does

- **Worklist:** admit retinal images, resolve patient/eye identity, and track review state.
- **Review:** inspect the retinal image, optional RETFound DR grade suggestion, and PRISM-DR lesion ROIs with detection confidence.
- **Dataset:** preserve source identity, annotation provenance, review status, and export manifests.
- **Models & Audit:** show model readiness, revision/hash provenance, inference lineage, and technical limitations.
- **Optional CVAT round-trip:** use dense geometry editing only when needed rather than making every AI detection a clinician task.

## Supported imaging intent

The release should document only formats proven by final tests. Current S8 target includes raster inputs such as JPEG/PNG/TIFF plus supported single-frame ophthalmic DICOM through the S5/S6 imaging pipeline. Non-ophthalmic or unsupported DICOM must fail explicitly rather than being treated as valid fundus input.

## Deployment model

```text
Clinician workstation / browser
        ↓
Review application (APP_PROFILE=review)
        ↓ provider-neutral HTTP API
Hospital GPU model server (APP_PROFILE=model_api)
        ↓
Verified local RETFound + PRISM assets
```

Initial model-server setup may use internet access to download and verify approved assets. Normal operation should run from local verified weights without silently re-downloading models.

## Quick start

### Clinician workstation

Use the final validated workstation launcher. On Windows this may remain:

```powershell
START.cmd
```

S8 must verify the authoritative command before release.

### Model server

Target operator experience:

```bash
./scripts/model-server/setup.sh       # one-time online setup
./scripts/model-server/start.sh       # normal startup
./scripts/model-server/healthcheck.sh # readiness check
```

These commands are targets for S8 and must be rewritten if the final implementation differs.

## Clinical workflow

<p align="center">
  <img src="assets/clinician-workflow.png" width="100%" alt="Clinician review workflow" />
</p>

AI output is assistance. Clinicians remain responsible for review decisions. A PRISM detection confidence score is a model score, not automatically a calibrated probability or disease probability.

## Documentation

Final S8 documentation should remain deliberately small:
- Installation
- Deployment
- Model Server
- Operator Runbook
- Configuration
- Security & Privacy
- Backup & Restore
- Troubleshooting
- Clinician User Manual (MD + generated PDF)
- Future Experiments
- Release Checklist

Superseded milestone/specification docs should be deleted, not archived.

## Models

The current product architecture supports:
- **RETFound** for DR grade suggestion through the configured provider adapter;
- **PRISM-DR** for lesion detections / pre-labels;
- provider-neutral remote inference from the clinician review application.

Final README must link to the verified model-source/provenance information retained by S8 and must not claim calibration, clinical validation, or regulatory approval that has not been established.

## Development

Expected validation surfaces include:

```bash
python -m pytest -q
python -m ruff check dr_support tests
cd frontend && npm test && npm run typecheck && npm run build
```

Use the final repository commands after S8 cleanup.

## Privacy and safety

- No secrets or model tokens in source control.
- Do not send raw DICOM headers/PHI to the remote Model API.
- Public/synthetic fixtures only in documentation and automated screenshots.
- Original source identity and derivative lineage remain auditable.
- Human review remains authoritative.

## License

See `LICENSE`. S8 must preserve the repository's actual legal terms and must not invent a new license.
