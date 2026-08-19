import React from 'react'
import { Controller } from 'react-hook-form'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

import { bankingCurrencies } from './formFields'
import { FormField, FORM_GRID, SectionShell, IRB_FIELD_INPUT, IRB_FIELD_SELECT } from './SectionShell'

const BankingFeePaymentDetails = ({ form }) => {
  const {
    control,
    register,
    formState: { errors },
  } = form

  return (
    <SectionShell
      title="Banking & Fee Payment Details"
      description="Wire transfer and invoicing details for fees, when applicable."
    >
      <div className={FORM_GRID}>
        <FormField label="Bank Name" required error={errors?.bankingFeePayment?.bankName?.message}>
          <Input
            className={IRB_FIELD_INPUT}
            autoComplete="off"
            {...register('bankingFeePayment.bankName', {
              required: 'Bank name is required',
              validate: (v) => String(v || '').trim() !== '' || 'Bank name is required',
            })}
          />
        </FormField>
        <FormField label="Account Name" required error={errors?.bankingFeePayment?.accountName?.message}>
          <Input
            className={IRB_FIELD_INPUT}
            autoComplete="off"
            {...register('bankingFeePayment.accountName', {
              required: 'Account name is required',
              validate: (v) => String(v || '').trim() !== '' || 'Account name is required',
            })}
          />
        </FormField>

        <FormField label="Account Number" required error={errors?.bankingFeePayment?.accountNumber?.message}>
          <Input
            className={IRB_FIELD_INPUT}
            autoComplete="off"
            inputMode="text"
            {...register('bankingFeePayment.accountNumber', {
              required: 'Account number is required',
              validate: (v) => String(v || '').trim() !== '' || 'Account number is required',
            })}
          />
        </FormField>
        <FormField label="Routing / SWIFT Code" error={errors?.bankingFeePayment?.routingSwift?.message}>
          <Input
            className={IRB_FIELD_INPUT}
            placeholder="Routing or SWIFT/BIC"
            autoComplete="off"
            {...register('bankingFeePayment.routingSwift')}
          />
        </FormField>

        <FormField label="IBAN (if applicable)" error={errors?.bankingFeePayment?.iban?.message}>
          <Input
            className={IRB_FIELD_INPUT}
            placeholder="e.g., GB82 WEST 1234 5698 7654 32"
            autoComplete="off"
            {...register('bankingFeePayment.iban')}
          />
        </FormField>
        <FormField label="Currency" required error={errors?.bankingFeePayment?.currency?.message}>
          <Controller
            name="bankingFeePayment.currency"
            control={control}
            rules={{
              required: 'Currency is required',
              validate: (v) =>
                !v ||
                bankingCurrencies.some((o) => o.value === v) ||
                'Select a supported currency',
            }}
            render={({ field }) => (
              <Select value={field.value || ''} onValueChange={field.onChange}>
                <SelectTrigger className={IRB_FIELD_SELECT}>
                  <SelectValue placeholder="Select currency" />
                </SelectTrigger>
                <SelectContent>
                  {bankingCurrencies.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </FormField>

        <FormField
          label="Invoice Address (if different)"
          error={errors?.bankingFeePayment?.invoiceAddress?.message}
          className="md:col-span-2"
        >
          <Input
            className={IRB_FIELD_INPUT}
            placeholder="Enter alternate billing / invoice address"
            {...register('bankingFeePayment.invoiceAddress')}
          />
        </FormField>
      </div>
    </SectionShell>
  )
}

export default BankingFeePaymentDetails
