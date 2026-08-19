import { createPortal } from 'react-dom'
import type { ReactNode } from 'react'

interface ModalOverlayProps {
  children: ReactNode
  onClose?: () => void
}

/** Portal modal backdrop above the navbar (z-[200]). */
export function ModalOverlay({ children, onClose }: ModalOverlayProps) {
  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center bg-black/50 p-4 overflow-y-auto"
      onClick={onClose}
    >
      {children}
    </div>,
    document.body,
  )
}
