# Architecture diagrams

These are maintainable Mermaid sources. They use C4 semantics (levels are named in each file's first comment), drawn with flowchart and sequence syntax because Mermaid's native C4 syntax is still experimental.

| Source | View | Used in |
|:--|:--|:--|
| [01-system-context.mmd](01-system-context.mmd) | C4 System Context | Developer Technical Guide ch. 2, technical briefing |
| [02-container.mmd](02-container.mmd) | C4 Container | Developer Technical Guide ch. 2, technical briefing |
| [03-image-staging-boundary.mmd](03-image-staging-boundary.mmd) | Image ownership / staging boundary | Team Image Sampling Requirements ch. 2, Developer Technical Guide ch. 3 |
| [04-image-admission-flow.mmd](04-image-admission-flow.mmd) | Dynamic: admission and Confirm Image | Developer Technical Guide ch. 6 |
| [05-remote-inference-flow.mmd](05-remote-inference-flow.mmd) | Dynamic: remote inference | Developer Technical Guide ch. 7 |
| [06-dataset-provenance-flow.mmd](06-dataset-provenance-flow.mmd) | Dataset readiness and provenance | Developer Technical Guide ch. 9 |
| [07-deployment-topology.mmd](07-deployment-topology.mmd) | C4 Deployment | Developer Technical Guide ch. 12 |

Rendered PNG and SVG files live in [`rendered/`](rendered/). Regenerate them after editing a source:

```
python scripts/docs/build_docs.py diagrams
```

This needs `mmdc` (`npm install -g @mermaid-js/mermaid-cli`). Set `PUPPETEER_EXECUTABLE_PATH` to reuse an installed Chromium. The theme is defined in `mermaid-config.json` and uses the `DESIGN.md` colours.
