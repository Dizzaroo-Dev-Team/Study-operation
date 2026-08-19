"use client"

import * as React from "react"
import * as TooltipPrimitive from "@radix-ui/react-tooltip"

import { cn } from "@/lib/utils"

const TooltipProvider = TooltipPrimitive.Provider

const Tooltip = TooltipPrimitive.Root

const TooltipTrigger = TooltipPrimitive.Trigger

const TooltipArrow = TooltipPrimitive.Arrow

const TooltipContent = React.forwardRef(({ className, sideOffset = 8, children, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        // Base styles
        "z-[100] overflow-hidden rounded-lg shadow-2xl",
        // Background & Border
        "bg-slate-800 border border-slate-700",
        // Text styling
        "px-3 py-2 text-xs font-medium text-white",
        // Max width for long tooltips
        "max-w-xs",
        // Animations (professional, subtle)
        "animate-in fade-in-0 zoom-in-95 duration-200",
        "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=closed]:duration-150",
        // Slide animations based on side
        "data-[side=bottom]:slide-in-from-top-2",
        "data-[side=left]:slide-in-from-right-2", 
        "data-[side=right]:slide-in-from-left-2",
        "data-[side=top]:slide-in-from-bottom-2",
        // Transform origin
        "origin-[--radix-tooltip-content-transform-origin]",
        className
      )}
      {...props}
    >
      {children}
      <TooltipArrow className="fill-slate-800" width={12} height={6} />
    </TooltipPrimitive.Content>
  </TooltipPrimitive.Portal>
))
TooltipContent.displayName = TooltipPrimitive.Content.displayName

// Simple Tooltip Wrapper Component for easy use
const SimpleTooltip = ({ children, content, side = "top", delayDuration = 300, ...props }) => {
  if (!content) return children;
  
  return (
    <TooltipProvider delayDuration={delayDuration}>
      <Tooltip>
        <TooltipTrigger asChild>
          {children}
        </TooltipTrigger>
        <TooltipContent side={side} {...props}>
          {content}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider, TooltipArrow, SimpleTooltip }
