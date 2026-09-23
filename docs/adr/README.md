# Architecture decision records

This folder holds numbered ADRs in the MADR 4.0 minimal format. Decisions marked *retrospective* record behaviour that already exists on `main` and was verified in the code. They document the reasoning; they do not change anything.

| ADR | Title | Status |
|:--|:--|:--|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-split-review-workstation-and-gpu-model-api.md) | Split the review workstation and the GPU Model API through runtime profiles | Accepted (retrospective) |
| [0003](0003-immutable-source-and-separate-analysis-derivative.md) | Keep the source immutable and send a separate, hashed analysis derivative to models | Accepted (retrospective) |
| [0004](0004-three-human-confirmation-milestones.md) | Use three human confirmation milestones and keep AI evidence non-authoritative | Accepted (retrospective) |
| [0005](0005-task-specific-dataset-readiness.md) | Use task-specific dataset readiness and no automatic split | Accepted (retrospective) |
| [0006](0006-human-selected-image-intake-boundary.md) | Admit only human-selected, hospital-staged images; the team monitors coverage outside the Workbench | Accepted (owner decision, V4) |
| [0007](0007-docs-as-code-toolchain.md) | Build documentation as code with Quarto, Mermaid, and self-contained HTML decks | Accepted |

## How to add an ADR

1. Copy the structure of an existing ADR into `NNNN-short-title.md`, using the next unused number.
2. Keep it to one or two pages: context, options considered, decision, consequences (good and bad).
3. Link it from this table. To reverse a decision, write a new ADR and mark the old one *Superseded by ADR-NNNN*. Never delete an ADR.
4. A decision that changes a protected area in `AGENTS.md` also needs an owner-approved normative spec under `docs/`.
