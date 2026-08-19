/** @type {import('tailwindcss').Config} */
export default {
  // Dizzaroo is light-only. Without this key Tailwind defaults to `media`, so any
  // stray `dark:` variant (alert/select/toast still carry some) flips dark under
  // OS dark mode. `class` makes them inert — no element ever gets the `dark` class.
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Dizzaroo Brand Colors
      colors: {
        'dizzaroo': {
          'deep-blue': '#1E73BE',
          'deep-blue-light': '#4A9FE8',
          'deep-blue-dark': '#155A94',
          'soft-green': '#76C893',
          'soft-green-light': '#A4D9B5',
          'soft-green-dark': '#5BA374',
          'blue-green': '#168AAD',
          'blue-green-light': '#4BA8C5',
          'blue-green-dark': '#116B87',
        },
        // Phase-1 design-system tokens (additive — coexist with legacy classes).
        // These are the *only* colours new components should reach for.
        brand: {
          50: '#E6F4F8',
          100: '#CCE9F1',
          200: '#99D3E3',
          500: '#168AAD',
          600: '#127190',
          700: '#0E5871',
        },
        accent: {
          50: '#EAF7EF',
          500: '#76C893',
          600: '#5BA374',
        },
        warning: {
          50: '#FEF3C7',
          500: '#F59E0B',
          600: '#D97706',
        },
        danger: {
          50: '#FEE2E2',
          500: '#DC2626',
          600: '#B91C1C',
        },
        // Flat color names for easier access
        'dizzaroo-deep-blue': '#1E73BE',
        'dizzaroo-soft-green': '#76C893',
        'dizzaroo-blue-green': '#168AAD',
        // Legacy support
        primary: {
          DEFAULT: '#1E73BE',
          50: '#E6F2FF',
          100: '#CCE5FF',
          200: '#99CBFF',
          300: '#66B1FF',
          400: '#3397FF',
          500: '#1E73BE',
          600: '#155A94',
          700: '#0D416A',
          800: '#052840',
          900: '#020F16',
        },
        secondary: {
          DEFAULT: '#76C893',
          50: '#F0F9F4',
          100: '#E1F3E9',
          200: '#C3E7D3',
          300: '#A4D9B5',
          400: '#86CD97',
          500: '#76C893',
          600: '#5BA374',
          700: '#457A58',
          800: '#2E513C',
          900: '#172820',
        },
      },
      // Dizzaroo DNA Gradient
      backgroundImage: {
        'dizzaroo-gradient': 'linear-gradient(135deg, #168AAD, #76C893)',
        'dizzaroo-gradient-hover': 'linear-gradient(135deg, #1E73BE, #76C893)',
        'dizzaroo-dna-gradient': 'linear-gradient(135deg, #168AAD, #76C893)',
      },
      // Urbanist Font Family
      fontFamily: {
        sans: ['Urbanist', 'system-ui', '-apple-system', 'sans-serif'],
        primary: ['Urbanist', 'sans-serif'],
      },
      // Typography Scale (with adjusted line-heights)
      fontSize: {
        'title': ['60px', { lineHeight: '1.2', letterSpacing: '-0.015em' }],      // text-6xl
        'heading': ['42px', { lineHeight: '1.25', letterSpacing: '-0.015em' }],   // text-4xl
        'subheading': ['36px', { lineHeight: '1.3', letterSpacing: '-0.015em' }], // text-3xl
        'medium-body': ['28px', { lineHeight: '1.35', letterSpacing: '0em' }],     // text-2xl
        'body': ['20px', { lineHeight: '1.4', letterSpacing: '0em' }],           // text-xl
        // Phase-1 UI scale (additive). Use these for any new component chrome.
        'ui-h1':      ['18px', { lineHeight: '24px', letterSpacing: '-0.01em', fontWeight: '600' }],
        'ui-h2':      ['14px', { lineHeight: '20px', letterSpacing: '0em',     fontWeight: '600' }],
        'ui-body':    ['13px', { lineHeight: '20px' }],
        'ui-body-sm': ['12px', { lineHeight: '18px' }],
        'ui-caption': ['11px', { lineHeight: '16px', fontWeight: '500' }],
      },
      // Border Radius (rounded UI)
      borderRadius: {
        'dizzaroo-sm': '0.5rem',
        'dizzaroo-md': '0.75rem',
        'dizzaroo-lg': '1rem',
        'dizzaroo-xl': '1.25rem',
      },
      // Custom Shadows
      boxShadow: {
        'dizzaroo': '0 4px 14px 0 rgba(30, 115, 190, 0.15)',
        'dizzaroo-lg': '0 10px 25px -5px rgba(30, 115, 190, 0.2)',
        // Phase-1: lightweight neutral shadows for cards/popovers.
        'card':       '0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 6px 0 rgb(0 0 0 / 0.04)',
        'card-hover': '0 2px 4px 0 rgb(0 0 0 / 0.06), 0 4px 12px 0 rgb(0 0 0 / 0.06)',
        'popover':    '0 4px 16px 0 rgb(0 0 0 / 0.10)',
      },
    },
  },
  plugins: [],
}

