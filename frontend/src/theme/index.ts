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
  focus: '0 0 0 3px rgba(167, 59, 36, 0.18)',
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
  semibold: 550,
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
    color: 'ink',
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
      // Brand
      'brand.50':  kkuColors.primarySoft,
      'brand.100': kkuColors.primarySoft,
      'brand.200': '#EBD0C7',
      'brand.300': '#D89C8D',
      'brand.400': '#C56C54',
      'brand.500': kkuColors.primary,
      'brand.600': kkuColors.primary,
      'brand.700': kkuColors.primaryDark,
      'brand.800': kkuColors.primaryDark,
      'brand.900': '#5A1E13',

      // Surfaces
      'surface.canvas':   kkuColors.surface,
      'surface.panel':    kkuColors.panel,
      'surface.subtle':   '#F6F4F2',
      'surface.muted':    '#F1EFEC',

      // Ink
      'text.primary':     kkuColors.ink,
      'text.secondary':   kkuColors.secondaryText,
      'text.muted':       '#8A93A0',
      'text.inverse':     '#FFFFFF',

      // Borders
      'border.subtle':    kkuColors.border,
      'border.default':   '#D8DBE0',
      'border.strong':    '#C2C6CD',
      'border.focus':     kkuColors.primary,

      // Status
      'status.info':          kkuColors.info,
      'status.info.bg':       kkuColors.infoSoft,
      'status.info.border':   kkuColors.infoBorder,
      'status.success':       kkuColors.success,
      'status.success.bg':    kkuColors.successSoft,
      'status.success.border':kkuColors.successBorder,
      'status.warning':       kkuColors.warning,
      'status.warning.bg':    kkuColors.warningSoft,
      'status.warning.border':kkuColors.warningBorder,
      'status.danger':        kkuColors.danger,
      'status.danger.bg':     kkuColors.dangerSoft,
      'status.danger.border': kkuColors.dangerBorder,
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
          bg: 'brand.500',
          color: 'white',
          _hover: { bg: 'brand.700' },
          _active: { bg: 'brand.700' },
        },
        outline: {
          bg: 'surface.panel',
          color: 'text.primary',
          borderColor: 'border.default',
          _hover: { bg: 'surface.subtle', borderColor: 'border.strong' },
        },
        secondary: {
          bg: 'brand.50',
          color: 'brand.700',
          borderColor: 'brand.100',
          _hover: { bg: '#EFD6CE' },
        },
        ghost: {
          bg: 'transparent',
          color: 'text.secondary',
          _hover: { bg: 'surface.subtle', color: 'text.primary' },
        },
        danger: {
          bg: 'status.danger.bg',
          color: 'status.danger',
          borderColor: 'status.danger.border',
          _hover: { bg: '#F5D6D2' },
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
          bg: 'brand.50',
          color: 'brand.700',
          borderWidth: '1px',
          borderColor: 'brand.100',
        },
        info: {
          bg: 'status.info.bg',
          color: 'status.info',
          borderWidth: '1px',
          borderColor: 'status.info.border',
        },
        success: {
          bg: 'status.success.bg',
          color: 'status.success',
          borderWidth: '1px',
          borderColor: 'status.success.border',
        },
        warning: {
          bg: 'status.warning.bg',
          color: 'status.warning',
          borderWidth: '1px',
          borderColor: 'status.warning.border',
        },
        danger: {
          bg: 'status.danger.bg',
          color: 'status.danger',
          borderWidth: '1px',
          borderColor: 'status.danger.border',
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
            bg: 'surface.panel',
            borderColor: 'border.default',
            color: 'text.primary',
            _hover: { borderColor: 'border.strong' },
            _focus: {
              borderColor: 'border.focus',
              boxShadow: 'focus',
            },
            _focusVisible: {
              borderColor: 'border.focus',
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
            bg: 'surface.panel',
            borderColor: 'border.default',
            color: 'text.primary',
            _hover: { borderColor: 'border.strong' },
            _focus: { borderColor: 'border.focus', boxShadow: 'focus' },
            _focusVisible: { borderColor: 'border.focus', boxShadow: 'focus' },
          },
        },
      },
      defaultProps: { variant: 'outline', size: 'md' },
    },
    Textarea: {
      baseStyle: { borderRadius: 'md' },
      variants: {
        outline: {
          bg: 'surface.panel',
          borderColor: 'border.default',
          color: 'text.primary',
          _hover: { borderColor: 'border.strong' },
          _focus: { borderColor: 'border.focus', boxShadow: 'focus' },
          _focusVisible: { borderColor: 'border.focus', boxShadow: 'focus' },
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
          bg: 'surface.panel',
          borderWidth: '1px',
          borderColor: 'border.subtle',
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
        boxShadow: '0 0 0 3px rgba(167, 59, 36, 0.18)',
      },
      '::selection': {
        background: kkuColors.primarySoft,
        color: kkuColors.primaryDark,
      },
    },
  },
};

export const theme = extendTheme(themeOverride);
