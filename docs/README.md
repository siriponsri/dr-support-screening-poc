# Documentation Portal

Use this page to choose the document for your role. Authoring sources and published artifacts are kept separate: Quarto and Markdown sources are canonical, while PDFs under `docs/pdfs/` are generated copies.

## For Clinicians

- [Clinician User Manual source](manuals/clinician/index.qmd) and [published PDF](pdfs/CLINICIAN_USER_MANUAL.pdf): review cases, confirm context and grade, correct annotations, and export datasets.
- [Clinician workflow](clinician/USER_WORKFLOW.md): a short current-state workflow reference.
- [Feature reference](clinician/FEATURE_REFERENCE.md): clinician-facing capability and state reference.
- [Image Selection Guide source](clinician/IMAGE_SELECTION_GUIDE.html) and [published PDF](pdfs/CLINICIAN_IMAGE_SELECTION_GUIDE.pdf): what to select and how sampling responsibility is divided.
- [Team Image Sampling Requirements source](clinician/sampling/index.qmd), [traceability register](clinician/sampling/REQUIREMENTS_TRACEABILITY.md), and [published PDF](pdfs/IMAGE_SAMPLING_REQUIREMENTS.pdf): planning and monitoring requirements for the project team.

## For Hospital IT and Operators

- [Deployment and Operations Manual source](manuals/operator/index.qmd) and [published PDF](pdfs/DEPLOYMENT_OPERATIONS_MANUAL.pdf): installation, routine operations, the Linux GPU Model API, security, and recovery.
- [Windows installation](operations/INSTALLATION.md): the supported `SETUP.cmd` -> `START.cmd` workstation path.
- [Configuration](operations/CONFIGURATION.md), [deployment](operations/DEPLOYMENT.md), [Model API](operations/MODEL_SERVER.md), and [operator runbook](operations/OPERATOR_RUNBOOK.md): operational details and environment separation.
- [Troubleshooting](operations/TROUBLESHOOTING.md), [backup and restore](operations/BACKUP_RESTORE.md), [security and privacy](operations/SECURITY_PRIVACY.md), and [CVAT Online](operations/CVAT_ONLINE_SETUP.md): recovery and optional integrations.

## For Developers

- [Developer Technical Guide source](manuals/developer/index.qmd) and [published PDF](pdfs/DEVELOPER_TECHNICAL_GUIDE.pdf): architecture, runtime, contracts, tests, and deployment boundaries.
- [Developer handoff](developer/DEVELOPER_HANDOFF.md): project status and ownership context.
- [Feature implementation map](developer/FEATURE_IMPLEMENTATION_MAP.md) and [where to change what](developer/WHERE_TO_CHANGE_WHAT.md): change ownership and compatibility checks.
- [Design system](../DESIGN.md): visual and interaction source of truth.

## Reference

- [Dataset manifest](reference/DATASET_MANIFEST.md): export schema and readiness rules.
- [Dataset manifest example](reference/DATASET_MANIFEST_V2_EXAMPLE.json) and [sample source manifest](reference/SAMPLE_SOURCE_MANIFEST.json): machine-readable examples.
- [Third-party notices](../THIRD_PARTY_NOTICES.md): licenses and source attribution.

## Architecture Decisions

- [ADR index](adr/README.md): accepted decisions and rationale.
- [Architecture sources and rendered diagrams](adr/architecture/README.md): Mermaid sources are canonical; rendered PNG/SVG files are generated beside them.

## Presentations

- [Product presentation](presentation/RETINAL_REVIEW_DEMO.html), [Thai script](presentation/PRESENTATION_SCRIPT_TH.md), and [source map](presentation/PRESENTATION_SOURCE_MAP.md): the clinician/product narrative.
- [Technical briefing](presentation/TECHNICAL_BRIEFING.html) and [Thai script](presentation/TECHNICAL_PRESENTATION_SCRIPT_TH.md): architecture and implementation briefing.
- The live HyperFrames source is [presentation/hyperframes/index.html](presentation/hyperframes/index.html); `npx hyperframes present docs/presentation/hyperframes` opens presenter mode. `PRESENT_DEMO.cmd` and `PRESENT_TECHNICAL.cmd` open the offline builds.

## Published PDFs

All tracked PDFs live only in [docs/pdfs](pdfs). Rebuild them with `python scripts/docs/build_docs.py ...`; never edit a PDF directly and never add a second copy at the repository root.

## Documentation QA

Run `python scripts/docs/check_docs.py` from the repository root. It checks canonical paths, local links, requirements IDs, generated presentation integrity, offline assets, PDF locations, and the absence of temporary task specifications.
