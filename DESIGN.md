# DR Support Screening POC Design System

Status: normative design documentation for future frontend work

Baseline: accepted S1 implementation 9c781a226c082b64323042853ae7f4b06cbddee6

Scope: visual and interaction design only. This document does not add product
features and does not change APIs, model contracts, database behavior, or the
S1 viewer interaction model.

DESIGN.md is the design source of truth for S2 product expansion. The current
React implementation is Chakra UI + React + Vite. Future sessions must map the
rules below to the existing component and theme boundaries before introducing
new page-specific styling.

## 1. Design Principles

1. **The retinal image is the primary clinical object.** On review and
   fullscreen screens, the image receives the largest uninterrupted area and
   the strongest visual contrast. Supporting controls are quiet and compact.
2. **Clinical calm over product spectacle.** Use solid surfaces, restrained
   borders, clear typography, and deliberate whitespace. Avoid visual effects
   that compete with retinal findings.
3. **Green is an interaction role, not a clinical result.** KKU Faculty of
   Medicine Deep Green is the primary product action and navigation color. It
   must never mean normal, negative, safe, or resolved by itself.
4. **Red Soil is an institutional accent, not a clinical result.** Khon Kaen
   University Red Soil is secondary and restrained. It must never mean disease,
   error, danger, or rejection by itself.
5. **Clinical semantics use their own tokens.** Info, success, warning,
   danger, degraded, and unavailable states use dedicated semantic colors,
   icons, and text labels. Brand colors are not substituted for them.
6. **AI and human provenance must be obvious.** Overlay line style, labels,
   controls, and copy must distinguish AI suggestions from human annotations;
   color alone is never sufficient.
7. **Information density must serve a decision.** Prefer compact metadata,
   tables, and aligned fields where they help review. Do not compress spacing
   until labels, targets, or image details become hard to scan.
8. **Every state is explicit.** Loading, empty, error, offline, warning, and
   partial-result states must say what happened and what the user can do next.
9. **Accessibility is part of clinical correctness.** Keyboard access, visible
   focus, text alternatives, readable contrast, and non-color cues are required
   behavior, not polish.
10. **Preserve S1 interaction behavior.** Visual refinement must not silently
    change coordinate space, zoom bounds, pan behavior, overlay provenance,
    selection behavior, lock behavior, or the fullscreen review model.

## 2. Brand and Color Tokens

### 2.1 Brand roles

| Token | Value | Normative use |
|---|---|---|
| brand.medicineGreen | #016301 | Primary actions, active navigation, focus emphasis, product mark |
| brand.medicineGreenHover | #004D00 | Hover and selected interaction emphasis |
| brand.medicineGreenPressed | #003B00 | Pressed/active state for primary actions |
| brand.medicineGreenSoft | #E8F3E8 | Quiet selected background and secondary green action surface |
| brand.redSoil | #A73B24 | Institutional accent, restrained secondary emphasis, KKU context |
| brand.redSoilDark | #7C291A | Red Soil text or active institutional accent when contrast requires it |
| brand.redSoilSoft | #F5E9E5 | Quiet institutional accent background |

Medicine Green owns the primary interaction role. Red Soil must not be used for
the default primary button, active clinical result, error state, lesion class,
or disease severity.

### 2.2 Token architecture

Use three layers. Components consume semantic or component tokens; they do not
hard-code brand hex values. The exception is the documented retinal overlay
palette, which is a domain visualization palette and must remain independent
from the application chrome.

~~~css
/* Primitive: raw values with no UI meaning. */
:root {
  --primitive-brand-medicine-green: #016301;
  --primitive-brand-medicine-green-hover: #004D00;
  --primitive-brand-red-soil: #A73B24;
  --primitive-neutral-white: #FFFFFF;
  --primitive-neutral-ink: #172018;
}

/* Semantic: purpose aliases. */
:root {
  --color-action-primary: var(--primitive-brand-medicine-green);
  --color-action-primary-hover: var(--primitive-brand-medicine-green-hover);
  --color-accent-institutional: var(--primitive-brand-red-soil);
}

/* Component: local contracts. */
:root {
  --button-primary-background: var(--color-action-primary);
  --button-primary-background-hover: var(--color-action-primary-hover);
  --button-focus-ring: var(--color-focus);
}
~~~

### 2.3 Legacy alignment note

The accepted S1 theme currently assigns Red Soil to the brand role. That is a
naming/role mismatch with this normative system. No frontend implementation is
changed by this document; future theme work must remap the primary brand role
and keep Red Soil available as the institutional secondary accent.

