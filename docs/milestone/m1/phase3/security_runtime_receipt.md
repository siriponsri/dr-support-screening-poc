# Phase 3 Security and Runtime Receipt

## Security gate

- No Phase 3 checkpoint was deserialized in this execution.
- The legacy optional model environment pins PyTorch `2.5.1`; it is not treated as a qualified Phase 3 loader environment.
- The applicable PyTorch advisory review remains a pre-deserialization gate for the exact selected build and transitive loader path. `weights_only=True` and a SHA-256 match are not treated as complete security clearance.
- The registry records `BLOCKED_ARTIFACT` / `DISABLED` for USPEC until observed bytes, trust evidence, exact runtime, loader review, and compatibility evidence exist.
- No model download, arbitrary bundle code execution, secret transfer, hospital-data transfer, or model-weight write occurred.

## Runtime receipt

| Check | Status | Evidence |
| --- | --- | --- |
| Model API profile import and legacy contract surface | `PASS` | Focused profile and bridge tests |
| Versioned v2 contract import/validation | `PASS` | `tests/test_phase3_foundation.py` |
| GPU/CUDA target qualification | `NOT_RUN` | No designated Phase 3 target host was available |
| Exact USPEC/PRISM model load | `NOT_RUN` | Artifact/runtime gate was not cleared |
| Cold load, warm p50/p95, VRAM, recovery | `NOT_RUN` | No qualified target runtime |
| Live Model API Gate C | `NOT_RUN` | No approved live endpoint/token was available |
| Offline inference qualification | `NOT_RUN` | No qualified model bundle was enabled |
| PostgreSQL Phase 3 history round trip | `NOT_RUN` | No PostgreSQL DSN/server was available in this run |

Manual review remains available when the Model API or any capability is
unavailable. The Model API keeps one-worker/serialized inference behavior and
does not silently fall back to CPU in its strict production profile.
