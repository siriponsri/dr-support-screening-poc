# S8 Read-and-Rewrite Map

This package is a **drafting accelerator, not a blind copy set**. Luna/Max should read every relevant draft, inspect the final repository, and rewrite commands/paths/status to match reality.

## Source of truth order

1. final repository implementation and tests;
2. frozen S1–S6 semantics;
3. `S8_MASTER_SPEC.md` owner intent;
4. these draft docs/templates;
5. old repository documentation only for facts that remain true.

If old docs conflict with current code, current validated code wins unless the conflict is a safety/frozen-semantic regression.

## Rewrite table

| Package draft | Intended final path | Action |
|---|---|---|
| `README_DRAFT.md` | `README.md` | Rewrite against final commands/version |
| `docs/INSTALLATION_DRAFT.md` | `docs/INSTALLATION.md` | Verify prerequisites and exact commands |
| `docs/DEPLOYMENT_DRAFT.md` | `docs/DEPLOYMENT.md` | Rewrite topology, paths, ports |
| `docs/MODEL_SERVER_DRAFT.md` | `docs/MODEL_SERVER.md` | Verify setup/start/healthcheck and assets |
| `docs/OPERATOR_RUNBOOK_DRAFT.md` | `docs/OPERATOR_RUNBOOK.md` | Rewrite operational commands |
| `docs/CONFIGURATION_DRAFT.md` | `docs/CONFIGURATION.md` | Generate from real env/settings |
| `docs/SECURITY_PRIVACY_DRAFT.md` | `docs/SECURITY_PRIVACY.md` | Verify actual logging/PHI behavior |
| `docs/BACKUP_RESTORE_DRAFT.md` | `docs/BACKUP_RESTORE.md` | Verify actual state paths |
| `docs/TROUBLESHOOTING_DRAFT.md` | `docs/TROUBLESHOOTING.md` | Keep only reproducible issues |
| `docs/CLINICIAN_USER_MANUAL_DRAFT.md` | final MD/PDF | Replace placeholders with Playwright screenshots |
| `docs/RELEASE_CHECKLIST.md` | same | Execute, do not merely copy |
| `FUTURE_EXPERIMENTS.md` | `docs/FUTURE_EXPERIMENTS.md` | Keep docs-only backlog |

## Delete policy

After final docs are written and links verified, delete superseded docs. **Do not move them to an archive.** Git history is the historical record.

Do not leave `_DRAFT` files in the final release tree.