## 3. Neutral and Semantic Colors

### 3.1 Neutral primitives

| Token | Value | Use |
|---|---|---|
| neutral.canvas | #F7F9F7 | Application background |
| neutral.panel | #FFFFFF | Panels, cards, dialogs, menus |
| neutral.subtle | #F1F4F1 | Quiet surfaces and hover backgrounds |
| neutral.muted | #E8ECE8 | Disabled surfaces and skeleton tracks |
| neutral.ink | #172018 | Primary text and headings |
| neutral.secondaryText | #52605A | Metadata, helper text, descriptions |
| neutral.mutedText | #75817B | Tertiary text only when paired with another cue |
| neutral.borderSubtle | #D8DFD9 | Default borders and dividers |
| neutral.borderDefault | #BFCABF | Input and table borders |
| neutral.borderStrong | #98A79B | Hover, active, and stronger separation |
| neutral.viewer | #0D1110 | Retinal viewer stage and image surround |
| neutral.inverse | #FFFFFF | Text on dark or solid brand surfaces |

### 3.2 Semantic tokens

These tokens communicate system state. They are separate from both brand
anchors and lesion colors. Every semantic state also needs a text label or
icon; color alone cannot carry meaning.

| Token | Value | Meaning |
|---|---|---|
| status.info | #245B9E | Informational or in-progress context |
| status.infoSoft | #EAF2FB | Informational surface |
| status.success | #2F7D5E | Completed/confirmed system state |
| status.successSoft | #E7F3ED | Success surface |
| status.warning | #9A6700 | Caution, partial result, or degraded state |
| status.warningSoft | #FBF2D9 | Warning surface |
| status.danger | #B42318 | Error, invalid action, or destructive action |
| status.dangerSoft | #FBE9E7 | Error surface |
| status.neutral | #667085 | Unknown, not started, or not applicable |
| status.neutralSoft | #F1F3F2 | Neutral surface |
| color.focus | #016301 | Keyboard focus ring; paired with a visible offset |

status.success is intentionally not brand.medicineGreen. status.danger is
intentionally not brand.redSoil.

### 3.3 Retinal annotation palette

These colors belong to the retinal visualization domain and are not UI theme
tokens. Preserve the current S1 values and their high contrast on the image.
Do not replace them with Medicine Green, Red Soil, or semantic status colors.

| Label | Token-like name for documentation | Value | Provenance |
|---|---|---|---|
| Microaneurysm | lesion.microaneurysm | #06B6D4 | AI or human |
| Hemorrhage | lesion.hemorrhage | #84CC16 | AI or human |
| Hard exudate | lesion.hardExudate | #E879F9 | AI or human |
| Soft exudate | lesion.softExudate | #6366F1 | AI or human |

Use class color plus provenance treatment:

- AI suggestion: class-colored dashed outline and a low-opacity fill.
- Human annotation: class-colored solid outline and a stronger fill.
- Selected human annotation: neutral dark selection outline plus the class
  color; do not recolor it to brand green.
- Preview geometry: neutral dark dashed outline and low-opacity fill.
- The legend must show both class and provenance treatment. Do not rely on
  hue alone, especially for color-vision differences.

## 4. Typography Hierarchy

Use Inter, already bundled by the frontend, with these fallbacks:
system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial,
sans-serif. Use tabular numerals for coordinates, percentages, dimensions, IDs,
and status values.

| Role | Size / line height | Weight | Use |
|---|---:|---:|---|
| Page title | 28px / 1.25; 22px mobile | 600 | One h1 per page |
| Section heading | 18px / 1.35 | 600 | Panel and section title |
| Subsection heading | 16px / 1.35 | 600 | Local grouping |
| Body | 13px / 1.5 | 400 | Main explanatory and data text |
| Emphasis body | 13px / 1.5 | 600 | Values, selected labels, important actions |
| Label | 12px / 1.35 | 600 | Form labels and table values needing emphasis |
| Metadata | 12px / 1.4 | 400 | Secondary context and helper text |
| Caption | 10-11px / 1.35 | 600 | Compact table headers, kicker, provenance key |
| Code / coordinates | 12px / 1.4 | 500 | IDs, pixel coordinates, model versions |

Rules:

- Use sentence case for labels, headings, buttons, and statuses.
- Uppercase is limited to small navigation kickers and table headers, with
  increased letter spacing and sufficient contrast.
