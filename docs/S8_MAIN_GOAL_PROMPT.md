# S8 Main Goal Prompt — Draft

Use after S6.1 is accepted and the S7 docs-only file is committed.

```text
/goal S8 — PRODUCTION & DEPLOYMENT HARDENING

Work on clean synchronized main unless owner explicitly changes this.
Do not create branch/worktree sprawl.

Read first:
- S8_MASTER_SPEC.md
- S8_READ_REWRITE_MAP.md
- FUTURE_EXPERIMENTS.md
- README_DRAFT.md
- all draft docs in the S8 package
- current README, pyproject, env/settings, startup scripts, model setup/runtime code, tests, frontend package scripts

These package files are DRAFTS. READ AND RE-WRITE them against the final repository; do not blindly copy commands or claims.

Primary goals:
1. audit the repository and delete dead/stale files;
2. delete obsolete docs rather than archiving them;
3. rewrite a concise professional README using the supplied logo/diagram assets;
4. create one-time online model-server setup with revision/hash verification;
5. create normal offline-ready model-server start + healthcheck;
6. add optional systemd deployment for hospital Linux GPU server;
7. preserve/simple clinician workstation startup;
8. document configuration, privacy, backup/restore and troubleshooting;
9. create Playwright-based clinician-manual screenshot automation and generate the final PDF;
10. prove clean-clone install, restart/reboot, offline model inference and end-to-end review/export.

Do not add new models, XAI, calibration, PACS/DICOMweb, scientific claims, or unrelated UI features.
Preserve S1–S6 frozen clinical/data/provenance semantics.

Repository cleanup rule:
- inventory KEEP/REWRITE/DELETE/UNKNOWN first;
- resolve UNKNOWN before deletion;
- move no old docs into archive;
- extract still-valid facts into final docs, then delete superseded files;
- remove dead code only after reference/import/test audit.

Model server target:
initial online setup → download/verify approved RETFound + PRISM assets → smoke → READY;
normal startup → local verified assets only → no silent download → healthcheck.

Manual target:
Playwright captures deterministic public/synthetic workflow screenshots from the final release and produces CLINICIAN_USER_MANUAL.pdf.

Run full backend/Ruff/frontend/typecheck/build/smoke/diff validation throughout.
Do final acceptance from a clean clone or clean machine/VM where practical.

Before finishing:
- no draft/stale docs remain;
- final README links/commands work;
- final docs match implementation;
- manual screenshots/PDF regenerated;
- online setup then offline restart/inference verified;
- main clean + origin synchronized.

Return final SHA, deleted/rewritten file inventory, final tree, setup/start commands, model verification results, clean-clone/offline/reboot acceptance, docs/manual outputs, validation, and remaining limitations.
Do not claim production clinical validation or regulatory approval.
```
