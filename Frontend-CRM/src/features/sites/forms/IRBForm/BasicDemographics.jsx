import React, { useMemo } from 'react'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

import {
  accreditationBodies,
  countries,
  iecTypes,
  irbTypes,
  irbStatuses,
  organizationTypes,
} from './formFields'
import { FormField, FORM_GRID, HelpText, SectionShell, IRB_FIELD_INPUT, IRB_FIELD_SELECT } from './SectionShell'

const BasicDemographics = ({ form }) => {
  const {
    register,
    setValue,
    watch,
    formState: { errors },
  } = form

  const orgType = watch('basic.organizationType')
  const selectedIrbType = watch('basic.irbType')
  const selectedIecType = watch('basic.iecType')
  const accreditationBody = watch('basic.accreditationBody')
  const irbStatus = watch('basic.irbStatus')
  const country = watch('basic.country')

  const required = useMemo(
    () => ({
      organizationType: true,
      registrationId: true,
      irbStatus: true,
      country: true,
    }),
    []
  )

  return (
    <SectionShell
      title="Basic Demographics"
      description="Organization identity, status, and accreditation details."
    >
      <div className={FORM_GRID}>
        <FormField
          label="Organization Type"
          required={required.organizationType}
          error={errors?.basic?.organizationType?.message}
        >
          <Select
            value={orgType || ''}
            onValueChange={(v) => {
              setValue('basic.organizationType', v, { shouldValidate: true, shouldDirty: true })
              setValue('basic.irbType', '', { shouldValidate: true, shouldDirty: true })
              setValue('basic.iecType', '', { shouldValidate: true, shouldDirty: true })
              setValue('basic.irbName', '', { shouldValidate: true, shouldDirty: true })
              setValue('basic.iecName', '', { shouldValidate: true, shouldDirty: true })
            }}
          >
            <SelectTrigger className={IRB_FIELD_SELECT}>
              <SelectValue placeholder="Select type" />
            </SelectTrigger>
            <SelectContent>
              {organizationTypes.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <input type="hidden" {...register('basic.organizationType', { required: 'Organization Type is required' })} />
        </FormField>

        {orgType === 'IRB' && (
          <FormField label="IRB Name" required error={errors?.basic?.irbName?.message} className="transition-all duration-200">
            <Input
              className={IRB_FIELD_INPUT}
              placeholder="e.g., Central IRB / Review Board"
              {...register('basic.irbName', {
                validate: (value) => {
                  if (orgType === 'IRB') {
                    const v = String(value || '').trim()
                    return v ? true : 'IRB Name is required'
                  }
                  return true
                },
              })}
            />
          </FormField>
        )}

        {orgType === 'IEC' && (
          <FormField label="IEC Name" required error={errors?.basic?.iecName?.message} className="transition-all duration-200">
            <Input
              className={IRB_FIELD_INPUT}
              placeholder="e.g., Local IEC / Ethics Committee"
              {...register('basic.iecName', {
                validate: (value) => {
                  if (orgType === 'IEC') {
                    const v = String(value || '').trim()
                    return v ? true : 'IEC Name is required'
                  }
                  return true
                },
              })}
            />
          </FormField>
        )}

        {orgType === 'IRB' && (
          <FormField label="IRB Type" required error={errors?.basic?.irbType?.message} className="transition-all duration-200">
            <Select
              value={selectedIrbType || ''}
              onValueChange={(v) => setValue('basic.irbType', v, { shouldValidate: true, shouldDirty: true })}
              disabled={!orgType}
            >
              <SelectTrigger className={IRB_FIELD_SELECT}>
                <SelectValue placeholder="Select IRB Type" />
              </SelectTrigger>
              <SelectContent>
                {irbTypes.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <input
              type="hidden"
              {...register('basic.irbType', {
                validate: (value) => {
                  if (orgType !== 'IRB') return true
                  if (!value) return 'IRB Type is required'
                  return irbTypes.some((o) => o.value === value) || 'Select a valid IRB Type'
                },
              })}
            />
          </FormField>
        )}

        {orgType === 'IEC' && (
          <FormField label="IEC Type" required error={errors?.basic?.iecType?.message} className="transition-all duration-200">
            <Select
              value={selectedIecType || ''}
              onValueChange={(v) => setValue('basic.iecType', v, { shouldValidate: true, shouldDirty: true })}
              disabled={!orgType}
            >
              <SelectTrigger className={IRB_FIELD_SELECT}>
                <SelectValue placeholder="Select IEC Type" />
              </SelectTrigger>
              <SelectContent>
                {iecTypes.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <input
              type="hidden"
              {...register('basic.iecType', {
                validate: (value) => {
                  if (orgType !== 'IEC') return true
                  if (!value) return 'IEC Type is required'
                  return iecTypes.some((o) => o.value === value) || 'Select a valid IEC Type'
                },
              })}
            />
          </FormField>
        )}

        <FormField
          label="Registration ID / IORG"
          required={required.registrationId}
          error={errors?.basic?.registrationId?.message}
          help="Use your official IRB/IEC registration identifier (if applicable)."
        >
          <Input
            className={IRB_FIELD_INPUT}
            placeholder="e.g., IORG0001234"
            {...register('basic.registrationId', { required: 'Registration ID is required' })}
          />
        </FormField>

        <FormField label="FWA / Assurance No.">
          <Input
            className={IRB_FIELD_INPUT}
            placeholder="e.g., FWA00001234"
            {...register('basic.fwaNumber')}
          />
        </FormField>

        <FormField label="OHRP Registration No.">
          <Input className={IRB_FIELD_INPUT} {...register('basic.ohrpRegistrationNumber')} />
        </FormField>

        <FormField label="Accreditation Body" required error={errors?.basic?.accreditationBody?.message}>
          <Select
            value={accreditationBody || ''}
            onValueChange={(v) => {
              setValue('basic.accreditationBody', v, { shouldDirty: true, shouldValidate: true })
              if (v === 'None/N/A') {
                setValue('basic.accreditationNumber', '', { shouldDirty: true, shouldValidate: true })
                setValue('basic.accreditationExpiry', '', { shouldDirty: true, shouldValidate: true })
              }
            }}
          >
            <SelectTrigger className={IRB_FIELD_SELECT}>
              <SelectValue placeholder="Select body" />
            </SelectTrigger>
            <SelectContent>
              {accreditationBodies.map((a) => (
                <SelectItem key={a.value} value={a.value}>
                  {a.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <input
            type="hidden"
            {...register('basic.accreditationBody', {
              required: 'Accreditation body is required',
              validate: (v) =>
                !v ||
                accreditationBodies.some((a) => a.value === v) ||
                'Select a supported accreditation body',
            })}
          />
        </FormField>

        {accreditationBody !== 'None/N/A' && (
          <FormField
            label="Accreditation No."
            required
            error={errors?.basic?.accreditationNumber?.message}
            className="transition-all duration-200"
          >
            <Input
              className={IRB_FIELD_INPUT}
              {...register('basic.accreditationNumber', {
                validate: (v) => {
                  if (accreditationBody === 'None/N/A') return true
                  return String(v || '').trim() !== '' || 'Accreditation number is required'
                },
              })}
            />
          </FormField>
        )}

        {accreditationBody !== 'None/N/A' && (
          <FormField
            label="Accreditation Expiry"
            required
            error={errors?.basic?.accreditationExpiry?.message}
            className="transition-all duration-200"
          >
            <Input
              type="date"
              className={IRB_FIELD_INPUT}
              {...register('basic.accreditationExpiry', {
                validate: (v) => {
                  if (accreditationBody === 'None/N/A') return true
                  return String(v || '').trim() !== '' || 'Accreditation expiry is required'
                },
              })}
            />
          </FormField>
        )}

        <FormField
          label="IRB / EC Status"
          required={required.irbStatus}
          error={errors?.basic?.irbStatus?.message}
        >
          <Select
            value={irbStatus || ''}
            onValueChange={(v) => setValue('basic.irbStatus', v, { shouldValidate: true, shouldDirty: true })}
          >
            <SelectTrigger className={IRB_FIELD_SELECT}>
              <SelectValue placeholder="Select status" />
            </SelectTrigger>
            <SelectContent>
              {irbStatuses.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <input type="hidden" {...register('basic.irbStatus', { required: 'Status is required' })} />
        </FormField>

        <FormField label="Date Established">
          <Input type="date" className={IRB_FIELD_INPUT} {...register('basic.dateEstablished')} />
        </FormField>

        <FormField
          label="Jurisdiction / Country"
          required={required.country}
          error={errors?.basic?.country?.message}
        >
          <Select
            value={country || ''}
            onValueChange={(v) => setValue('basic.country', v, { shouldValidate: true, shouldDirty: true })}
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
          <input type="hidden" {...register('basic.country', { required: 'Country is required' })} />
        </FormField>
      </div>
    </SectionShell>
  )
}

export default BasicDemographics
