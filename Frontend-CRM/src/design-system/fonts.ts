/**
 * Dizzaroo Typography System
 * Using Urbanist font with custom kerning and line-height adjustments
 */

export const DizzarooTypography = {
  // Font Family
  fontFamily: {
    primary: ['Urbanist', 'sans-serif'],
  },
  
  // Font Sizes (mapped to Tailwind)
  fontSize: {
    title: '60pt',      // text-6xl
    heading: '42pt',   // text-4xl
    subheading: '36pt', // text-3xl
    mediumBody: '28pt', // text-2xl
    body: '20pt',       // text-xl
  },
  
  // Line Heights (adjusted +25-30%)
  lineHeight: {
    title: '1.2',      // 72px (60pt * 1.2)
    heading: '1.25',   // 52.5px (42pt * 1.25)
    subheading: '1.3', // 46.8px (36pt * 1.3)
    mediumBody: '1.35', // 37.8px (28pt * 1.35)
    body: '1.4',       // 28px (20pt * 1.4)
  },
  
  // Letter Spacing (kerning +15)
  letterSpacing: {
    tight: '-0.015em',
    normal: '0em',
    wide: '0.015em',
  },
  
  // Font Weights
  fontWeight: {
    light: 300,
    regular: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
} as const

