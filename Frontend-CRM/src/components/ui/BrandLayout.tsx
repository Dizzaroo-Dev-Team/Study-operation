import React from 'react'
import BrandLogo from './BrandLogo'

interface BrandLayoutProps {
  children: React.ReactNode
  headerActions?: React.ReactNode
}

const BrandLayout: React.FC<BrandLayoutProps> = ({ 
  children, 
  headerActions 
}) => {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navbar with Deep Blue Header */}
      <nav className="bg-dizzaroo-deep-blue text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex justify-between items-center">
            <BrandLogo showText={true} />
            {headerActions && (
              <div className="flex items-center gap-3">
                {headerActions}
              </div>
            )}
          </div>
        </div>
      </nav>
      
      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-6">
        {children}
      </main>
    </div>
  )
}

export default BrandLayout

