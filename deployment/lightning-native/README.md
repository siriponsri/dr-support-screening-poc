# Lightning native private demo

This runbook preserves the verified native services; it does not start or stop
processes automatically and never uses broad `pkill`, `killall`, or destructive
Docker cleanup.

## Existing service map

| Service | Loopback endpoint | Role |
|---|---:|---|
| PostgreSQL | `127.0.0.1:54329` | Review persistence |
| Combined USPEC + PRISM API | `127.0.0.1:7865` | UWF grade and PRISM lesion assistance |
| RETFound API | `127.0.0.1:7866` | CFP global grade / lesion bridge as configured |
| UWF Review | `127.0.0.1:8767` | UWF Review API/UI |
| CFP Review | `127.0.0.1:8768` | CFP Review API/UI |

These ports are from the prior Lightning checkpoint and must be rechecked with
`ss -ltnp` or the operator's process inventory before use. Do not stop a PID
unless it is owned by the current run and recorded in the run receipt.

## Host-local checks

```bash
curl --fail http://127.0.0.1:7865/health
curl --fail http://127.0.0.1:7865/v1/models
curl --fail http://127.0.0.1:7866/health
curl --fail http://127.0.0.1:8767/app/
curl --fail http://127.0.0.1:8768/app/
```

Use the existing private token environment for authenticated model endpoints.
Reuse the approved evidence for real hospital UWF/CFP inference, same-eye
longitudinal comparison, PostgreSQL save/reload/restart, and fail-closed
hospital export. Do not rerun model qualification merely for this handoff.

## Windows private access

From an authorized Windows workstation, create a private SSH forwarding session
with the host operator's account (credentials remain outside Git):

```powershell
ssh -N `
  -L 8767:127.0.0.1:8767 `
  -L 8768:127.0.0.1:8768 `
  -L 7865:127.0.0.1:7865 `
  -L 7866:127.0.0.1:7866 `
  user@lightning-host
```

Open `http://127.0.0.1:8767/app/` for UWF and
`http://127.0.0.1:8768/app/` for CFP. Windows connectivity and Tailscale are
`NOT_RUN` in this environment; SSH forwarding must be performed only by an
authorized operator over the private host boundary.

## Safe restart

Record the service owner and PID/container identity. Restart only the run-owned
service using the established native launcher/systemd unit, then repeat the
health, model metadata, review UI, persistence and export-denial checks. Keep
PostgreSQL data and external model assets. Never delete runtime state to make a
restart pass.

Read-only helper scripts are available:

```bash
./deployment/lightning-native/status.sh
REMOTE_MODEL_TOKEN="$PRIVATE_MODEL_TOKEN" ./deployment/lightning-native/health.sh
```

The health helper accepts the token only from the process environment for model
metadata requests; it never writes or prints it.

## Unified clinician Review (authorized private hospital demo)

The supported Lightning M1 clinician entrypoint is one loopback Review service
that admits both explicitly bound hospital roots into one PostgreSQL-backed
queue. It does not replace the qualified modality-specific services.

| Service | Loopback endpoint | Role |
|---|---:|---|
| Unified Review | `http://127.0.0.1:8769/app/` | One authenticated-private browser entrypoint for UWF + CFP |
| Unified model gateway | `127.0.0.1:8881` | Internal only; routes UWF → USPEC, CFP → RETFound, lesions → PRISM |
| Existing UWF Review fallback | `http://127.0.0.1:8767/app/` | Preserved fallback |
| Existing CFP Review fallback | `http://127.0.0.1:8768/app/` | Preserved fallback |

The unified launcher is deliberately run-owned and refuses occupied ports or
unrelated PIDs:

```bash
./deployment/lightning-native/unified.sh start
./deployment/lightning-native/unified.sh status
./deployment/lightning-native/unified.sh smoke
./deployment/lightning-native/unified.sh stop
```

Before `start`, inject the private environment supplied by the authorized
operator. `DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS` is a server-only JSON object
whose values are exact absolute private directories, for example
`{"UWF":"/private/approved-uwf","CFP":"/private/approved-cfp"}`. Also set
`DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL=1`,
`DR_SUPPORT_HOSPITAL_SCOPE=PRIVATE_PROJECT_EVALUATION`,
`MODEL_HOSPITAL_SCOPE=PRIVATE_PROJECT_EVALUATION`,
`MODEL_ALLOW_AUTHORIZED_HOSPITAL=1`, `REMOTE_MODEL_TOKEN`,
`DR_SUPPORT_HOSPITAL_LINKAGE_KEY`, and the private PostgreSQL URL. The roots,
credentials, images, weights, and database values must not be placed in Git or
printed in receipts.

The private access boundary is an authenticated SSH account plus loopback-only
forwarding; do not bind `8769`, `8881`, `7865`, or `7866` to a public interface.
The Review API itself is a localhost single-user service and does not add a
second browser login; SSH account authorization and the loopback bind are the
required access boundary for this private demo. Do not expose the port through
a public reverse proxy without an approved authentication layer.
From an authorized Windows workstation, forward only the clinician URL:

```powershell
ssh -N `
  -L 8769:127.0.0.1:8769 `
  user@lightning-host
```

Then open `http://127.0.0.1:8769/app/`. The SSH session is the access-control
boundary; the browser URL is not a public endpoint and the internal model ports
are never forwarded to clinicians. If the unified lane is unavailable, the
operator may forward the preserved fallbacks instead:

```powershell
ssh -N `
  -L 8767:127.0.0.1:8767 `
  -L 8768:127.0.0.1:8768 `
  user@lightning-host
```

The unified queue keeps source origin `HOSPITAL_AUTHORIZED`, server-side UWF /
CFP modality binding, opaque case references, immutable Original RGB, and
PostgreSQL audit history. It does not relabel hospital data as PUBLIC or
SYNTHETIC. Hospital dataset export remains fail-closed; a successful model
inference or a test-actor review does not grant export authorization.

The gateway discovery endpoint merges duplicate IDs from a combined native
backend without ambiguity and prefers a ready descriptor from a dedicated
backend. Its aggregate `/health` reports verified model assets only when every
configured backend reports verified assets. Versioned PRISM UWF requests use
the existing Bridge v2.1 contract; UWF PRISM remains experimental and does not
claim PREPARED or clinical validation.

### Verified private smoke scope

The current Lightning verification covered, without printing patient data:

- one shared queue containing 21 authorized UWF and 10 authorized CFP cases;
- authenticated gateway and Review health/model discovery;
- UWF global inference routed to USPEC and CFP global inference routed to
  RETFound;
- UWF and CFP lesion requests routed to PRISM, including a real UWF Bridge
  v2.1 request;
- four eligible verified same-eye UWF comparisons;
- existing `8767` / `8768` services left healthy as fallback.

A test-actor PostgreSQL save/reload check is separate from clinician
confirmation and must not be presented as clinical sign-off or dataset
training ground truth. The UWF PRISM path remains research-only, and no
hospital portable GPU or external Windows connectivity claim is made by this
native receipt.
