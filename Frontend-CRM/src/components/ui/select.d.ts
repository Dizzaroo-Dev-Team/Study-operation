import * as React from 'react'

export interface SelectProps {
  value?: string
  defaultValue?: string
  onValueChange?: (value: string) => void
  disabled?: boolean
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children?: React.ReactNode
}

export declare const Select: React.FC<SelectProps>
export declare const SelectGroup: React.FC<React.HTMLAttributes<HTMLDivElement>>
export declare const SelectValue: React.FC<{ placeholder?: string; className?: string }>

export declare const SelectTrigger: React.ForwardRefExoticComponent<
  React.ButtonHTMLAttributes<HTMLButtonElement> & React.RefAttributes<HTMLButtonElement>
>
export declare const SelectContent: React.ForwardRefExoticComponent<
  React.HTMLAttributes<HTMLDivElement> & {
    position?: 'item-aligned' | 'popper'
  } & React.RefAttributes<HTMLDivElement>
>
export declare const SelectItem: React.ForwardRefExoticComponent<
  React.HTMLAttributes<HTMLDivElement> & {
    value: string
    disabled?: boolean
  } & React.RefAttributes<HTMLDivElement>
>
export declare const SelectLabel: React.ForwardRefExoticComponent<
  React.HTMLAttributes<HTMLDivElement> & React.RefAttributes<HTMLDivElement>
>
export declare const SelectSeparator: React.ForwardRefExoticComponent<
  React.HTMLAttributes<HTMLDivElement> & React.RefAttributes<HTMLDivElement>
>
