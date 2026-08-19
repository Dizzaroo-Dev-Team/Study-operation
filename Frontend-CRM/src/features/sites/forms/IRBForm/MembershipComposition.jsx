import React, { useEffect } from 'react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

import { twoDigitNumberPattern } from './formFields'
import { FormField, FORM_GRID, SectionShell, IRB_FIELD_INPUT } from './SectionShell'

const parsePercentInput = (raw) => {
  const s = String(raw ?? '').trim().replace(/%+\s*$/, '')
  if (s === '') return NaN
  const n = Number(s)
  return Number.isFinite(n) ? n : NaN
}

const MembershipComposition = ({ form }) => {
  const {
    register,
    setValue,
    watch,
    formState: { errors },
  } = form

  const quorumRequired = watch('membership.quorumRequired')

  useEffect(() => {
    if (quorumRequired === 'no') {
      setValue('membership.quorumThresholdPercent', '', { shouldDirty: true, shouldValidate: true })
      setValue('membership.quorumMinimumMembersPresent', '', { shouldDirty: true, shouldValidate: true })
    }
  }, [quorumRequired, setValue])

  const quorumReg = register('membership.quorumRequired')
  const { ref: quorumRef, ...quorumRadioRest } = quorumReg

  return (
    <SectionShell title="Membership Composition" description="Leadership names, membership counts, and quorum rules.">
      <div className={FORM_GRID}>
        <FormField label="Chair Name" required error={errors?.membership?.chairName?.message}>
          <Input
            className={IRB_FIELD_INPUT}
            {...register('membership.chairName', { required: 'Chair Name is required' })}
          />
        </FormField>
        <FormField label="Vice-Chair Name">
          <Input className={IRB_FIELD_INPUT} {...register('membership.viceChairName')} />
        </FormField>

        <FormField label="Number of Members" required error={errors?.membership?.numberOfMembers?.message}>
          <Input
            className={IRB_FIELD_INPUT}
            inputMode="numeric"
            placeholder="e.g., 12"
            {...register('membership.numberOfMembers', {
              required: 'Number of Members is required',
              pattern: { value: twoDigitNumberPattern, message: 'Enter a 1–2 digit number' },
            })}
          />
        </FormField>
        <FormField
          label="Number of Alternates"
          help="Optional. Use 0–99."
          error={errors?.membership?.numberOfAlternates?.message}
        >
          <Input
            className={IRB_FIELD_INPUT}
            inputMode="numeric"
            placeholder="e.g., 05"
            {...register('membership.numberOfAlternates', {
              pattern: { value: twoDigitNumberPattern, message: 'Enter a 1–2 digit number' },
            })}
          />
        </FormField>
      </div>

      <div className="mt-8 pt-6 border-t border-slate-200 space-y-4">
        <div>
          <h4 className="text-sm font-semibold text-gray-900">Quorum Requirements</h4>
          <p className="text-xs text-muted-foreground mt-0.5">Indicate whether a voting quorum applies to this committee.</p>
        </div>

        <div className="flex flex-wrap gap-6" role="radiogroup" aria-label="Quorum required">
          <label
            className={cn(
              'flex items-center gap-2 cursor-pointer text-sm text-gray-800',
              quorumRequired === 'yes' && 'font-medium'
            )}
          >
            <input
              type="radio"
              value="yes"
              className="h-4 w-4 border-slate-300 text-[#168AAD] focus:ring-[#168AAD]"
              ref={quorumRef}
              {...quorumRadioRest}
            />
            Yes (Quorum required)
          </label>
          <label
            className={cn(
              'flex items-center gap-2 cursor-pointer text-sm text-gray-800',
              quorumRequired === 'no' && 'font-medium'
            )}
          >
            <input
              type="radio"
              value="no"
              className="h-4 w-4 border-slate-300 text-[#168AAD] focus:ring-[#168AAD]"
              {...quorumRadioRest}
            />
            No
          </label>
        </div>
        {errors?.membership?.quorumRequired?.message ? (
          <p className="text-xs text-rose-600">{errors.membership.quorumRequired.message}</p>
        ) : null}

        {quorumRequired === 'yes' && (
          <div className={cn(FORM_GRID, 'pt-2 animate-in fade-in-0 duration-200')}>
            <FormField
              label="Quorum Threshold (%)"
              required
              help="Numeric only (e.g., 51 for 51%)."
              error={errors?.membership?.quorumThresholdPercent?.message}
            >
              <Input
                className={IRB_FIELD_INPUT}
                inputMode="decimal"
                placeholder="e.g., 51"
                autoComplete="off"
                {...register('membership.quorumThresholdPercent', {
                  validate: (v) => {
                    if (quorumRequired !== 'yes') return true
                    const n = parsePercentInput(v)
                    if (!Number.isFinite(n)) return 'Enter a valid percentage'
                    if (n <= 0 || n > 100) return 'Enter a number greater than 0 and up to 100'
                    return true
                  },
                })}
              />
            </FormField>
            <FormField
              label="Minimum Members Present"
              required
              help="Whole number (minimum members that must be present)."
              error={errors?.membership?.quorumMinimumMembersPresent?.message}
            >
              <Input
                className={IRB_FIELD_INPUT}
                inputMode="numeric"
                placeholder="e.g., 8"
                autoComplete="off"
                {...register('membership.quorumMinimumMembersPresent', {
                  validate: (v) => {
                    if (quorumRequired !== 'yes') return true
                    const s = String(v ?? '').trim()
                    if (!s) return 'Minimum members is required'
                    if (!/^\d+$/.test(s)) return 'Whole numbers only'
                    const n = Number(s)
                    if (n < 1) return 'Enter at least 1'
                    return true
                  },
                })}
              />
            </FormField>
          </div>
        )}
      </div>
    </SectionShell>
  )
}

export default MembershipComposition
