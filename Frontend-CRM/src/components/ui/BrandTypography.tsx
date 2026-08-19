import React from 'react'

interface TitleProps {
  children: React.ReactNode
  className?: string
}

export const Title: React.FC<TitleProps> = ({ children, className = '' }) => {
  return (
    <h1 className={`text-title font-bold text-dizzaroo-deep-blue ${className}`}>
      {children}
    </h1>
  )
}

interface HeadingProps {
  children: React.ReactNode
  className?: string
}

export const Heading: React.FC<HeadingProps> = ({ children, className = '' }) => {
  return (
    <h2 className={`text-heading font-semibold text-dizzaroo-deep-blue ${className}`}>
      {children}
    </h2>
  )
}

interface SubheadingProps {
  children: React.ReactNode
  className?: string
}

export const Subheading: React.FC<SubheadingProps> = ({ children, className = '' }) => {
  return (
    <h3 className={`text-subheading font-semibold text-gray-800 ${className}`}>
      {children}
    </h3>
  )
}

interface TextProps {
  children: React.ReactNode
  className?: string
  variant?: 'body' | 'medium' | 'small'
}

export const Text: React.FC<TextProps> = ({ 
  children, 
  className = '',
  variant = 'body'
}) => {
  const variants = {
    body: 'text-body',
    medium: 'text-medium-body',
    small: 'text-base',
  }
  
  return (
    <p className={`${variants[variant]} text-gray-700 ${className}`}>
      {children}
    </p>
  )
}

