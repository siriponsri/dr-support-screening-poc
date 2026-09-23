---
status: Accepted
date: 2026-09-23
---

# ADR-0007: Build documentation as code with Quarto, Mermaid, and self-contained HTML decks

## Context and problem statement

Manuals, guides, diagrams, and presentations must be reproducible from the repository, work offline, and not create competing sources of truth. The previous build scripts were removed from `main`, and README pointed at missing files.

## Considered options

- Separate ad-hoc scripts per document
- One build entry point (`scripts/docs/build_docs.py`) plus one QA script (`scripts/docs/check_docs.py`)

## Decision outcome

Quarto books (with XeLaTeX) produce the PDFs. Mermaid sources in `docs/architecture/` are rendered to PNG/SVG. The clinician image guide is one HTML file printed to PDF. Presentation sources inline shared `presenter.css`/`presenter.js` and images into offline HTML. `check_docs.py` verifies links, requirement IDs, and that presentation reveals match the Thai scripts.

### Consequences

- Good: one command per document; reviewable diffs; offline decks.
- Bad: the toolchain needs Quarto, TeX, Chromium, and mermaid-cli on the build machine; committed PDFs and HTML must be rebuilt when sources change.

## More information

`scripts/docs/build_docs.py`, Developer Technical Guide ch. 13.