- Do not use oversized hero type or long all-caps strings in clinical flows.
- Do not encode importance using bold alone; use layout, label, and grouping.
- Keep line lengths near 70-90 characters for explanatory copy.

## 5. Spacing Scale

Use a 4px base scale. Existing Chakra spacing values map directly to this
scale. Prefer the smallest value that preserves grouping and touchability.

| Token | Value | Typical use |
|---|---:|---|
| space.0 | 0px | Explicit reset |
| space.1 | 4px | Icon-to-label micro gap |
| space.1.5 | 6px | Tight status content |
| space.2 | 8px | Compact control gap |
| space.3 | 12px | Input padding, table compact gap |
| space.4 | 16px | Default component gap |
| space.5 | 20px | Section internal gap |
| space.6 | 24px | Section/page rhythm |
| space.7 | 28px | Page-side padding at laptop widths |
| space.8 | 32px | Major grouping |
| space.10 | 40px | Large empty-state breathing room |
| space.12 | 48px | Viewer or page separation |
| space.16 | 64px | Rare top-level separation |

Default layout guidance:

- Page padding: 16px mobile, 20px tablet, 28px laptop/desktop.
- Section-to-section gap: 20px; compact worklist gap: 16px.
- Panel padding: 16px mobile, 20px at laptop and above.
- Form field stack gap: 12px; label-to-control gap: 6px.
- Viewer toolbar-to-stage gap: 8px; stage-to-status gap: 8px.
- Do not use spacing as a substitute for a missing hierarchy or label.

## 6. Borders, Radius, and Shadows

| Token | Value | Use |
|---|---|---|
| radius.none | 0px | Full-bleed viewer and strict table edges |
| radius.sm | 5px | Compact controls, thumbnails, badges |
| radius.md | 8px | Buttons, inputs, panels, viewer stage |
| radius.lg | 10px | Main sections and dialogs |
| radius.xl | 12px | Only large dialogs or grouped overlays |
| radius.full | 9999px | Circular indicators and compact status pills only |

- Default border: 1px solid neutral.borderSubtle.
- Use neutral.borderDefault for inputs, selected rows, and control groups.
- Use neutral.borderStrong only for hover, active, or clear structural
  separation.
- Panels are defined by a border first. A shadow is optional and subtle.
- shadow.xs: 0 1px 1px rgb(15 23 42 / 0.04) for quiet panels.
- shadow.sm: 0 1px 2px rgb(15 23 42 / 0.06) for interactive surfaces.
- shadow.md: 0 2px 6px rgb(15 23 42 / 0.08) for menus and drawers.
- shadow.lg: 0 8px 24px rgb(15 23 42 / 0.10) for dialogs only.
- No decorative shadows, floating card stacks, or glow effects.
- Gradients are exceptional. Solid surfaces are the default; if a gradient is
  ever required, it must be low contrast, short-range, and support hierarchy
  rather than decoration.

## 7. Buttons and Icon Buttons

### Button variants

| Variant | Treatment | Use |
|---|---|---|
| Primary | Solid Medicine Green, inverse text | Commit, save, continue, analyze |
| Secondary | Medicine Green soft surface, deep green text, 1px border | Related action with lower emphasis |
| Outline | Panel surface, neutral border, primary text | Tertiary actions and navigation |
| Ghost | Transparent, secondary text; subtle hover surface | Toolbar and low-emphasis actions |
| Institutional | Red Soil text or soft surface, neutral/Red Soil border | Explicit KKU or institutional context only |
| Danger | status.danger semantic treatment | Destructive or invalid action only |

Red Soil is not the default primary action. It is not a severity cue. A
destructive action must use status.danger, not Red Soil.

### Sizes and states

| Size | Height | Horizontal padding | Icon |
|---|---:|---:|---:|
| Compact | 32px | 12px | 14-16px |
| Default | 36px | 16px | 16-18px |
| Comfortable | 42px | 20px | 18-20px |
| Icon-only default | 36px square | 0 | 16-18px |
| Icon-only touch target | 44px square | 0 | 18-20px |

States are ordered: disabled, loading, pressed, focus, hover, default.

- Hover changes background/border, not meaning.
- Pressed uses the darker action token and no added shadow.
- Focus-visible uses a 2px ring with a 2px offset; never remove the ring.
- Disabled controls use a muted surface/text and at least 0.55 opacity, plus
  the actual disabled attribute or aria-disabled where appropriate.
