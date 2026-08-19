// Type declarations for the untyped tabs.jsx (shadcn wrapper around Radix Tabs).
import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";

export declare const Tabs: typeof TabsPrimitive.Root;
export declare const TabsList: React.ForwardRefExoticComponent<
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List> &
    React.RefAttributes<React.ElementRef<typeof TabsPrimitive.List>>
>;
export declare const TabsTrigger: React.ForwardRefExoticComponent<
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger> &
    React.RefAttributes<React.ElementRef<typeof TabsPrimitive.Trigger>>
>;
export declare const TabsContent: React.ForwardRefExoticComponent<
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content> &
    React.RefAttributes<React.ElementRef<typeof TabsPrimitive.Content>>
>;
