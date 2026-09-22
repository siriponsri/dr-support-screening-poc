# Security & Privacy — Draft for S8 Rewrite

## Required release posture

- Human review remains authoritative.
- No autonomous diagnosis/referral claim.
- Secrets are environment-managed and excluded from Git/logs/screenshots.
- Raw DICOM header/PHI is not sent to the Model API.
- DICOM public metadata uses the established safe allowlist.
- Documentation/manual automation uses public or synthetic data only.
- Source SHA and derivative/analysis SHA remain distinct and auditable.
- Model/checkpoint provenance remains pinned and verifiable.

## Hospital deployment

Document network boundaries, bind addresses, TLS/reverse-proxy expectations if used, filesystem permissions, backup access, and log access. Do not present a public-internet deployment as the default.

## Incident handling

If PHI or a secret appears in logs, screenshots, exports, or committed files, treat it as a release blocker and rotate/remove according to local hospital policy.
