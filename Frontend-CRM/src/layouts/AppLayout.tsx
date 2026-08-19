import React from 'react'
import Navbar from '../components/Navbar'

interface AppLayoutProps {
  children: React.ReactNode
  currentMode?: string
  onModeChange?: (mode: string) => void
  onNavigateToUsers?: () => void
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  children,
  currentMode,
  onModeChange,
  onNavigateToUsers,
}) => {
  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-x-hidden">
      <Navbar
        currentMode={currentMode}
        onModeChange={onModeChange}
        onNavigateToUsers={onNavigateToUsers}
      />
      <div className="relative z-0 flex-1 flex flex-row min-h-0 overflow-hidden">
        <main className="relative z-0 flex-1 overflow-hidden overflow-x-hidden min-h-0">
          {children}
        </main>
      </div>
    </div>
  )
}

export default AppLayout
