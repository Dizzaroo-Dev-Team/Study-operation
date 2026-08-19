// Type declarations for the untyped toast.jsx (shadcn wrapper around Radix Toast).
import * as React from "react";
import * as ToastPrimitives from "@radix-ui/react-toast";

export declare const ToastProvider: typeof ToastPrimitives.Provider;
export declare const ToastViewport: React.ForwardRefExoticComponent<
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Viewport> &
    React.RefAttributes<React.ElementRef<typeof ToastPrimitives.Viewport>>
>;
export declare const Toast: React.ForwardRefExoticComponent<
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Root> & {
    variant?: "default" | "destructive";
  } & React.RefAttributes<React.ElementRef<typeof ToastPrimitives.Root>>
>;
export declare const ToastAction: React.ForwardRefExoticComponent<
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Action> &
    React.RefAttributes<React.ElementRef<typeof ToastPrimitives.Action>>
>;
export declare const ToastClose: React.ForwardRefExoticComponent<
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Close> &
    React.RefAttributes<React.ElementRef<typeof ToastPrimitives.Close>>
>;
export declare const ToastTitle: React.ForwardRefExoticComponent<
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Title> &
    React.RefAttributes<React.ElementRef<typeof ToastPrimitives.Title>>
>;
export declare const ToastDescription: React.ForwardRefExoticComponent<
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Description> &
    React.RefAttributes<React.ElementRef<typeof ToastPrimitives.Description>>
>;
