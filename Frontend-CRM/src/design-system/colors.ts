/**
 * Dizzaroo Brand Colors
 * Official color palette from Dizzaroo Brand Manual
 */

export const DizzarooColors = {
  // Primary Colors
  deepBlue: '#1E73BE',
  softGreen: '#76C893',
  blueGreen: '#168AAD',
  
  // Extended Palette
  deepBlueLight: '#4A9FE8',
  deepBlueDark: '#155A94',
  softGreenLight: '#A4D9B5',
  softGreenDark: '#5BA374',
  blueGreenLight: '#4BA8C5',
  blueGreenDark: '#116B87',
  
  // Neutral Colors
  white: '#FFFFFF',
  black: '#000000',
  gray50: '#F9FAFB',
  gray100: '#F3F4F6',
  gray200: '#E5E7EB',
  gray300: '#D1D5DB',
  gray400: '#9CA3AF',
  gray500: '#6B7280',
  gray600: '#4B5563',
  gray700: '#374151',
  gray800: '#1F2937',
  gray900: '#111827',
  
  // Semantic Colors
  success: '#76C893',
  info: '#168AAD',
  warning: '#F59E0B',
  error: '#EF4444',
} as const

/**
 * DNA Gradient (for accents only)
 * linear-gradient(135deg, #168AAD, #76C893)
 */
export const dizzarooGradient = 'linear-gradient(135deg, #168AAD, #76C893)'

/**
 * Tailwind-compatible color object
 */
export const tailwindColors = {
  'dizzaroo-deep-blue': DizzarooColors.deepBlue,
  'dizzaroo-soft-green': DizzarooColors.softGreen,
  'dizzaroo-blue-green': DizzarooColors.blueGreen,
  'dizzaroo-deep-blue-light': DizzarooColors.deepBlueLight,
  'dizzaroo-deep-blue-dark': DizzarooColors.deepBlueDark,
  'dizzaroo-soft-green-light': DizzarooColors.softGreenLight,
  'dizzaroo-soft-green-dark': DizzarooColors.softGreenDark,
  'dizzaroo-blue-green-light': DizzarooColors.blueGreenLight,
  'dizzaroo-blue-green-dark': DizzarooColors.blueGreenDark,
}

