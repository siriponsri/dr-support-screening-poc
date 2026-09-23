# Backup and Restore

## What to back up

Back up the active Workspace's SQLite review database, the configured output folder containing dataset exports, and the hospital-controlled source image storage. Preserve the folder relationship used by the Workspace profile. The catalog database path is configured by `DR_SUPPORT_WORKSPACE_CATALOG` or the local default.

Keep a separate controlled backup of the verified Model API asset directory and its configuration record. Do not place model weights or secrets in Git.

## What is reproducible

The frontend bundle can be rebuilt with `cd frontend && npm ci && npm run build`. Python dependencies can be installed from `pyproject.toml` and the lockfile-backed environment. Model assets can be reacquired through the approved online setup and must pass the pinned revision and hash checks before use. CVAT tasks are external and require the hospital's own retention policy.

## Backup procedure

Stop writes to the review workstation, then copy the SQLite database and output directory with a filesystem snapshot or an equivalent file-consistent backup. Record the release commit SHA, active workspace configuration, and model asset hashes. Keep source images in their original hospital-controlled location; a database backup alone does not contain all source bytes.

## Restore procedure

1. Install the same release commit and dependencies.
2. Restore the SQLite database, catalog, source image folders, and output folder to approved paths.
3. Open or recreate the Workspace profile with those paths; profile deletion never deletes the source or review files.
4. Run the backend and scan the input folder.
5. Verify case count, patient/eye context, review history, source hashes, and exported manifest contents.
6. On a Model API host, run `python -m dr_support.setup_models --model all --verify` before accepting inference traffic.

## Restore validation

Open one synthetic/public case in Worklist and Review, confirm the original image displays, inspect Models & Audit provenance, and perform a test export to a separate output folder. Never use PHI for a restore demonstration unless the hospital has approved it.
