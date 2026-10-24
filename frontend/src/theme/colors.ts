/**
 * Primitive values for the clinical product theme.
 *
 * Components should consume the semantic and component aliases in the Chakra
 * theme. Keeping the raw palette here makes the role mapping auditable and
 * prevents brand values from being reused as clinical status colors.
 */
export const primitiveColors = {
  // Brand primitives. Red Soil is institutional accent, never danger.
  medicineGreen: '#016301',
  medicineGreenHover: '#004D00',
  medicineGreenPressed: '#003B00',
  medicineGreenSoft: '#E8F3E8',
  medicineGreenBorder: '#B9D6B9',
  redSoil: '#A73B24',
  redSoilDark: '#7C291A',
  redSoilSoft: '#F5E9E5',
  redSoilBorder: '#E0B9AE',

  // Sidebar primitives: deep green-black navigation surface.
  sidebarBackground: '#16231A',
  sidebarRaised: '#1E2F23',
  sidebarActive: '#24382A',
  sidebarBorder: '#2A3B2F',
  sidebarBorderStrong: '#3E5444',
  sidebarText: '#EEF3EF',
  sidebarSecondaryText: '#A9BCAF',
  sidebarActiveMark: '#6FBF73',
  sidebarActiveText: '#FFFFFF',
  sidebarInstitutional: '#E3A08F',

  // Neutral primitives
  neutralCanvas: '#F6F7F6',
  neutralPanel: '#FFFFFF',
  neutralSubtle: '#F1F4F1',
  neutralMuted: '#E8ECE8',
  neutralInk: '#172018',
  neutralSecondaryText: '#52605A',
  neutralMutedText: '#75817B',
  neutralBorderSubtle: '#D8DFD9',
  neutralBorderDefault: '#BFCABF',
  neutralBorderStrong: '#98A79B',
  neutralViewer: '#0D1110',
  neutralInverse: '#FFFFFF',

  // Clinical semantic primitives remain independent from brand colors.
  statusInfo: '#245B9E',
  statusInfoSoft: '#EAF2FB',
  statusInfoBorder: '#B9CFEA',
  statusSuccess: '#2F7D5E',
  statusSuccessSoft: '#E7F3ED',
  statusSuccessBorder: '#B8DCCB',
  statusWarning: '#9A6700',
  statusWarningSoft: '#FBF2D9',
  statusWarningBorder: '#E6CD8B',
  statusDanger: '#B42318',
  statusDangerSoft: '#FBE9E7',
  statusDangerBorder: '#E9B7B1',
  statusNeutral: '#667085',
  statusNeutralSoft: '#F1F3F2',
} as const;

/** Compatibility name for the token preview page and existing imports. */
export const kkuColors = primitiveColors;

export type KkuColorKey = keyof typeof kkuColors;
