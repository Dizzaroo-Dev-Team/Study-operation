import React, { useState, useRef, useEffect } from 'react'

interface ResizableSidebarProps {
  children: React.ReactNode
  defaultWidth?: number
  minWidth?: number
  maxWidth?: number
}

const ResizableSidebar: React.FC<ResizableSidebarProps> = ({ 
  children, 
  defaultWidth = 192, // w-48 = 192px
  minWidth = 150,
  maxWidth = 400
}) => {
  const [width, setWidth] = useState(defaultWidth)
  const [isResizing, setIsResizing] = useState(false)
  const sidebarRef = useRef<HTMLDivElement>(null)
  const startXRef = useRef<number>(0)
  const startWidthRef = useRef<number>(0)
  // Mirror min/max into refs so the mousemove closure reads the latest values
  // without forcing the effect to re-subscribe (which used to accumulate
  // duplicate listeners mid-drag whenever the parent re-rendered).
  const minWidthRef = useRef<number>(minWidth)
  const maxWidthRef = useRef<number>(maxWidth)
  useEffect(() => { minWidthRef.current = minWidth }, [minWidth])
  useEffect(() => { maxWidthRef.current = maxWidth }, [maxWidth])

  useEffect(() => {
    if (!isResizing) return

    const handleMouseMove = (e: MouseEvent) => {
      const diff = e.clientX - startXRef.current
      const newWidth = Math.max(
        minWidthRef.current,
        Math.min(maxWidthRef.current, startWidthRef.current + diff),
      )
      setWidth(newWidth)
    }

    const handleMouseUp = () => {
      setIsResizing(false)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizing])

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
    startXRef.current = e.clientX
    startWidthRef.current = width
  }

  return (
    <div 
      ref={sidebarRef}
      className="relative flex-shrink-0"
      style={{ width: `${width}px` }}
    >
      {children}
      <div
        onMouseDown={handleMouseDown}
        className={`absolute top-0 right-0 w-1 h-full cursor-col-resize hover:bg-dizzaroo-deep-blue transition-colors ${
          isResizing ? 'bg-dizzaroo-deep-blue' : 'bg-transparent'
        }`}
        style={{ zIndex: 10 }}
      />
    </div>
  )
}

export default ResizableSidebar

