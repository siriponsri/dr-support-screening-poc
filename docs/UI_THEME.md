# Clinical UI Theme (Historical Handoff)

> [`DESIGN.md`](../DESIGN.md) is the normative design source. This file is
> retained as a migration note for the accepted React frontend and must not
> introduce a competing palette or interaction contract.

The React frontend uses a three-layer token architecture:

1. Primitive values live in `frontend/src/theme/colors.ts`.
2. Semantic aliases in `frontend/src/theme/index.ts` express action, surface,
   text, border, focus, viewer, and clinical status roles.
3. Component aliases in the same theme define button, input, panel, and viewer
   contracts consumed by Chakra component variants.

| Role | Token | HEX | Use |
|---|---|---|---|
| Primary action | `action.primary` | `#016301` | Medicine Green actions and active navigation |
| Primary hover | `action.primaryHover` | `#004D00` | Hover and selected interaction emphasis |
| Primary pressed | `action.primaryPressed` | `#003B00` | Pressed primary actions |
| Primary soft | `action.primarySoft` | `#E8F3E8` | Quiet selected and secondary action surfaces |
| Institutional accent | `accent.institutional` | `#A73B24` | Restrained KKU context only; never danger or disease |
| Application canvas | `surface.canvas` | `#F7F9F7` | Application background |
| Panel | `surface.panel` | `#FFFFFF` | Panels, cards, dialogs, and menus |
| Primary text | `text.primary` | `#172018` | Headings and body text |
| Secondary text | `text.secondary` | `#52605A` | Metadata, helper text, and descriptions |
| Subtle border | `border.subtle` | `#D8DFD9` | Default borders and dividers |
| Viewer stage | `surface.viewer` | `#0D1110` | Retinal image surround |
| Info | `status.info` | `#245B9E` | Informational and in-progress state |
| Success | `status.success` | `#2F7D5E` | Completed or confirmed system state |
| Warning | `status.warning` | `#9A6700` | Caution, partial result, or degraded state |
| Danger | `status.danger` | `#B42318` | Error, invalid action, or destructive action |

Medicine Green is an interaction role, not a clinical result. Red Soil is an
institutional accent, not a disease, error, danger, or rejection cue. Clinical
status colors remain independent from both brand anchors and retinal overlays.

The frontend keeps the accepted S1 retinal visualization palette independent
from application chrome:

- MICROANEURYSM `#06B6D4`
- HEMORRHAGE `#84CC16`
- HARD_EXUDATE `#E879F9`
- SOFT_EXUDATE `#6366F1`

AI suggestions use dashed outlines and low-opacity fills. Human annotations
use solid outlines, stronger fills, and explicit provenance labels. Selection,
preview geometry, and lock state use non-color cues as documented in
`DESIGN.md`.

No institutional logo or endorsement is included by this POC.