- Loading keeps the action label when possible, shows a spinner, prevents
  duplicate activation, and explains progress when the action is long-running.
- Icon-only controls require an accessible name and a tooltip for discovery;
  the tooltip cannot be the only accessible name.
- Use Lucide icons already available in frontend/src/lib/icons.ts. Do not use
  emoji or custom decorative glyphs for controls.

## 8. Inputs and Selects

- Default control height is 36px; use 32px only in dense toolbars and 42px for
  touch-oriented or high-importance forms.
- Use a visible label above the control. Placeholder text is not a label.
- Input background is neutral.panel; border is neutral.borderDefault.
- Hover uses neutral.borderStrong.
- Focus-visible uses color.focus plus a visible offset ring.
- Invalid state uses status.danger, aria-invalid="true", and an adjacent
  message that states how to correct the value.
- Disabled state uses neutral.muted and muted text; it must remain legible.
- Selects retain a native or accessible trigger affordance. Do not hide the
  selected value behind an icon.
- Helper text belongs below the control and is visually quieter than the
  label, but not below readable contrast.
- In annotation tools, the lesion-class select is a domain control and uses
  the independent lesion palette in its legend, not the brand palette.

## 9. Tabs

- Use semantic tablist, tab, and tabpanel roles when content changes in place;
  use links when tabs navigate to distinct routes.
- Default tab treatment is text on a transparent surface with a 2px bottom
  indicator. Active indicator and active text use Medicine Green.
- Inactive text uses neutral.secondaryText; hover uses neutral.ink and a
  subtle neutral background.
- Do not use large pill tabs or colored tab panels.
- Keep tab labels short and stable. Optional counts use neutral tabular text,
  not a KPI card.
- Keyboard order is visible and predictable: Tab enters the tablist, Arrow
  keys move between tabs, Enter/Space activates when the pattern requires it.
- On mobile, allow horizontal scrolling rather than wrapping tabs into an
  unreadable second navigation row.

## 10. Tables and Worklists

Worklists are decision surfaces, not dashboard decoration.

- Use a bordered table container with solid panel surface and no floating card
  treatment.
- Header: 10-11px semibold, sentence-case or short uppercase labels, subtle
  neutral surface, 12px x 16px padding.
- Row: 48px default height, 40px compact height, 56px comfortable height.
- Cell padding: 12px x 16px by default; reduce only for proven dense review.
- Text is left aligned; numbers and timestamps are right aligned; statuses are
  left aligned with badge text; row actions are right aligned.
- Hover uses neutral.subtle. Selection uses brand.medicineGreenSoft plus a
  non-color selection cue such as a left rule or checkbox.
- Do not stripe rows unless a future data density test proves it necessary.
- Preview thumbnails use a dark neutral surround and preserve aspect ratio.
  The thumbnail is a navigation aid, not a replacement for review.
- IDs, model versions, revisions, and dimensions use the code/coordinate style.
- Status badges use semantic tokens and explicit text. Never use green for
  "normal" or Red Soil for "disease".
- On narrow screens, keep required columns and provide horizontal scrolling or
  a documented stacked row pattern. Do not silently hide clinical status.
- Empty, loading, error, and degraded table states occupy the same table
  region so the layout does not jump unnecessarily.

## 11. Navigation and Sidebar

- The shell is a quiet persistent frame: panel surface, 1px divider, no heavy
  shadow, and clear page context in the top bar.
- Expanded sidebar widths: approximately 210px tablet, 236px laptop, 256px
  desktop. Collapsed mode is approximately 64-68px and icon-only.
- Mobile uses a navigation drawer opened by a labeled menu control.
- Brand mark may use Medicine Green. Institutional Red Soil may appear as a
  small secondary detail, but must not dominate the shell.
- Active navigation uses Medicine Green text/indicator and a soft green
  background. Do not use Red Soil as the default active state.
- The active state needs aria-current="page"; collapsed icon-only items need
  tooltips and accessible labels.
- Group navigation by task, not by implementation or API endpoint. Keep the
  existing product areas recognizable.
- Workspace context belongs near navigation and must remain visually distinct
  from the clinical image/result state.
- Environment notices such as public/synthetic-only are persistent, concise,
  and use semantic status treatment rather than decorative branding.

## 12. Toolbars

- A toolbar is a single horizontal control band with related actions, not a
  collection of unrelated cards.
- Use 8px gaps between controls and 16px between control groups.
- Primary action may be solid Medicine Green; secondary actions are outline or
  ghost. Keep destructive actions separated and semantic.
