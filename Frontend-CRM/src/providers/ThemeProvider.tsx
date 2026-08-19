import React from 'react'

interface ThemeProviderProps {
  children: React.ReactNode
}

/**
 * ThemeProvider - Injects Dizzaroo brand styles globally
 * Applies Urbanist font, CSS variables, and brand tokens
 */
export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  return (
    <div className="font-primary antialiased h-full min-h-0 w-full">
      {children}
    </div>
  )
}

export default ThemeProvider

