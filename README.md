# Retinal Review Workbench

Retinal Review Workbench is a clinician-controlled retinal screening review and dataset workspace for public/synthetic research and clinical-support use. It is not an autonomous diagnostic or regulated medical device.

Windows workstation: run `SETUP.cmd` once, then `START.cmd` each day. The browser opens at `http://127.0.0.1:8000/app/`; `OPEN_APP.cmd` reopens or starts it and `STOP.cmd` stops only the repository-managed process. Setup and deployment details are in the [documentation portal](docs/README.md).

The review workstation and controlled Linux GPU Model API are separate roles. The workstation does not require model weights or a GPU. Use the [Model API operations guide](docs/operations/MODEL_SERVER.md) for the Linux service.

The normal clinician path is one line per image: Worklist -> Confirm Image -> Review -> Clinician Review -> Confirm DR Grade -> Annotation Editor (optional ROI corrections) -> Confirm Annotation -> next Worklist image. Datasets shows DR-ready and Lesion-ready separately. Model evidence is optional; human review remains authoritative and original admitted images remain immutable.

Use only approved synthetic/public fixtures in tests, screenshots, examples, and public documentation. Do not commit PHI, secrets, credentials, model weights, runtime databases, or `local-state/` artifacts. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).