- Toolbars may wrap on tablet/mobile. They must never cover the retinal image.
- Icon-only controls need labels, tooltips, and a visible focus state.
- Preserve the existing viewer toolbar order where possible: zoom out, 100%,
  zoom in, Fit, Coordinate Inspector, fullscreen.
- For annotation, keep tools grouped: selection/drawing, history and object
  actions, lesion class, and visibility toggles.
- A toolbar should not become a KPI row. Do not place unrelated totals or
  summary cards beside controls.

## 13. Full-Screen Retinal Viewer

The fullscreen viewer is a focused review surface. It is not a dashboard or a
decorative modal.

### Layout

- Use the existing full-viewport modal pattern: darkened backdrop, full-width
  and full-height content, no rounded outer dialog, and no competing sidebar.
- Header contains case display name, image dimensions/modality when available,
  zoom controls, and a clearly labeled close/exit control.
- Annotation controls, when present, occupy one compact panel between the
  header and stage. They may scroll or wrap, but they must not reduce the
  image below a usable review area.
- The viewer stage uses neutral.viewer, overflow hidden, and a visible focus
  target. The image and SVG overlay remain in one transformed stage.
- Status information stays below the stage. It is compact and uses tabular
  numerals for zoom and coordinates.
- The retinal image remains visually dominant. No gradient, glow, giant card,
  or decorative illustration is allowed in this surface.

### S1 interaction contract

Future visual work must preserve these behaviors from the accepted baseline:

- Fit-to-viewport is the initial state and resets when the active case or
  fullscreen state changes.
- Zoom is bounded, uses the existing 1.2 step behavior, and keeps wheel zoom
  centered on the pointer where supported.
- 100% centers the image at actual scale; Fit returns to fit scale.
- Right-drag and Space + left-drag pan the image. Panning is bounded to the
  viewport and does not enter an annotation tool.
- Double-click fits the image when it is not completing a polygon.
- Context menu is suppressed within the viewer so right-drag remains usable.
- Fullscreen shows the same image, overlays, controls, and coordinate basis as
  the inline viewer. Exit is available by a labeled control and Escape.
- Image and overlay geometry stay in original image pixel space. Scaling and
  panning are presentation transforms only.

## 14. Annotation Visual States

### AI suggestions

- Use the fixed class color, a dashed outline, and low-opacity fill.
- Show a readable class label and score where present; label text must not be
  confused with a human annotation.
- AI shapes are immutable in the S1 editor: no resize handles and no drag
  editing.
- Toggling AI visibility must not alter human annotations or their selection.

### Human annotations

- Use the fixed class color, a solid outline, and stronger fill than AI.
- Display a clear provenance label such as HUMAN - MA where space permits.
- Human shapes are selectable. Selection is a neutral dark outline with a
  stronger non-scaling stroke so it remains visible at any zoom.
- Only an unlocked human rectangle exposes eight resize handles. Handles are
  white with a dark outline and use the appropriate resize cursor.
- Human polygon, point, and circle geometry must retain the same provenance
  treatment even when selected.

### Drawing preview and legend

- In-progress geometry uses a neutral dark dashed outline and low-opacity fill;
  it must not look like a saved AI or human result.
- The legend shows the four class colors plus the AI dashed/human solid rule.
- Add text or pattern cues whenever overlays could be confused by hue alone.
- Annotation visibility controls use explicit AI on/off and Human on/off
  language or an equivalent accessible label.

## 15. Selected, Locked, Unlocked, and Disabled States

| State | Visual treatment | Interaction |
|---|---|---|
| Selected | Dark neutral outline, stronger stroke, visible label; class color remains | Can be acted on by the enabled tool |
| Unlocked human | Normal human overlay plus handles when selected | May move/resize according to geometry and tool |
| Locked human | Normal human overlay, lock affordance in controls, no handles | Cannot move or resize; can still be identified |
| Disabled control | Muted surface/text, reduced emphasis, no hover treatment | Cannot activate; must expose disabled semantics |
| Loading control | Existing control shape with spinner and disabled duplicate activation | Action is in progress |
| Inspector active | Crosshair/active target button, editing controls disabled | Coordinates can be read; geometry cannot mutate |

Do not use color alone to indicate selected or locked state. Use outline,
handles, icon, label, aria-pressed, or aria-disabled as appropriate. A record
without an explicit locked: false remains protected by default, as in the
current S1 behavior.

## 16. Coordinate Inspector State

