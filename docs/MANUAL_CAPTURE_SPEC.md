# Manual Capture Specification

## Goal

Generate reproducible final clinician-manual screenshots with Playwright, then build a PDF from the final manual.

## Required properties

- use a deterministic public/synthetic workspace;
- capture final release commit only;
- desktop viewport recommended: `1440x900`;
- optional mobile appendix: `390x844`;
- hide/censor tokens and local machine paths;
- never use real patient data;
- wait for stable network/UI state before each capture;
- screenshots named in user-journey order;
- no ad-hoc manual screenshots in the final PDF.

## Recommended command surface

```text
npm run manual:capture
npm run manual:pdf
```

S8 may implement equivalent commands if they fit the repository better.

## Capture list

1. app/workspace entry
2. workspace selection
3. scan input
4. Worklist
5. Review image
6. AI overlay + confidence
7. optional advanced annotation entry
8. Dataset status
9. Export
10. Models & Audit

## PDF generation

Preferred approach: render a local HTML/manual page with the captured assets and use Playwright/Chromium `page.pdf()` for deterministic PDF output. Embed the release version/commit SHA in the footer.
