/**
 * Read-only custom template fields at the same anchor positions as VisitReportLegacyTab.
 */
import type { MvrFieldDef } from '@/components/mon/types/mvrTemplate'
import { MvrDynamicReviewReportBody } from './MvrDynamicReviewReportBody'

const INSERTED_TEMPLATE_STUB = {
  id: 'review-inserted-fields',
  name: '',
  version: 0,
  schema: { fields: [] as MvrFieldDef[] },
}

function isFullWidthField(field: MvrFieldDef): boolean {
  return field.type === 'section' || field.type === 'table' || field.type === 'textarea' || field.type === 'multiselect'
}

function insertedFieldsTemplate(fields: MvrFieldDef[]) {
  return { ...INSERTED_TEMPLATE_STUB, schema: { fields } }
}

export function MvrLegacyInsertedFieldsReview({
  fields,
  submissionData,
  changedFieldKeys,
  placement = 'block',
}: {
  fields: MvrFieldDef[]
  submissionData: Record<string, unknown>
  changedFieldKeys?: Set<string>
  /** block = stacked above/below grid rows; grid = cells inside parent grid */
  placement?: 'block' | 'grid'
}) {
  if (!fields.length) return null

  if (placement === 'block') {
    return (
      <div style={{ marginBottom: 14 }}>
        <MvrDynamicReviewReportBody
          template={insertedFieldsTemplate(fields)}
          submissionData={submissionData}
          changedFieldKeys={changedFieldKeys}
        />
      </div>
    )
  }

  return (
    <>
      {fields.map((field) => (
        <div
          key={field.id}
          style={{ gridColumn: isFullWidthField(field) ? '1 / -1' : undefined }}
        >
          <MvrDynamicReviewReportBody
            layout="inline"
            template={insertedFieldsTemplate([field])}
            submissionData={submissionData}
            changedFieldKeys={changedFieldKeys}
          />
        </div>
      ))}
    </>
  )
}