Coordinate Inspector is a mode, not a tooltip.

- The target control uses an accessible name such as Enable coordinate
  inspector and Disable coordinate inspector, plus aria-pressed.
- Active state uses the primary interaction treatment and a crosshair cursor.
- Selecting Inspector exits or suspends drawing, selection, movement, and
  resizing. Tool buttons and mutation actions are visibly disabled.
- Existing annotations remain visually present but do not receive resize
  handles. Pointer movement never changes geometry.
- Left pointer movement reports original-image X and Y coordinates in a fixed
  status area below the stage. Use one decimal place and tabular numerals.
- The coordinate readout must be text, not color or a hover-only tooltip.
- Zoom and bounded pan remain available as in S1. Escape exits Inspector,
  clears the readout, and returns to Select.
- Keyboard shortcut X toggles Inspector when the viewer owns focus. Escape
  always exits the mode before performing any page-level escape behavior.

## 17. Status Bar

The status bar is a quiet, persistent line immediately below the viewer stage.
It has a minimum 28px height, wraps when needed, and uses 11-12px text.

It may contain:

- current viewer zoom percentage;
- the current navigation hint in inline view or fullscreen;
- Original pixels: X ... - Y ... px while Inspector is active;
- the invariant Geometry: original image pixels statement in fullscreen;
- AI suggestion and human annotation provenance keys.

Use aria-live="polite" for changing zoom/coordinate text, but do not make the
entire viewer announce on every pointer move. Keep high-frequency changes
concise and do not replace the status bar with transient toasts.

## 18. Empty, Loading, Error, and Degraded States

### Empty

- Use a quiet bordered panel or table-region message, not a large illustration.
- State what is empty, why it may be empty, and the next valid action when one
  exists, such as open Worklist or choose a workspace.
- Never imply that an empty result means a negative clinical finding.

### Loading

- Use a small spinner or restrained skeleton in the content region.
- Preserve already loaded image/result content during a refresh when possible;
  do not replace a usable viewer with a blank page.
- Long-running inference displays the current existing progress message and
  prevents duplicate actions.

### Error

- Use status.danger tokens, an icon, a concise title, and a useful message.
- Include Retry, Back, or recovery guidance only when the existing flow can
  perform it. Do not invent a recovery action that the API cannot support.
- Keep the error local to the failed region when the rest of the page remains
  usable.
- Error is never represented by Red Soil.

### Degraded or partial

- Use status.warning with explicit copy such as Partial, Warnings, or Not all
  model results returned.
- Preserve and label returned content. Do not show an all-clear state when one
  model, runtime, or result is missing.
- Runtime health states remain distinct: Connecting, Checking, Ready, Warnings,
  Offline/Disconnected. Use semantic status colors and text.

## 19. Accessibility and Contrast Principles

- Meet WCAG 2.2 AA for normal text (4.5:1), large text (3:1), and meaningful
  non-text UI boundaries (3:1) against their actual background.
- Test both brand and semantic combinations in the rendered component. Do not
  assume a soft background creates sufficient contrast for any foreground.
- Never convey a state through color alone. Pair it with text, icon, pattern,
  stroke style, position, or shape.
- Maintain a visible focus-visible ring with at least 2px thickness and a
  visible offset from the component.
- Make interactive targets at least 44px where touch use is expected. Compact
  controls may be 32-36px only when the surrounding target remains usable.
- Preserve logical DOM order, heading order, label associations, and keyboard
  operation. Do not make a div look like a button without button semantics.
- Icon-only controls need an accessible name; tooltips are supplemental.
- Retinal images need descriptive alt text. SVG annotation shapes need a
  meaningful group label or accessible title when they convey information.
- Do not let focus rings, labels, or status text be clipped by overflow.
- Respect reduced-motion preferences. Transitions should be short and should
  not animate retinal content, overlays, or coordinate readouts.
- Check keyboard navigation and screen-reader announcements for fullscreen,
  Inspector, lock/unlock, loading, and error states.

## 20. Responsive Rules

Use the current breakpoint intent:

| Tier | Width | Layout behavior |
|---|---:|---|
| Mobile | < 768px | Drawer navigation, single column, wrapped controls |
| Tablet | 768-1023px | Permanent or compact sidebar, dense single-column review where needed |
| Laptop | 1024-1279px | Two-column review when image remains primary |
| Desktop | >= 1280px | Wider two-column review, up to 1440px content measure |

