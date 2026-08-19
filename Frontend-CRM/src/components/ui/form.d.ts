import * as React from 'react'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export declare const Form: React.FC<any>

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export declare function FormField(props: any): React.JSX.Element

export declare const FormItem: React.ForwardRefExoticComponent<
  React.HTMLAttributes<HTMLDivElement> & React.RefAttributes<HTMLDivElement>
>

export declare const FormLabel: React.ForwardRefExoticComponent<
  React.LabelHTMLAttributes<HTMLLabelElement> & React.RefAttributes<HTMLLabelElement>
>

export declare const FormControl: React.ForwardRefExoticComponent<
  React.HTMLAttributes<HTMLElement> & React.RefAttributes<HTMLElement>
>

export declare const FormDescription: React.ForwardRefExoticComponent<
  React.HTMLAttributes<HTMLParagraphElement> & React.RefAttributes<HTMLParagraphElement>
>

export declare const FormMessage: React.ForwardRefExoticComponent<
  React.HTMLAttributes<HTMLParagraphElement> & React.RefAttributes<HTMLParagraphElement>
>

export declare function useFormField(): {
  id: string
  name: string
  formItemId: string
  formDescriptionId: string
  formMessageId: string
  invalid: boolean
  isDirty: boolean
  isTouched: boolean
  error?: { message?: string }
}
