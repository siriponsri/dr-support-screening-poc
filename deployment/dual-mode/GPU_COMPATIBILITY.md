# Portable GPU compatibility matrix

This is a deployment definition and preflight contract, not a claim that every
profile has been runtime-qualified. Model assets are supplied from external
read-only mounts. No CPU fallback is supported.

| Profile | Target | Current host evidence | Portable Compose | GPU qualification |
|---|---|---|---|---|
| `lightning-t4` | Tesla T4, SM 7.5 | T4, 15,360 MiB, driver 580.178.04, CUDA runtime 12.8 / Torch 2.11.0+cu128 | Portable Compose image build and synthetic route smoke passed | PASS_SINGLE_HOST_T4_SMOKE |
| `ceo-p40` | Tesla P40, SM 6.1 / Pascal | Target unavailable | Definition only; select a P40-compatible image after preflight | NOT_RUN |
| `hospital-3090` | RTX 3090, SM 8.6 / Ampere | Target unavailable | Definition only; target-host preflight required | NOT_RUN |

The current Lightning host has one visible T4. The portable T4 evidence is
synthetic-only and sequential: UWF→USPEC, CFP→RETFound, and CFP lesions→PRISM
returned HTTP 200 while sharing one T4. It does not prove hospital portable
inference or simultaneous three-GPU residency. It cannot prove P40 or 3090
compatibility. The P40 profile names a candidate Pascal base image only; its
actual P40 runtime and inference qualification remain NOT_RUN and must not be
inferred from YAML parsing or static preflight.
`bin/preflight.sh` fails closed for a profile/GPU mismatch, placeholder image,
missing assets, missing secrets, or a missing CUDA runtime. The Compose file
binds every host port to loopback only.
