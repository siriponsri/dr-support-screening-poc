# Documentation

Older documents (manuals, milestone receipts, plans, presentations) were removed on 1 November 2026. They stay
recoverable from the Git tag `archive/docs-before-cut-20261101`.

## Guides in Thai (PDF)

| Guide | For | File |
| --- | --- | --- |
| Deployment guide | hospital IT and the operator | [`docs/pdfs/DEPLOYMENT_GUIDE_TH.pdf`](pdfs/DEPLOYMENT_GUIDE_TH.pdf) |
| Test report | the owner and reviewers | [`docs/pdfs/TEST_REPORT_TH.pdf`](pdfs/TEST_REPORT_TH.pdf) |
| User manual, step by step with screenshots | physicians and nurses, no code | [`docs/pdfs/USER_MANUAL_TH.pdf`](pdfs/USER_MANUAL_TH.pdf) |

The Thai sources are in `docs/th/` (`user-manual.md`, `deployment-guide.md`, `test-report.md`, screenshots in
`docs/th/images/`, the Anuphan font with its OFL licence in `docs/th/assets/`). After editing a source, rebuild
the PDFs (needs Microsoft Edge and Playwright, both in the test setup):

```powershell
.\.venv\Scripts\python.exe scripts\docs\build_pdfs.py               # all three, or name one: user-manual
.\.venv\Scripts\python.exe scripts\docs\capture_thai_manual.py --demo-root C:\DRDemo   # retake the screenshots
```

The screenshot script starts its own throwaway app with sign-in, the ten public samples and the synthetic
fixture (mock AI, demo data only), so it needs an empty demo folder and a built `frontend/dist`.

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