- Review and annotation pages collapse to one column before the image becomes
  too narrow. The image column wins when space is constrained.
- Desktop review layouts may use approximately 1.35-1.4fr for the image and
  0.6-0.65fr for supporting content, with a 20px gap.
- On mobile, page header actions may wrap below the title. Do not truncate the
  primary action or case identity.
- Viewer controls wrap or horizontally scroll in a compact band. Keep the
  stage below them and keep the status bar visible.
- Fullscreen mobile layout prioritizes the stage, keeps close and essential
  viewer controls reachable, and allows annotation controls to scroll.
- Tables use horizontal scrolling or a documented stacked row pattern; no
  required clinical status is hidden only because the viewport is narrow.
- Use responsive text and spacing changes sparingly. Clinical labels should
  remain readable rather than shrinking below the documented minimums.

## 21. Rules for Future S2 Pages

These rules define presentation for future Workspace, Worklist, Dataset
Manifest, and Model Audit pages. They do not authorize new product behavior.

### Workspace

- Show the active workspace as context in the shell and page header, using a
  compact panel/list treatment rather than a dashboard card.
- Surface modality, source, image count, and current selection only when those
  values already exist in the contract.
- Use a clear selected row or active outline for workspace selection. Medicine
  Green indicates interaction selection, not dataset quality.
- Keep workspace context separate from model result and clinical status cues.

### Worklist

- Use a dense, scannable table with thumbnail, case identity, analysis state,
  review state, and the existing review action.
- Filters, search, or tabs may be added only when the product contract defines
  them; style them as a compact toolbar above the table.
- Use explicit status text and semantic tokens for Pending, Reviewed, Needs
  correction, Escalated, Partial, and Not analyzed.
- Do not add KPI-card summaries, decorative charts, or severity color scales.

### Dataset Manifest

- Treat the manifest as provenance data: IDs, filenames, source, modality,
  dimensions, admission state, revision, and available annotations.
- Use a table/detail split or expandable rows with code styling for IDs and
  dimensions. Preserve copyability and truncation affordances.
- Distinguish missing metadata, invalid metadata, and empty datasets using
  their explicit semantic states.
- Do not use retinal lesion colors for dataset rows or source badges.

### Model Audit

- Present model ID, version, runtime, timestamps, request/result provenance,
  warnings, and returned state in a structured table or detail panel.
- Use semantic status colors for Loaded, Warning, Offline, Failed, or Unknown.
  Medicine Green does not mean a model is clinically normal or trustworthy.
- Keep warnings adjacent to the model/result they qualify. Do not hide them in
  a global toast or decorative indicator.
- Use expandable details for long metadata and preserve readable monospace
  treatment for versions, revisions, and technical identifiers.
- Do not add confidence heatmaps, performance claims, or audit conclusions
  unless the existing data contract supplies them.

## 22. Do / Do Not

### Do

- Do use Medicine Green for primary product interaction and active navigation.
- Do use Red Soil as a restrained institutional accent only.
- Do keep clinical status colors separate from brand colors.
- Do preserve the four S1 lesion colors and distinguish AI from human by stroke,
  fill, label, and provenance.
- Do keep the retinal image dominant in review and fullscreen layouts.
- Do use borders, compact spacing, and small shadows to establish hierarchy.
- Do use Lucide icons with accessible names and visible focus states.
- Do make loading, error, degraded, and empty states explicit and recoverable.
- Do prefer semantic tokens and component tokens over hard-coded UI colors.

### Do not

- Do not interpret Medicine Green as normal, negative, safe, or resolved.
- Do not interpret Red Soil as disease, error, danger, or rejection.
- Do not use brand colors for lesion overlays or replace the S1 lesion palette.
- Do not use glassmorphism, sci-fi AI styling, heavy gradients, glow effects,
  giant rounded cards, or excessive shadows.
- Do not build KPI-card dashboards for clinical review, worklists, or audit.
- Do not use emoji-driven UI or decorative visual noise.
- Do not hide required clinical information on smaller screens.
- Do not change viewer coordinate space, API/model behavior, persistence, or
  existing S1 gestures as part of visual work.

## 23. Design-Token Examples for the Current React Frontend

The following examples are handoff examples, not a request to edit the frontend
in this task.

### CSS variable example

