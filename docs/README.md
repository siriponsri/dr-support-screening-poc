# Documentation

Older documents (manuals, milestone receipts, plans, presentations) were removed on 1 November 2026. They stay
recoverable from the Git tag `archive/docs-before-cut-20261101`.

## Guides in Thai (PDF)

| Guide | For | File |
| --- | --- | --- |
| Deployment guide | hospital IT and the operator | `docs/pdfs/DEPLOYMENT_GUIDE_TH.pdf` (coming in the next step) |
| Test report | the owner and reviewers | `docs/pdfs/TEST_REPORT_TH.pdf` (coming in the next step) |
| User manual, step by step with screenshots | physicians and nurses, no code | `docs/pdfs/USER_MANUAL_TH.pdf` (coming in the next step) |

## For developers

- [Architecture](ARCHITECTURE.md): system map, case flow, roles, data model, safety rules. Start here.
- [Configuration](developer/CONFIGURATION.md): environment variables and runtime profiles.
- [dr-train access](developer/DR_TRAIN_ACCESS.md): working with or without the team GPU server, personal tokens.
- [Model server operations](developer/MODEL_SERVER_OPERATIONS.md): regular gateway, Model API, PRISM receipts.
- [Security and privacy](developer/SECURITY.md): rules and the 31 October 2026 audit.
- [Dataset manifest](developer/DATASET_MANIFEST.md): the export contract.
- [Backup and restore](developer/BACKUP_RESTORE.md): recovery contract and procedures.
- Deployment packages: [web app](../deployment/webapp/README.md), [hospital server](../deployment/hospital-server/README.md).
- Repository rules: [AGENTS.md](../AGENTS.md), [CLAUDE.md](../CLAUDE.md), [DESIGN.md](../DESIGN.md).
- Current state: [HANDOFF.md](../HANDOFF.md) (English) and [GOAL.md](../GOAL.md) (Thai).
