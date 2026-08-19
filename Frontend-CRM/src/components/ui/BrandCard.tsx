import React from 'react'

interface BrandCardProps {
  children: React.ReactNode
  className?: string
  withGradientAccent?: boolean
  hover?: boolean
}

const BrandCard: React.FC<BrandCardProps> = ({
  children,
  className = '',
  withGradientAccent = false,
  hover = false,
}) => {
  return (
    <div
      className={`
        bg-white rounded-xl dizzaroo-shadow
        ${withGradientAccent ? 'border-t-4 border-t-transparent bg-gradient-to-b from-transparent to-transparent' : ''}
        ${withGradientAccent ? 'relative overflow-hidden' : ''}
        ${hover ? 'hover:dizzaroo-shadow-lg transition-shadow duration-250' : ''}
        ${className}
      `}
      style={withGradientAccent ? {
        borderTopColor: 'transparent',
        background: 'linear-gradient(to bottom, #168AAD 4px, transparent 4px), white',
      } : {}}
    >
      {withGradientAccent && (
        <div className="absolute top-0 left-0 right-0 h-1 bg-dizzaroo-gradient"></div>
      )}
      <div className={withGradientAccent ? 'pt-1' : ''}>
        {children}
      </div>
    </div>
  )
}

export default BrandCard

