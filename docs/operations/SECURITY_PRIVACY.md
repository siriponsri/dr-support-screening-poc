# Security and Privacy

Retinal Review Workbench is a public/synthetic research and clinical-support proof of concept. Human review remains authoritative. The product does not claim autonomous diagnosis, autonomous referral, regulatory approval, clinical validation, or calibrated probability output.

## Data boundaries

- Keep source images and SQLite state on hospital-controlled storage.
- Original admitted images are immutable; the application stores source references, hashes, and derived analysis lineage.
- The review workstation sends image bytes and contract identifiers to the configured Model API only when inference is requested. Local filesystem paths, patient resolver fields, OCR fields, and raw DICOM headers are not sent as model payload fields.
- DICOM ingestion exposes only the established safe technical metadata allowlist to the application. Do not copy private headers into notes, screenshots, or exports.
- Models accept fundus CFP inputs. MRI, OCT, PACS, DICOMweb, and unsupported modalities are outside scope.

## Secrets

Keep `REMOTE_MODEL_TOKEN`, `CVAT_TOKEN`, and any reverse-proxy credentials in an approved secret manager or private service environment. Do not store them in React, localStorage, sessionStorage, SQLite, logs, screenshots, or committed `.env` files. Rotate a credential immediately if it appears in a log or artifact.

## Network

Bind the review workstation to localhost unless a controlled workstation network requires otherwise. Keep the Model API on a protected hospital LAN or behind an approved TLS/authentication boundary. Do not expose port `7860` directly to the public internet.

## Model provenance

Model source revisions, checkpoint hashes, image SHA-256, analysis SHA-256, inference metadata, and annotation provenance are displayed read-only in Models & Audit where available. These facts establish lineage, not model accuracy. RETFound and PRISM-DR licensing and research-use limits remain in `THIRD_PARTY_NOTICES.md`.

## Incident response

If PHI or a secret is committed, logged, exported, or captured, stop distribution, preserve the incident details according to local policy, rotate the secret, and remove the affected artifact from release outputs. Do not rewrite Git history as a substitute for credential rotation.
