# Regular service: security actions waiting for the owner (2026-10-31)

Status: request only. Nothing here is created, opened or approved. The
regular service runs today with the existing backend principal and the owner's
own SSH route, which is enough for single-machine testing but not for live
acceptance with 3 to 5 separate users.

## 1. Per-user principals (needed for live multiuser acceptance)

Today every app context shares one backend token, so the workstation ID that
drives fairness and attribution is a label, not an identity.

Proposed least-privilege change:

- One random token per user, generated on dr-train by the operator and handed
  to that user's app only (never in Git, chat, logs or the browser).
- dr-train keeps only `token_sha256 -> principal_id, allowed workstation IDs,
  scopes` in a private operator file (mode 0600). The gateway checks the token,
  then the workstation ID against that principal.
- Scopes: submit/cancel/status for own tickets, the two charged routes. No
  operator actions (reconcile, revoke) for users.
- Rollback: remove the user's row; the old shared token keeps working for the
  owner only until it is retired.

## 2. A route for other workstations

The SSH key is never distributed. Options:

| Option | What changes | Risk |
| --- | --- | --- |
| A. All apps on the owner's workstation (current) | Nothing | Not separate machines; fine for testing only |
| B. Gateway on the dr-train private network address with TLS and per-user tokens | Listener on a non-loopback address, certificate, host firewall allowing only named user devices | New network exposure; needs IT agreement |
| C. Each user gets their own restricted SSH account that can only forward to 127.0.0.1:7860 | New Linux accounts and `authorized_keys` forced-command rules | More accounts to manage |

Recommendation: B together with section 1, after IT agrees, because it keeps
one audited entry point and no shell access.

## 3. Owner's packet documents in Git

The packet (`docs/long-runs/20261031-local-app-real-api/`) and audit
(`docs/audit/20261031-local-web-real-api/`) are the owner's untracked files. A
branch with byte-identical copies exists (`docs/regular-service-packet`), but
merging it would require moving the owner's working files aside first, so it
was not merged. The owner decides whether these should be tracked.
