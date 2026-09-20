import { extendTheme, type ThemeConfig, type ThemeOverride } from '@chakra-ui/react';
import { kkuColors } from './colors';

const config: ThemeConfig = {
  initialColorMode: 'light',
  useSystemColorMode: false,
};

/**
 * Chakra breakpoint tokens — aligned to the responsive foundation spec.
 *
 *   base    < 768px   mobile
 *   tablet  768-1023  tablet
 *   laptop  1024-1279 laptop
 *   desktop ≥ 1280px  desktop
 */
const breakpoints = {
  base: '0em',
  tablet: '48em',
  laptop: '64em',
  desktop: '80em',
};

/**
 * Restraint: prefer a tight spacing scale so cards don't balloon.
 * 4px base, 0.5 step → 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64
 */
const space = {
  px: '1px',
  0.5: '2px',
  1: '4px',
  1.5: '6px',
  2: '8px',
  3: '12px',
  4: '16px',
  5: '20px',
  6: '24px',
  7: '28px',
  8: '32px',
  9: '36px',
  10: '40px',
  12: '48px',
  14: '56px',
  16: '64px',
  20: '80px',
  24: '96px',
  32: '128px',
};

/**
 * Restraint: keep radii small. No pill-shaped UI. 6–10px on most surfaces,
 * 12px on dialogs, full only on true circular indicators.
 */
const radii = {
  none: '0',
  xs: '3px',
  sm: '5px',
  base: '6px',
  md: '8px',
  lg: '10px',
  xl: '12px',
  '2xl': '16px',
  full: '9999px',
};

/**
 * Subtle shadows only — never the AI/dashboard "deep blur" look.
 */
const shadows = {
  xs: '0 1px 1px rgba(15, 23, 42, 0.04)',
  sm: '0 1px 2px rgba(15, 23, 42, 0.06)',
  md: '0 2px 6px rgba(15, 23, 42, 0.08)',
  lg: '0 8px 24px rgba(15, 23, 42, 0.10)',
  // A light offset keeps the green focus ring visible on both panel and
  // canvas surfaces without changing the component's layout bounds.
  focus: `0 0 0 2px ${kkuColors.neutralPanel}, 0 0 0 4px ${kkuColors.medicineGreen}`,
};

const fontSizes = {
  xxs: '10px',
  xs: '11px',
  sm: '12px',
  md: '13px',
  lg: '14px',
  xl: '16px',
  '2xl': '18px',
  '3xl': '22px',
  '4xl': '28px',
  '5xl': '34px',
};

const fontWeights = {
  normal: 400,
  medium: 500,
  semibold: 600,
  bold: 600,
  strong: 700,
};

const lineHeights = {
  tight: 1.25,
  snug: 1.35,
  normal: 1.5,
  relaxed: 1.65,
};

/**
 * Heading typography — tight tracking, semibold weight, never screaming-bold.
 */
const headingTheme = {
  baseStyle: {
    color: 'text.primary',
    fontWeight: 'semibold',
    letterSpacing: '-0.01em',
    lineHeight: 'snug',
  },
  sizes: {
    xs: { fontSize: 'sm', fontWeight: 'semibold' },
    sm: { fontSize: 'md', fontWeight: 'semibold' },
    md: { fontSize: 'lg', fontWeight: 'semibold' },
    lg: { fontSize: 'xl', fontWeight: 'semibold' },
    xl: { fontSize: '2xl', fontWeight: 'semibold', letterSpacing: '-0.015em' },
    '2xl': { fontSize: '3xl', fontWeight: 'semibold', letterSpacing: '-0.02em' },
    '3xl': { fontSize: '4xl', fontWeight: 'semibold', letterSpacing: '-0.02em' },
  },
};

