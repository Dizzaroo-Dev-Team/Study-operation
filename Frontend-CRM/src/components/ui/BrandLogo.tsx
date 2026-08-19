import React from 'react'

interface BrandLogoProps {
  className?: string
  showText?: boolean
}

const BrandLogo: React.FC<BrandLogoProps> = ({ 
  className = '',
  showText = true 
}) => {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      {/* Logo placeholder - replace with actual Dizzaroo logo */}
      <div 
        className="flex items-center justify-center bg-dizzaroo-gradient rounded-xl"
        style={{ 
          minWidth: '125px',
          height: '50px',
          padding: '8px'
        }}
      >
        <span className="text-white font-bold text-xl">Dizzaroo</span>
      </div>
      {showText && (
        <span className="text-dizzaroo-deep-blue font-bold text-2xl hidden md:block">
          CRM
        </span>
      )}
    </div>
  )
}

export default BrandLogo

