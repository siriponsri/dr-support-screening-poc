# Clinician Image Selection Guide — source

The guide has one source file, [`../image-selection/IMAGE_SELECTION_GUIDE.html`](../image-selection/IMAGE_SELECTION_GUIDE.html).

The PDF [`../CLINICIAN_IMAGE_SELECTION_GUIDE.pdf`](../CLINICIAN_IMAGE_SELECTION_GUIDE.pdf) is printed from that same page, so the web version and the PDF never drift apart. Rebuild it with:

```
python scripts/docs/build_docs.py image-guide
```

## Rules for editing

- Keep the PDF to one page (two at most). Check it after every rebuild.
- The guide answers only four questions: what to choose, what to avoid, what to do if unsure, and whether the clinician manages dataset balance (they do not).
- Do not add forms, calculators, per-image fields, or data entry without explicit owner approval (IMG-SAMP-100, IMG-SAMP-101).
- Wording traces to [`../image-sampling-requirements/REQUIREMENTS_TRACEABILITY.md`](../image-sampling-requirements/REQUIREMENTS_TRACEABILITY.md). Change the requirement there first, then this guide.
- Use only drawings. Never add patient images or PHI.
