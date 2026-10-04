# Phase 3 Artifact Receipt

Status: `BLOCKED_ARTIFACT / NOT_LOADED` for the preferred USPEC UWF grader.

| Capability | Artifact role | Expected identity | Observed receipt | Result |
| --- | --- | --- | --- | --- |
| USPEC UWF grading | `grading_state.pt` trained inference checkpoint | 1,213,535,294 bytes; SHA-256 `8f07eb11859f638faee368a56c7c532ca946fee320f92f030a0cf25c63b769ac` | The checkpoint is external to this repository/worktree; observed bytes and independent hash were unavailable | `BLOCKED_ARTIFACT` |
| USPEC base encoder | `USPEC_weights.pth` training/base asset | Historical role only; not the normal inference artifact | Not acquired or loaded | `NOT_RUN` |
| RETFound CFP comparator | `retfound-aptos5` | Source revision and expected checkpoint digest are recorded in the registry | Existing provider metadata and historical asset evidence remain separate from this Phase 3 run | `COMPARATOR_ONLY` |
| PRISM CFP comparator | `prism-dr-5fold` | Source revision is recorded; individual asset manifest remains authoritative | Historical 21/21 byte receipt is preserved; no new deserialization was attempted | `COMPARATOR_ONLY` |

No expected hash was rewritten, no checkpoint was copied into Git, and no
provider was promoted because a path or file happened to exist. Trust, rights,
runtime compatibility, hardware, domain, clinical, and release status remain
separate from byte identity.
