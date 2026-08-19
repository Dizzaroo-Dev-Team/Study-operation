import * as React from 'react'

export interface SheetProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children?: React.ReactNode
}

export interface SheetContentProps extends React.HTMLAttributes<HTMLDivElement> {
  side?: 'top' | 'bottom' | 'left' | 'right'
  /** Prevent the sheet from closing when clicking outside (e.g. into a Select portal) */
  onPointerDownOutside?: (e: PointerEvent | CustomEvent) => void
  onInteractOutside?: (e: PointerEvent | CustomEvent) => void
  onEscapeKeyDown?: (e: KeyboardEvent) => void
}

export declare const Sheet: React.FC<SheetProps>
export declare const SheetTrigger: React.FC<{ asChild?: boolean; children?: React.ReactNode }>
export declare const SheetClose: React.FC<{ asChild?: boolean; children?: React.ReactNode }>
export declare const SheetContent: React.ForwardRefExoticComponent<
  SheetContentProps & React.RefAttributes<HTMLDivElement>
>
export declare const SheetHeader: React.FC<React.HTMLAttributes<HTMLDivElement>>
export declare const SheetFooter: React.FC<React.HTMLAttributes<HTMLDivElement>>
export declare const SheetTitle: React.ForwardRefExoticComponent<
  React.HTMLAttributes<HTMLHeadingElement> & React.RefAttributes<HTMLHeadingElement>
>
export declare const SheetDescription: React.ForwardRefExoticComponent<
  React.HTMLAttributes<HTMLParagraphElement> & React.RefAttributes<HTMLParagraphElement>
>
