# Deployment — Draft for S8 Rewrite

## Recommended topology

- **Clinician LAN client / workstation:** review UI + review API, remote model runtime.
- **Hospital GPU server:** local model runtime, RETFound + PRISM weights, Model API.
- **Workspace/export storage:** hospital-controlled filesystem with explicit backup policy.
- **CVAT Online:** optional external integration; not required for basic review/inference.

See `../assets/system-architecture.html` for the editable diagram source.

## Deployment principles

- Separate review workstation from GPU weight loading.
- Keep tokens in environment/secrets management, never committed files.
- Allow first-time internet access for setup only when approved.
- Verify local model assets before routine startup.
- After setup, demonstrate offline restart + inference.
- Restrict LAN exposure with host firewall/network policy; document bind address and port.
- Do not expose the Model API directly to the public internet by default.

## Release acceptance

Document exact service start/stop/restart, logs, health endpoint, review-to-model connectivity, reboot recovery, and rollback procedure.
