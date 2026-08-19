import React from 'react'
import { Controller } from 'react-hook-form'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

import { fullBoardMeetingFrequencies } from './formFields'
import { FormField, FORM_GRID, SectionShell, IRB_FIELD_INPUT, IRB_FIELD_SELECT } from './SectionShell'

const MeetingSchedule = ({ form }) => {
  const {
    control,
    register,
    formState: { errors },
  } = form

  return (
    <SectionShell
      title="Meeting Schedule"
      description="Full board cadence, submission timing, and review turnaround expectations."
    >
      <div className={FORM_GRID}>
        <FormField
          label="Full Board Meeting Frequency"
          required
          error={errors?.meetingSchedule?.fullBoardFrequency?.message}
        >
          <Controller
            name="meetingSchedule.fullBoardFrequency"
            control={control}
            rules={{ required: 'Full Board Meeting Frequency is required' }}
            render={({ field }) => (
              <Select
                value={field.value || ''}
                onValueChange={(v) => {
                  field.onChange(v)
                }}
              >
                <SelectTrigger className={IRB_FIELD_SELECT}>
                  <SelectValue placeholder="Select frequency" />
                </SelectTrigger>
                <SelectContent>
                  {fullBoardMeetingFrequencies.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </FormField>

        <FormField label="Usual Meeting Day" error={errors?.meetingSchedule?.usualMeetingDay?.message}>
          <Input
            className={IRB_FIELD_INPUT}
            placeholder="e.g., Third Thursday"
            {...register('meetingSchedule.usualMeetingDay')}
          />
        </FormField>

        <FormField label="Meeting Date" error={errors?.meetingSchedule?.meetingDate?.message}>
          <Input type="date" className={IRB_FIELD_INPUT} {...register('meetingSchedule.meetingDate')} />
        </FormField>

        <FormField
          label="Submission Deadline (days before meeting)"
          error={errors?.meetingSchedule?.submissionDeadline?.message}
        >
          <Input
            className={IRB_FIELD_INPUT}
            placeholder="e.g., 14 calendar days"
            {...register('meetingSchedule.submissionDeadline')}
          />
        </FormField>
      </div>
    </SectionShell>
  )
}

export default MeetingSchedule
