import React from 'react'
import { Controller } from 'react-hook-form'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { DEFAULT_PHONE_COUNTRY, PHONE_COUNTRY_OPTIONS } from './irbPhoneCountryCodes'
import { FormField, FORM_GRID, SectionShell, IRB_FIELD_INPUT, IRB_FIELD_SELECT } from './SectionShell'
import { cn } from '@/lib/utils'

const formatNationalDigits = (raw) => String(raw || '').replace(/\D/g, '').slice(0, 15)

const contactKey = (prefix) => prefix.split('.').pop()

const ContactBlock = ({ prefix, title, form, isPrimary }) => {
  const {
    register,
    setValue,
    watch,
    control,
    formState: { errors },
  } = form

  const ck = contactKey(prefix)
  const baseErrors = errors?.contacts?.[ck] || {}

  const phonePath = `${prefix}.phone`
  const phoneVal = watch(phonePath)

  return (
    <div
      className={cn(
        'rounded-xl border p-4 space-y-2 shadow-sm transition',
        isPrimary
          ? 'border-violet-200/80 bg-gradient-to-br from-violet-50/90 via-white to-white'
          : 'border-slate-200/80 bg-gradient-to-br from-slate-50/80 via-white to-white',
      )}
    >
      <div className="flex items-center gap-2 pb-2 border-b border-slate-200/60">
        <div
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-lg text-xs font-bold',
            isPrimary ? 'bg-violet-100 text-violet-700' : 'bg-slate-100 text-slate-600',
          )}
        >
          {isPrimary ? 'P' : 'S'}
        </div>
        <div className="text-sm font-semibold text-slate-900">{title}</div>
      </div>
      <div className="space-y-2">
        <div className={FORM_GRID}>
          <FormField label="Full Name" required={isPrimary} error={baseErrors?.fullName?.message}>
            <Input
              className={IRB_FIELD_INPUT}
              {...register(`${prefix}.fullName`, isPrimary ? { required: 'Full Name is required' } : {})}
            />
          </FormField>
          <FormField label="Job Title">
            <Input className={IRB_FIELD_INPUT} {...register(`${prefix}.jobTitle`)} />
          </FormField>
        </div>

        <div className="flex flex-col gap-2 md:flex-row md:items-start md:gap-3">
          <FormField label="Email" required={isPrimary} error={baseErrors?.email?.message} className="min-w-0 flex-1">
            <Input
              type="email"
              className={IRB_FIELD_INPUT}
              placeholder="name@org.com"
              {...register(`${prefix}.email`, {
                ...(isPrimary
                  ? {
                      required: 'Email is required',
                      pattern: {
                        value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                        message: 'Invalid email format',
                      },
                    }
                  : {
                      validate: (v) => {
                        const s = String(v || '').trim()
                        if (!s) return true
                        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s) || 'Invalid email format'
                      },
                    }),
              })}
            />
          </FormField>

          <FormField
            label="Country code"
            required={isPrimary}
            error={baseErrors?.phoneCountryCode?.message}
            className="w-full shrink-0 md:w-[7.25rem]"
          >
            <Controller
              name={`${prefix}.phoneCountryCode`}
              control={control}
              rules={
                isPrimary
                  ? {
                      required: 'Country code is required',
                      validate: (v) =>
                        (v && String(v).trim() !== '') || 'Country code is required',
                    }
                  : undefined
              }
              defaultValue={DEFAULT_PHONE_COUNTRY}
              render={({ field }) => {
                const v = field.value || DEFAULT_PHONE_COUNTRY
                const selectedOpt = PHONE_COUNTRY_OPTIONS.find((o) => o.value === v)
                return (
                  <Select value={v} onValueChange={(val) => field.onChange(val)}>
                    <SelectTrigger
                      className={cn(IRB_FIELD_SELECT, 'h-10 px-1.5 text-[11px] leading-tight [&_svg]:h-3 [&_svg]:w-3')}
                      title={selectedOpt?.label}
                    >
                      <SelectValue placeholder="Code" />
                    </SelectTrigger>
                    <SelectContent className="max-h-60 min-w-[min(100vw-2rem,22rem)]">
                      {PHONE_COUNTRY_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value} textValue={opt.label}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )
              }}
            />
          </FormField>

          <FormField label="Phone" required={isPrimary} error={baseErrors?.phone?.message} className="min-w-0 flex-1">
            <Input
              className={IRB_FIELD_INPUT}
              placeholder="National number (digits only)"
              autoComplete="tel-national"
              value={phoneVal || ''}
              onChange={(e) =>
                setValue(phonePath, formatNationalDigits(e.target.value), { shouldDirty: true })
              }
            />
            <input
              type="hidden"
              {...register(phonePath, {
                required: isPrimary ? 'Phone number is required' : false,
                validate: (v) => {
                  const d = String(v || '').replace(/\D/g, '')
                  if (isPrimary) {
                    if (!d) return 'Phone number is required'
                    return d.length >= 7 || 'Enter a valid phone number (at least 7 digits)'
                  }
                  if (!d) return true
                  return d.length >= 7 || 'Enter a valid phone number (at least 7 digits)'
                },
              })}
            />
          </FormField>
        </div>
      </div>
    </div>
  )
}

const ContactPersonnel = ({ form }) => {
  return (
    <SectionShell title="Contact Personnel" description="Primary and alternate administrative contacts.">
      <div className="space-y-2">
        <ContactBlock prefix="contacts.primary" title="Primary Contact" form={form} isPrimary />
        <ContactBlock prefix="contacts.secondary" title="Secondary / Alternate Contact" form={form} isPrimary={false} />
      </div>
    </SectionShell>
  )
}

export default ContactPersonnel
