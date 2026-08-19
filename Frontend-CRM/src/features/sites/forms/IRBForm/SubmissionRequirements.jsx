import React, { useEffect } from 'react'
import { Controller } from 'react-hook-form'

import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

import {
  SUBMISSION_METHOD_HARD_COPY,
  paymentMethods,
  submissionFeeCurrencies,
  submissionMethods,
  submissionTypes,
} from './formFields'
import { FormField, FORM_GRID, SectionShell, IRB_FIELD_INPUT, IRB_FIELD_SELECT } from './SectionShell'
import { cn } from '@/lib/utils'

const SubmissionRequirements = ({ form }) => {
  const {
    control,
    setValue,
    register,
    getValues,
    watch,
    formState: { errors },
  } = form

  const submissionMethod = watch('submissionRequirements.submissionMethod')
  const isHardCopy = submissionMethod === SUBMISSION_METHOD_HARD_COPY

  useEffect(() => {
    if (!isHardCopy) {
      setValue('submissionRequirements.numberOfCopiesRequired', '', {
        shouldDirty: true,
        shouldValidate: true,
      })
    }
  }, [isHardCopy, setValue])

  const feeCurrencyError = errors?.submissionRequirements?.submissionFeeCurrency?.message
  const feeAmountError = errors?.submissionRequirements?.submissionFeeAmount?.message
  const feeError = feeCurrencyError || feeAmountError

  return (
    <SectionShell
      title="Submission Requirements"
      description="Classify the submission, how it is filed, fees, and payment options."
    >
      <div className={FORM_GRID}>
        <FormField
          label="Submission Type"
          required
          error={errors?.submissionRequirements?.submissionType?.message}
        >
          <Controller
            name="submissionRequirements.submissionType"
            control={control}
            rules={{ required: 'Submission type is required' }}
            render={({ field }) => (
              <Select
                value={field.value || ''}
                onValueChange={(v) => {
                  field.onChange(v)
                }}
              >
                <SelectTrigger className={IRB_FIELD_SELECT}>
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  {submissionTypes.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </FormField>

        <FormField label="Submission Date" error={errors?.submissionRequirements?.submissionDate?.message}>
          <Input
            type="date"
            className={IRB_FIELD_INPUT}
            {...register('submissionRequirements.submissionDate')}
          />
        </FormField>

        <FormField
          label="Submission Method"
          required
          error={errors?.submissionRequirements?.submissionMethod?.message}
          className={!isHardCopy ? 'md:col-span-2 max-w-xl' : undefined}
        >
          <Controller
            name="submissionRequirements.submissionMethod"
            control={control}
            rules={{ required: 'Submission method is required' }}
            render={({ field }) => (
              <Select
                value={field.value || ''}
                onValueChange={(v) => {
                  field.onChange(v)
                }}
              >
                <SelectTrigger className={IRB_FIELD_SELECT}>
                  <SelectValue placeholder="Select method" />
                </SelectTrigger>
                <SelectContent>
                  {submissionMethods.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </FormField>

        {isHardCopy ? (
          <FormField
            label="Number of Copies Required"
            required
            error={errors?.submissionRequirements?.numberOfCopiesRequired?.message}
          >
            <Input
              className={IRB_FIELD_INPUT}
              inputMode="numeric"
              min={1}
              step={1}
              placeholder="e.g., 3"
              {...register('submissionRequirements.numberOfCopiesRequired', {
                validate: (v) => {
                  if (getValues('submissionRequirements.submissionMethod') !== SUBMISSION_METHOD_HARD_COPY) return true
                  const n = parseInt(String(v ?? '').trim(), 10)
                  if (!Number.isFinite(n) || n < 1) return 'Enter a whole number of at least 1'
                  return true
                },
              })}
            />
          </FormField>
        ) : null}

        <div className="md:col-span-2">
          <div className={FORM_GRID}>
            <FormField label="Submission Fee" required error={feeError}>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
                <Controller
                  name="submissionRequirements.submissionFeeCurrency"
                  control={control}
                  rules={{ required: 'Currency is required' }}
                  render={({ field }) => (
                    <Select value={field.value || ''} onValueChange={(v) => field.onChange(v)}>
                      <SelectTrigger className={cn(IRB_FIELD_SELECT, 'w-full sm:w-[7.5rem] shrink-0')}>
                        <SelectValue placeholder="Currency" />
                      </SelectTrigger>
                      <SelectContent>
                        {submissionFeeCurrencies.map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
                <Input
                  className={cn(IRB_FIELD_INPUT, 'min-w-0 sm:flex-1')}
                  inputMode="decimal"
                  placeholder="Amount (e.g., 250.00)"
                  {...register('submissionRequirements.submissionFeeAmount', {
                    required: 'Amount is required',
                    validate: (v) => {
                      const s = String(v ?? '').trim()
                      if (s === '') return 'Amount is required'
                      const n = Number(String(s).replace(/,/g, ''))
                      if (!Number.isFinite(n) || n < 0) {
                        return 'Enter a valid amount (0 or greater)'
                      }
                      return true
                    },
                  })}
                />
              </div>
            </FormField>

            <FormField
              label="Payment Method"
              required
              error={errors?.submissionRequirements?.paymentMethod?.message}
            >
              <Controller
                name="submissionRequirements.paymentMethod"
                control={control}
                rules={{ required: 'Payment method is required' }}
                render={({ field }) => (
                  <Select value={field.value || ''} onValueChange={(v) => field.onChange(v)}>
                    <SelectTrigger className={IRB_FIELD_SELECT}>
                      <SelectValue placeholder="Select payment method" />
                    </SelectTrigger>
                    <SelectContent>
                      {paymentMethods.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </FormField>
          </div>
        </div>
      </div>
    </SectionShell>
  )
}

export default SubmissionRequirements
