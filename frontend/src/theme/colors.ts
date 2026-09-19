/**
 * KKU Warm Clinical — design color tokens.
 *
 * The KKU Red-Soil anchor (#A73B24) is intentionally held for primary chrome
 * (CTA, active navigation, brand mark, focus emphasis). Every other role pulls
 * from the supporting neutrals and a single warm accent.
 *
 * Status colors (info / success / warning / danger) are reserved for status
 * states and information hierarchy — they should not be used decoratively.
 *
 * Lesion overlay colors (overlaid on retinal imagery) are deliberately NOT
 * part of the UI palette and remain an independent owner-defined CVAT palette.
 */

export const kkuColors = {
  // Brand anchor
  primary: '#A73B24',        // KKU Primary / Red Soil
  primaryDark: '#7C291A',    // Primary Dark / Deep Brick
  primarySoft: '#F4E5E0',    // Primary Soft / Clay Tint

  // Warm accent (used sparingly)
  accent: '#C99A45',         // Warm Accent / Muted Gold
  accentSoft: '#F7EEDB',

  // Neutral surfaces & text
  ink: '#202428',            // Ink
  secondaryText: '#667085',  // Secondary Text
  surface: '#FCFBFA',        // Application background
  panel: '#FFFFFF',          // Panels, cards, dialogs
  border: '#E5E7EB',         // Default border / divider

  // Status (semantic)
  info: '#2563EB',
  success: '#16865C',
  warning: '#D97706',
  danger: '#B42318',

  // Soft variants for status backgrounds (90% whitewashed for status pills)
  infoSoft: '#E8F0FE',
  successSoft: '#E3F5EC',
  warningSoft: '#FBEFDC',
  dangerSoft: '#FBE7E4',

  // Status borders (low-contrast companions for status pills)
  infoBorder: '#BFD4FA',
  successBorder: '#BFE3CF',
  warningBorder: '#F4D9A8',
  dangerBorder: '#F5C5BF',
} as const;

export type KkuColorKey = keyof typeof kkuColors;
