---
status: Accepted
date: 2026-09-23
---

# ADR-0001: Record architecture decisions

## Context and problem statement

Architecture knowledge for this POC is spread across milestone specs, `AGENTS.md`, and commit history. New maintainers cannot easily tell which choices are deliberate and protected.

## Considered options

- Keep decisions as plain Markdown ADRs in `docs/adr/`, reviewed like code
- Rely on commit messages and milestone specs only
- Use an external wiki

## Decision outcome

Record significant decisions as numbered MADR 4.0 (minimal variant) files in `docs/adr/`. Numbers are never reused. A reversed decision is marked *Superseded by ADR-NNNN*; it is never deleted. ADR-0002 to ADR-0006 retrospectively record decisions that are already implemented on `main` (verified at `ec74af8`). They do not introduce new behaviour.

### Consequences

- Good: decisions are versioned with the code and linked from the Developer Technical Guide.
- Bad: ADRs can drift unless every change that touches a decision updates or supersedes its ADR.

## More information

Nygard, *Documenting Architecture Decisions* (2011); MADR 4.0.0 (adr.github.io/madr).
