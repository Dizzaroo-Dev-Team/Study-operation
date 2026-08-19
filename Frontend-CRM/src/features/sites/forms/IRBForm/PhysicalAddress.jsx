import React from 'react'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

import { countries, timeZones } from './formFields'
import { FormField, FORM_GRID, SectionShell, IRB_FIELD_INPUT, IRB_FIELD_SELECT } from './SectionShell'

const PhysicalAddress = ({ form }) => {
  const {
    register,
    setValue,
    watch,
    formState: { errors },
  } = form

  const country = watch('address.country')
  const tz = watch('address.timeZone')

  return (
    <SectionShell title="Physical Address" description="Administrative office address and office hours.">
      <div className={FORM_GRID}>
        <FormField label="Address Line 1" required error={errors?.address?.line1?.message}>
          <Input
            className={IRB_FIELD_INPUT}
            {...register('address.line1', { required: 'Address Line 1 is required' })}
          />
        </FormField>
        <FormField label="Address Line 2">
          <Input className={IRB_FIELD_INPUT} {...register('address.line2')} />
        </FormField>
        <FormField label="City" required error={errors?.address?.city?.message}>
          <Input className={IRB_FIELD_INPUT} {...register('address.city', { required: 'City is required' })} />
        </FormField>
        <FormField label="State" required error={errors?.address?.state?.message}>
          <Input
            className={IRB_FIELD_INPUT}
            {...register('address.state', {
              required: 'State is required',
              validate: (v) => String(v || '').trim() !== '' || 'State is required',
            })}
          />
        </FormField>
        <FormField label="Zip Code" required error={errors?.address?.zip?.message}>
          <Input
            className={IRB_FIELD_INPUT}
            {...register('address.zip', {
              required: 'Zip code is required',
              validate: (v) => String(v || '').trim() !== '' || 'Zip code is required',
            })}
          />
        </FormField>
        <FormField label="Country" required error={errors?.address?.country?.message}>
          <Select
            value={country || ''}
            onValueChange={(v) => setValue('address.country', v, { shouldValidate: true, shouldDirty: true })}
          >
            <SelectTrigger className={IRB_FIELD_SELECT}>
              <SelectValue placeholder="Select country" />
            </SelectTrigger>
            <SelectContent>
              {countries.map((c) => (
                <SelectItem key={c.value} value={c.value}>
                  {c.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <input type="hidden" {...register('address.country', { required: 'Country is required' })} />
        </FormField>
        <FormField label="Office Hours">
          <Input className={IRB_FIELD_INPUT} placeholder="e.g., Mon–Fri 9:00–17:00" {...register('address.officeHours')} />
        </FormField>
        <FormField label="Time Zone">
          <Select value={tz || ''} onValueChange={(v) => setValue('address.timeZone', v, { shouldDirty: true })}>
            <SelectTrigger className={IRB_FIELD_SELECT}>
              <SelectValue placeholder="Select time zone" />
            </SelectTrigger>
            <SelectContent>
              {timeZones.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <input type="hidden" {...register('address.timeZone')} />
        </FormField>
      </div>
    </SectionShell>
  )
}

export default PhysicalAddress
