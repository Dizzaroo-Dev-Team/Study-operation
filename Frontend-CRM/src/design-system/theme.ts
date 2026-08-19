/**
 * Dizzaroo Design System Theme
 * Complete theme configuration including palette, typography, shadows, and radius
 */

import { DizzarooColors, dizzarooGradient } from './colors'
import { DizzarooTypography } from './fonts'

export const DizzarooTheme = {
  // Color Palette
  colors: DizzarooColors,
  gradient: dizzarooGradient,
  
  // Typography
  typography: DizzarooTypography,
  
  // Border Radius (rounded UI)
  borderRadius: {
    sm: '0.5rem',   // rounded-lg
    md: '0.75rem',  // rounded-xl
    lg: '1rem',     // rounded-2xl
    xl: '1.25rem',  // rounded-3xl
    full: '9999px', // rounded-full
  },
  
  // Shadows
  shadows: {
    sm: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
    xl: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
    'dizzaroo': '0 4px 14px 0 rgba(30, 115, 190, 0.15)',
  },
  
  // Spacing
  spacing: {
    xs: '0.25rem',  // 4px
    sm: '0.5rem',   // 8px
    md: '1rem',     // 16px
    lg: '1.5rem',   // 24px
    xl: '2rem',     // 32px
    '2xl': '3rem',  // 48px
    '3xl': '4rem',  // 64px
  },
  
  // Transitions
  transitions: {
    fast: '150ms ease-in-out',
    normal: '250ms ease-in-out',
    slow: '350ms ease-in-out',
  },
} as const

export type DizzarooThemeType = typeof DizzarooTheme

