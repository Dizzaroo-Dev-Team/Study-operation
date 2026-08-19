import * as React from 'react'

export interface TooltipProviderProps {
  delayDuration?: number
  skipDelayDuration?: number
  disableHoverableContent?: boolean
  children?: React.ReactNode
}

export interface TooltipContentProps extends React.HTMLAttributes<HTMLDivElement> {
  side?: 'top' | 'bottom' | 'left' | 'right'
  sideOffset?: number
  align?: 'start' | 'center' | 'end'
  alignOffset?: number
}

export declare const TooltipProvider: React.FC<TooltipProviderProps>
export declare const Tooltip: React.FC<{ children?: React.ReactNode; open?: boolean; defaultOpen?: boolean; onOpenChange?: (open: boolean) => void }>
export declare const TooltipTrigger: React.ForwardRefExoticComponent<
  React.HTMLAttributes<HTMLElement> & { asChild?: boolean } & React.RefAttributes<HTMLElement>
>
export declare const TooltipContent: React.ForwardRefExoticComponent<
  TooltipContentProps & React.RefAttributes<HTMLDivElement>
>
