# Dual-mode private deployment

This directory defines a portable, private Compose handoff without changing
qualified native model environments. It does not contain model weights,
hospital data, secrets, or runtime databases.

## Mode A: Lightning native

Use the already-qualified native services and the runbook in
`deployment/lightning-native/README.md`. This host-local deployment remains
the verified path for the Lightning Tesla T4. Windows access is through an
operator-created loopback SSH tunnel; no public bind or tunnel is configured by
these files.

## Mode B: portable GPU

Select exactly one profile and provide a private environment (never commit it):

```bash
set -a; . /private/secure/dual-mode-lightning-t4.env; set +a
./deployment/dual-mode/bin/preflight.sh
./deployment/dual-mode/bin/start.sh
./deployment/dual-mode/bin/status.sh
./deployment/dual-mode/bin/smoke.sh
./deployment/dual-mode/bin/stop.sh
```

The scripts scope operations to the Compose project
`dr-screening-dual-mode` (or `COMPOSE_PROJECT_NAME`). Preflight also requires
`DR_SCREENING_SOURCE_COMMIT` to be the exact 40-character Git SHA used for the
review image build identity. `stop.sh` only stops
that project and does not remove its PostgreSQL volume. There is no CPU
fallback: preflight requires `nvidia-smi`, exact target GPU identity, verified
external read-only assets, private credentials, and a non-placeholder base
image.

The gateway requires a bearer token for model metadata and inference. It is
loopback-bound by Compose, stateless, and routes UWF global requests to USPEC,
CFP global requests to RETFound, and lesion requests to PRISM. The review
service uses the existing Bridge contract and PostgreSQL schema.

## Status boundary

The current host has one Tesla T4. The portable Compose images and gateway
were exercised in a synthetic-only, sequential single-T4 smoke: UWF→USPEC,
CFP→RETFound, and CFP lesions→PRISM each returned HTTP 200. This is not
hospital portable inference and does not prove simultaneous three-GPU residency.
P40 and RTX 3090 are unavailable and remain `NOT_RUN`; the P40 profile image is
only a candidate Pascal base image, not P40 qualification. See
`GPU_COMPATIBILITY.md`.