~~~css
:root {
  /* Primitive layer */
  --primitive-brand-green-500: #016301;
  --primitive-brand-green-700: #004D00;
  --primitive-brand-green-900: #003B00;
  --primitive-brand-green-050: #E8F3E8;
  --primitive-brand-red-soil-500: #A73B24;
  --primitive-brand-red-soil-700: #7C291A;
  --primitive-brand-red-soil-050: #F5E9E5;
  --primitive-neutral-canvas: #F7F9F7;
  --primitive-neutral-panel: #FFFFFF;
  --primitive-neutral-ink: #172018;
  --primitive-neutral-secondary: #52605A;
  --primitive-neutral-muted: #75817B;
  --primitive-neutral-border: #D8DFD9;
  --primitive-neutral-viewer: #0D1110;
  --primitive-status-info: #245B9E;
  --primitive-status-success: #2F7D5E;
  --primitive-status-warning: #9A6700;
  --primitive-status-danger: #B42318;

  /* Semantic layer */
  --color-action-primary: var(--primitive-brand-green-500);
  --color-action-primary-hover: var(--primitive-brand-green-700);
  --color-action-primary-pressed: var(--primitive-brand-green-900);
  --color-action-secondary-bg: var(--primitive-brand-green-050);
  --color-accent-institutional: var(--primitive-brand-red-soil-500);
  --color-accent-institutional-dark: var(--primitive-brand-red-soil-700);
  --color-surface-canvas: var(--primitive-neutral-canvas);
  --color-surface-panel: var(--primitive-neutral-panel);
  --color-text-primary: var(--primitive-neutral-ink);
  --color-text-secondary: var(--primitive-neutral-secondary);
  --color-text-muted: var(--primitive-neutral-muted);
  --color-border-subtle: var(--primitive-neutral-border);
  --color-viewer-background: var(--primitive-neutral-viewer);
  --color-status-info: var(--primitive-status-info);
  --color-status-success: var(--primitive-status-success);
  --color-status-warning: var(--primitive-status-warning);
  --color-status-danger: var(--primitive-status-danger);

  /* Component layer */
  --button-primary-bg: var(--color-action-primary);
  --button-primary-bg-hover: var(--color-action-primary-hover);
  --button-primary-fg: #FFFFFF;
  --button-radius: 8px;
  --input-border: var(--color-border-subtle);
  --input-focus-ring: var(--color-action-primary);
  --panel-radius: 10px;
  --viewer-radius: 8px;
}
~~~

### Chakra theme mapping example

~~~ts
const semanticTokens = {
  colors: {
    'action.primary': { default: '#016301' },
    'action.primaryHover': { default: '#004D00' },
    'accent.institutional': { default: '#A73B24' },
    'surface.canvas': { default: '#F7F9F7' },
    'surface.panel': { default: '#FFFFFF' },
    'text.primary': { default: '#172018' },
    'text.secondary': { default: '#52605A' },
    'status.info': { default: '#245B9E' },
    'status.success': { default: '#2F7D5E' },
    'status.warning': { default: '#9A6700' },
    'status.danger': { default: '#B42318' },
  },
};
~~~

Component usage should read as intent:

~~~tsx
<Button bg="action.primary" _hover={{ bg: 'action.primaryHover' }}>
  Save annotations
</Button>

<IconButton
  aria-label="Enable coordinate inspector"
  icon={<Target size={16} />}
  variant="outline"
  aria-pressed={isCoordinateInspector}
/>

<Text color="status.warning">Partial model result</Text>
~~~

Retinal overlay values remain local to the viewer visualization boundary:

~~~ts
const LESION_COLORS = {
  MICROANEURYSM: '#06B6D4',
  HEMORRHAGE: '#84CC16',
  HARD_EXUDATE: '#E879F9',
  SOFT_EXUDATE: '#6366F1',
} as const;
~~~

Do not promote those values into brand, status, or generic component tokens.
They have a different job and must remain independently testable.

## Unresolved Design Questions

These are implementation or product-ownership questions, not permission to
change the S1 contract:

1. Should the future theme keep Chakra semantic names such as brand.500 for
   compatibility, or migrate to explicit names such as action.primary in one
   deliberate theme pass?
2. Should the current docs/UI_THEME.md be marked historical, updated, or
   replaced once the Medicine Green role is implemented in the frontend?
3. Which exact clinical status vocabulary and icon set will be approved for
   production-facing review states beyond the current POC labels?
4. Will future S2 work require a formal dark viewer theme for non-fullscreen
   review, or should the dark surface remain scoped to the retinal stage?
5. Which additional keyboard and screen-reader test cases are required before
   Workspace, Dataset Manifest, and Model Audit are considered production-ready?

