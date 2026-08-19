import * as React from "react"
import { Controller, FormProvider, useFormContext } from "react-hook-form"

const Form = FormProvider

const FormField = ({ ...props }) => {
  return <Controller {...props} />
}

const FormItem = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} className={className} {...props} />
))
FormItem.displayName = "FormItem"

const FormLabel = React.forwardRef(({ className, ...props }, ref) => (
  <label ref={ref} className={className} {...props} />
))
FormLabel.displayName = "FormLabel"

const FormControl = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} className={className} {...props} />
))
FormControl.displayName = "FormControl"

const FormDescription = React.forwardRef(({ className, ...props }, ref) => (
  <p ref={ref} className={className} {...props} />
))
FormDescription.displayName = "FormDescription"

const FormMessage = React.forwardRef(({ className, ...props }, ref) => (
  <p ref={ref} className={className} {...props} />
))
FormMessage.displayName = "FormMessage"

function useFormField() {
  const ctx = useFormContext()
  return { form: ctx }
}

export {
  useFormField,
  Form,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
  FormField,
}

