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
