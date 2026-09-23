<!-- canonical-topic: presentations -->

# Presentation Sources

The presentation directory has one source for each deliverable:

- [Product HyperFrames source](hyperframes/index.html) is the live clinician/product deck.
- [Product source map](PRESENTATION_SOURCE_MAP.md) records source ownership and truth labels.
- [Thai product script](PRESENTATION_SCRIPT_TH.md) is the speaking script.
- [Technical source](src/TECHNICAL_BRIEFING.source.html) builds the technical briefing.
- [Thai technical script](TECHNICAL_PRESENTATION_SCRIPT_TH.md) is the technical speaking script.

`RETINAL_REVIEW_DEMO.html` and `TECHNICAL_BRIEFING.html` are generated offline
copies. Rebuild them from the repository root with:

```powershell
python scripts/docs/build_docs.py demo briefing
```

Presentation claims must be labeled as current UI, upstream/reference, or
proposal/future discussion. Owner-provided PPTX references stay local and
untracked; they are not generated repository artifacts.
