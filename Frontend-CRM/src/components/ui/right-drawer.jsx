import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { Button } from './button';
import { cn } from '@/lib/utils';

const RightDrawer = ({ 
  isOpen, 
  onClose, 
  title, 
  subtitle,
  children, 
  className = "",
  size = "lg" // sm, md, lg, xl, full
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const [isAnimating, setIsAnimating] = useState(false);

  const sizeClasses = {
    sm: "w-96",
    md: "w-[500px]",
    lg: "w-[650px]",
    xl: "w-[800px]",
    full: "w-full max-w-6xl"
  };

  useEffect(() => {
    console.log('🎨 RightDrawer useEffect - isOpen changed:', {
      isOpen,
      isVisible,
      isAnimating,
      stackTrace: new Error().stack
    });
    
    if (isOpen) {
      console.log('✅ RightDrawer opening...');
      setIsVisible(true);
      // Small delay to trigger animation
      setTimeout(() => {
        console.log('🎬 RightDrawer animation starting');
        setIsAnimating(true);
      }, 10);
      // Prevent body scroll when drawer is open
      document.body.style.overflow = 'hidden';
    } else {
      console.log('❌ RightDrawer closing...');
      setIsAnimating(false);
      const timer = setTimeout(() => {
        console.log('🚪 RightDrawer fully closed, setting isVisible to false');
        setIsVisible(false);
        // Restore body scroll when drawer is closed
        document.body.style.overflow = 'unset';
      }, 300); // Match transition duration
      return () => {
        console.log('🧹 RightDrawer cleanup - clearing timer');
        clearTimeout(timer);
      };
    }
    
    return () => {
      console.log('🧹 RightDrawer cleanup - restoring body scroll');
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  // Don't render if not visible
  if (!isVisible) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div 
        className={cn(
          "absolute inset-0 bg-slate-900/45 backdrop-blur-sm transition-all duration-300 ease-in-out",
          isAnimating ? "opacity-100" : "opacity-0"
        )}
        onClick={(e) => {
          console.log('🖱️ RightDrawer backdrop clicked:', {
            stackTrace: new Error().stack
          });
          onClose();
        }}
      />
      
      {/* Drawer */}
      <div className="absolute right-0 top-0 h-full flex">
        <div 
          className={cn(
            "relative h-full bg-white/95 backdrop-blur-md border-l border-slate-200 shadow-[0_20px_50px_rgba(15,23,42,0.16)] transform transition-all duration-300 ease-out flex flex-col",
            sizeClasses[size],
            className,
            isAnimating ? "translate-x-0" : "translate-x-full"
          )}
        >
          {/* Professional Header */}
          <div className="flex-none border-b bg-white/90 backdrop-blur-sm">
            <div className="h-1 w-full bg-gradient-to-r from-[hsl(var(--dz-primary))] via-[hsl(var(--dz-secondary))] to-[hsl(var(--dz-success))]" />
            <div className="flex items-center justify-between px-6 py-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground tracking-tight">{title}</h2>
                {subtitle && (
                  <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
                )}
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={(e) => {
                  console.log('❌ RightDrawer close button clicked:', {
                    stackTrace: new Error().stack
                  });
                  onClose();
                }}
                className="h-8 w-8 hover:bg-muted transition-colors"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          
          {/* Content - Scrollable */}
          <div className="flex-1 overflow-y-auto">
            <div className="px-6 py-5">
              {children}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RightDrawer;