const themeOverride: ThemeOverride = {
  config,
  breakpoints,
  fonts: {
    heading:
      "'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    body:
      "'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    mono: "ui-monospace, SFMono-Regular, 'JetBrains Mono', Menlo, Consolas, monospace",
  },
  fontSizes,
  fontWeights,
  lineHeights,
  space,
  radii,
  shadows,
  semanticTokens: {
    colors: {
      // Semantic role aliases. Components should not consume raw primitives.
      'action.primary': kkuColors.medicineGreen,
      'action.primaryHover': kkuColors.medicineGreenHover,
      'action.primaryPressed': kkuColors.medicineGreenPressed,
      'action.primarySoft': kkuColors.medicineGreenSoft,
      'action.primaryBorder': kkuColors.medicineGreenBorder,
      'accent.institutional': kkuColors.redSoil,
      'accent.institutionalDark': kkuColors.redSoilDark,
      'accent.institutionalSoft': kkuColors.redSoilSoft,
      'accent.institutionalBorder': kkuColors.redSoilBorder,

      // Surfaces
      'surface.canvas': kkuColors.neutralCanvas,
      'surface.panel': kkuColors.neutralPanel,
      'surface.subtle': kkuColors.neutralSubtle,
      'surface.muted': kkuColors.neutralMuted,
      'surface.viewer': kkuColors.neutralViewer,

      // Ink
      'text.primary': kkuColors.neutralInk,
      'text.secondary': kkuColors.neutralSecondaryText,
      'text.muted': kkuColors.neutralMutedText,
      'text.inverse': kkuColors.neutralInverse,

      // Borders
      'border.subtle': kkuColors.neutralBorderSubtle,
      'border.default': kkuColors.neutralBorderDefault,
      'border.strong': kkuColors.neutralBorderStrong,
      'border.focus': kkuColors.medicineGreen,
      'color.focus': kkuColors.medicineGreen,

      // Status
      'status.info': kkuColors.statusInfo,
      'status.infoSoft': kkuColors.statusInfoSoft,
      'status.infoBorder': kkuColors.statusInfoBorder,
      'status.success': kkuColors.statusSuccess,
      'status.successSoft': kkuColors.statusSuccessSoft,
      'status.successBorder': kkuColors.statusSuccessBorder,
      'status.warning': kkuColors.statusWarning,
      'status.warningSoft': kkuColors.statusWarningSoft,
      'status.warningBorder': kkuColors.statusWarningBorder,
      'status.danger': kkuColors.statusDanger,
      'status.dangerSoft': kkuColors.statusDangerSoft,
      'status.dangerBorder': kkuColors.statusDangerBorder,
      'status.neutral': kkuColors.statusNeutral,
      'status.neutralSoft': kkuColors.statusNeutralSoft,

      // Component contracts. These are the final layer consumed by Chakra
      // variants and keep local treatment changes out of page components.
      'button.primary.background': kkuColors.medicineGreen,
      'button.primary.backgroundHover': kkuColors.medicineGreenHover,
      'button.primary.backgroundPressed': kkuColors.medicineGreenPressed,
      'button.primary.foreground': kkuColors.neutralInverse,
      'button.secondary.background': kkuColors.medicineGreenSoft,
      'button.secondary.foreground': kkuColors.medicineGreenHover,
      'button.secondary.border': kkuColors.medicineGreenBorder,
      'button.outline.background': kkuColors.neutralPanel,
      'button.outline.foreground': kkuColors.neutralInk,
      'button.outline.border': kkuColors.neutralBorderDefault,
      'button.ghost.foreground': kkuColors.neutralSecondaryText,
      'button.danger.background': kkuColors.statusDangerSoft,
      'button.danger.foreground': kkuColors.statusDanger,
      'button.danger.border': kkuColors.statusDangerBorder,
      'input.background': kkuColors.neutralPanel,
      'input.border': kkuColors.neutralBorderDefault,
      'input.borderHover': kkuColors.neutralBorderStrong,
      'input.borderFocus': kkuColors.medicineGreen,
      'panel.background': kkuColors.neutralPanel,
      'panel.border': kkuColors.neutralBorderSubtle,
      'viewer.background': kkuColors.neutralViewer,
    },
  },
  components: {
    Heading: headingTheme,
    Text: {
      baseStyle: {
        color: 'text.primary',
        lineHeight: 'normal',
      },
    },
    Checkbox: {
      baseStyle: {
        control: {
          borderColor: 'border.default',
          _checked: {
            bg: 'action.primary',
            borderColor: 'action.primary',
            _hover: { bg: 'action.primaryHover', borderColor: 'action.primaryHover' },
          },
          _focusVisible: { boxShadow: 'focus' },
        },
      },
    },
    Switch: {
      baseStyle: {
        track: {
          bg: 'border.default',
          _checked: { bg: 'action.primary' },
        },
        thumb: { bg: 'surface.panel' },
      },
    },
    Button: {
      baseStyle: {
        fontWeight: 'semibold',
        borderRadius: 'md',
        fontSize: 'md',
        _focusVisible: {
          boxShadow: 'focus',
          outline: 'none',
        },
        _disabled: {
          opacity: 0.55,
          cursor: 'not-allowed',
        },
      },
      sizes: {
        sm: { h: '32px', minW: '32px', px: 3, fontSize: 'sm' },
        md: { h: '36px', minW: '36px', px: 4, fontSize: 'md' },
        lg: { h: '42px', minW: '42px', px: 5, fontSize: 'lg' },
      },
      variants: {
        solid: {
          bg: 'button.primary.background',
          color: 'button.primary.foreground',
          _hover: { bg: 'button.primary.backgroundHover' },
          _active: { bg: 'button.primary.backgroundPressed' },
        },
        outline: {
          bg: 'button.outline.background',
          color: 'button.outline.foreground',
          borderColor: 'button.outline.border',
          _hover: { bg: 'surface.subtle', borderColor: 'border.strong' },
        },
        secondary: {
          bg: 'button.secondary.background',
          color: 'button.secondary.foreground',
          borderColor: 'button.secondary.border',
          _hover: { bg: 'button.secondary.border' },
        },
        ghost: {
          bg: 'transparent',
          color: 'button.ghost.foreground',
          _hover: { bg: 'surface.subtle', color: 'text.primary' },
        },
        danger: {
          bg: 'button.danger.background',
          color: 'button.danger.foreground',
          borderColor: 'button.danger.border',
          _hover: { bg: 'button.danger.border' },
        },
      },
      defaultProps: {
        variant: 'outline',
        size: 'md',
      },
    },
    Badge: {
      baseStyle: {
        textTransform: 'none',
        fontWeight: 'semibold',
        letterSpacing: '0.02em',
        borderRadius: 'sm',
        px: 2,
        py: '2px',
        fontSize: 'xxs',
      },
      variants: {
        subtle: {
          bg: 'surface.subtle',
          color: 'text.secondary',
          borderWidth: '1px',
          borderColor: 'border.subtle',
        },
        brand: {
          bg: 'action.primarySoft',
          color: 'action.primaryHover',
          borderWidth: '1px',
          borderColor: 'action.primaryBorder',
        },
        info: {
          bg: 'status.infoSoft',
          color: 'status.info',
          borderWidth: '1px',
          borderColor: 'status.infoBorder',
        },
        success: {
          bg: 'status.successSoft',
          color: 'status.success',
          borderWidth: '1px',
          borderColor: 'status.successBorder',
        },
        warning: {
          bg: 'status.warningSoft',
          color: 'status.warning',
          borderWidth: '1px',
          borderColor: 'status.warningBorder',
        },
        danger: {
          bg: 'status.dangerSoft',
          color: 'status.danger',
          borderWidth: '1px',
          borderColor: 'status.dangerBorder',
        },
      },
      defaultProps: { variant: 'subtle' },
    },
    Input: {
      baseStyle: {
        field: {
          borderRadius: 'md',
        },
      },
      sizes: {
        md: { field: { h: '36px', borderRadius: 'md', fontSize: 'md' } },
      },
      variants: {
        outline: {
          field: {
            bg: 'input.background',
            borderColor: 'input.border',
            color: 'text.primary',
            _hover: { borderColor: 'input.borderHover' },
            _focus: {
              borderColor: 'input.borderFocus',
              boxShadow: 'focus',
            },
            _focusVisible: {
              borderColor: 'input.borderFocus',
              boxShadow: 'focus',
            },
          },
        },
      },
      defaultProps: { variant: 'outline', size: 'md' },
    },
    Select: {
      baseStyle: {
        field: { borderRadius: 'md' },
      },
      sizes: {
        md: { field: { h: '36px', borderRadius: 'md', fontSize: 'md' } },
      },
      variants: {
        outline: {
          field: {
            bg: 'input.background',
            borderColor: 'input.border',
            color: 'text.primary',
            _hover: { borderColor: 'input.borderHover' },
            _focus: { borderColor: 'input.borderFocus', boxShadow: 'focus' },
            _focusVisible: { borderColor: 'input.borderFocus', boxShadow: 'focus' },
          },
        },
      },
      defaultProps: { variant: 'outline', size: 'md' },
    },
    Textarea: {
      baseStyle: { borderRadius: 'md' },
      variants: {
        outline: {
          bg: 'input.background',
          borderColor: 'input.border',
          color: 'text.primary',
          _hover: { borderColor: 'input.borderHover' },
          _focus: { borderColor: 'input.borderFocus', boxShadow: 'focus' },
          _focusVisible: { borderColor: 'input.borderFocus', boxShadow: 'focus' },
        },
      },
      defaultProps: { variant: 'outline' },
    },
    Table: {
      baseStyle: {
        table: {
          fontSize: 'md',
        },
        th: {
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          fontSize: 'xxs',
          color: 'text.secondary',
          fontWeight: 'bold',
          bg: 'surface.subtle',
          borderColor: 'border.subtle',
        },
        td: {
          borderColor: 'border.subtle',
          color: 'text.primary',
        },
      },
      variants: {
        clinical: {
          th: {
            px: 5,
            py: 3,
          },
          td: {
            px: 5,
            py: 4,
          },
        },
      },
      defaultProps: { variant: 'clinical', size: 'md' },
    },
    Modal: {
      baseStyle: {
        dialog: {
          borderRadius: 'lg',
          bg: 'panel.background',
          borderWidth: '1px',
          borderColor: 'panel.border',
          boxShadow: 'lg',
        },
        header: {
          fontWeight: 'semibold',
          fontSize: 'lg',
        },
      },
    },
    Drawer: {
      baseStyle: {
        dialog: {
          bg: 'surface.panel',
        },
        header: {
          fontWeight: 'semibold',
          fontSize: 'lg',
        },
      },
    },
    Alert: {
      baseStyle: {
        container: {
          borderRadius: 'md',
        },
        title: {
          fontWeight: 'semibold',
          fontSize: 'md',
        },
        description: {
          fontSize: 'sm',
          color: 'text.secondary',
        },
      },
    },
    Tooltip: {
      baseStyle: {
        bg: 'text.primary',
        color: 'text.inverse',
        fontSize: 'xs',
        px: 2,
        py: 1,
        borderRadius: 'sm',
      },
    },
  },
  styles: {
    global: {
      'html, body, #root': {
        height: '100%',
        bg: 'surface.canvas',
        color: 'text.primary',
      },
      body: {
        fontFeatureSettings: '"cv11", "ss01", "ss03"',
      },
      '*:focus-visible': {
        outline: 'none',
        boxShadow: 'focus',
      },
      '::selection': {
        background: kkuColors.medicineGreenSoft,
        color: kkuColors.medicineGreenHover,
      },
    },
  },
};

export const theme = extendTheme(themeOverride);
