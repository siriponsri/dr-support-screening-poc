# Operator Runbook — Draft for S8 Rewrite

Keep this operational, not architectural.

## Daily checks
1. Model API service is active.
2. `/health` returns ready.
3. `/v1/models` reports expected RETFound and PRISM assets.
4. Review application can reach Model API.
5. Workspace/export storage has sufficient free space.

## Start / stop / restart

S8 must insert exact commands for the validated deployment method (systemd or approved equivalent).

## Logs

Document:
- application log location;
- model-server/service logs;
- rotation/retention expectation;
- fields that must never contain secrets or PHI.

## Common incidents

- Model API unavailable → review remains usable; inference disabled.
- Weight missing/hash mismatch → fail closed; rerun approved setup.
- CUDA/device unavailable → clear readiness failure; no silent CPU fallback unless explicitly supported.
- DICOM codec missing → explicit codec-required state.
- Storage unavailable → block writes/exports with actionable error.

## Escalation bundle

Provide version, commit SHA, service status, health response, sanitized logs, and failing case ID/hash — never raw patient identifiers or secrets.
