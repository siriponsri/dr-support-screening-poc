# Release builders

Build both packages from a checkout with a prebuilt `frontend/dist`:

```powershell
python scripts/release/build_release.py --version 0.7.0-r1
```

Outputs are written under ignored `local-state/release/artifacts/`:

- `DR-Screening-Workstation-<version>.zip`
- `DR-Model-API-<version>.zip`
- `SHA256SUMS.txt`

The builder uses explicit allowlists and fails if a selected path contains
weights, private environment files, databases, logs, dependency trees, or
runtime state. The Model API package contains software and contracts only;
`scripts/release/model_artifacts.json` records the expected USPEC identity and
does not acquire the artifact. Its `model-api-check.sh`, `model-api-verify.sh`,
`model-api-start.sh`, and `model-api-health.sh` helpers remain identity-only, disabled, and
`NOT_RUN` until P3.1 host qualification is separately authorized.
