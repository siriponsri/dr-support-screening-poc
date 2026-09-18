# CVAT Online

Host: https://app.cvat.ai
Project: https://app.cvat.ai/projects/445923?page=1&pageSize=10
Project ID: 445923. These values are deliberately restricted in the connector.

Required label names (IDs resolved by API, never hard-coded):
MICROANEURYSM, HEMORRHAGE, HARD_EXUDATE, SOFT_EXUDATE. Labels may remain `type:any`.

Round-trip import currently supports rectangle, ellipse, polygon, polyline, and points. Mask geometry is **not supported in v0.1.2**; the connector fails explicitly instead of silently discarding mask data. Use one of the supported geometry tools for the live acceptance pass.

Provide a read/write personal access token to the developer server through its secure runtime
secret/environment configuration, under `CVAT_TOKEN`. Do not paste it in chat, source, Git,
command arguments, browser JavaScript, screenshots, or documentation. The application reads
only the environment; no credential-entry endpoint exists.

PAT authentication uses `Authorization: Bearer ...`, as documented at
https://docs.cvat.ai/docs/api_sdk/access_tokens/ . Legacy `Token` auth is not used.
Redirects are rejected to prevent forwarding a secret to another origin. Errors omit response
bodies and credentials. The application does not modify users, project labels, or tokens.

Runtime acceptance:
1. Run a lesion prediction on one admitted image.
2. Prepare CVAT task. Authentication and the four project labels are inspected before writes. The bounded clinician pre-label subset is pushed; raw PRISM output stays in local case provenance.
3. If CVAT is processing the upload, retry after the task is ready. Do not recreate it.
4. Open the returned task/job URL, review and save a correction, and sync back.
5. Confirm only after inspecting the imported annotations.

A deterministic task name binds image hash and prediction hash. Successful repeat syncs do
not duplicate boxes. Existing annotations are preserved. An ambiguous write outcome stops
that live operation for manual reconciliation; it never blindly repeats a possibly successful
write. Do not run two independent Bridge servers against the same task/state store.

Current delivery: live auth/create/upload/push/pull NOT_EXECUTED (CVAT_TOKEN absent).
Offline connector and round-trip fixtures passed. No fake live task URL is reported.
Missing token affects only live operations; the UI, providers, and offline tests remain usable.
