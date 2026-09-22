# Backup & Restore — Draft for S8 Rewrite

S8 must inspect the real persistence layout before finalizing this file.

Document separately:
- application state/database;
- workspace source references (do not imply originals are copied if they are not);
- clinician review state;
- exported datasets;
- model assets/cache;
- configuration/secrets (handled through approved secret backup, not Git).

Provide:
1. what must be backed up;
2. what can be regenerated/downloaded;
3. backup command/process;
4. restore command/process;
5. validation after restore;
6. tested failure/rollback procedure.

A restore test is part of release acceptance.
