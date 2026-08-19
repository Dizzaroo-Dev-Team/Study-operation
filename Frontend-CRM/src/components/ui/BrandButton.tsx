import React from 'react'

interface BrandButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'gradient'
  size?: 'sm' | 'md' | 'lg'
  children: React.ReactNode
}

const BrandButton: React.FC<BrandButtonProps> = ({
  variant = 'primary',
  size = 'md',
  children,
  className = '',
  ...props
}) => {
  const baseStyles = 'font-primary font-semibold rounded-xl transition-all duration-250 ease-in-out focus:outline-none focus:ring-2 focus:ring-offset-2'
  
  const variants = {
    primary: 'bg-dizzaroo-deep-blue text-white hover:bg-dizzaroo-deep-blue-dark focus:ring-dizzaroo-deep-blue dizzaroo-shadow hover:dizzaroo-shadow-lg',
    secondary: 'bg-dizzaroo-soft-green text-white hover:bg-dizzaroo-soft-green-dark focus:ring-dizzaroo-soft-green dizzaroo-shadow hover:dizzaroo-shadow-lg',
    outline: 'border-2 border-dizzaroo-deep-blue text-dizzaroo-deep-blue hover:bg-dizzaroo-deep-blue hover:text-white focus:ring-dizzaroo-deep-blue',
    gradient: 'bg-dizzaroo-gradient text-white hover:opacity-90 focus:ring-dizzaroo-blue-green dizzaroo-shadow hover:dizzaroo-shadow-lg',
  }
  
  const sizes = {
    sm: 'px-4 py-2 text-sm',
    md: 'px-6 py-3 text-base',
    lg: 'px-8 py-4 text-lg',
  }
  
  return (
    <button
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export default BrandButton

