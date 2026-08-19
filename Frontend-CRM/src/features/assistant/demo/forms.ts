// Fillable-forms registry (extensible, whitelist-only). Orbit may POPULATE a
// registered form's fields on request — it NEVER submits/saves/signs (sacred
// rule 2: the user's own click submits, through the guarded/confirmed/audited
// route). Expansion is form-by-form and test-id-bound.
//
// `data-testid`s live HERE (frontend), the single source of truth. The backend
// only ever sends {form, [{key, value}]}; the frontend resolves key -> testid and
// fills the real on-screen field. Unknown form/field ids are silently ignored.

export type FillFieldType = 'text' | 'textarea' | 'date' | 'select'

export interface FillableField {
  key: string           // stable key the model uses
  label: string         // human label (sent to the model so it maps intent -> field)
  testid: string        // the field's data-testid on screen (never leaves the frontend)
  type: FillFieldType
}

export interface FillableForm {
  id: string
  label: string
  aliases: string[]
  formTestid: string    // the form container's data-testid (presence check)
  submitLabel: string   // what the user clicks themselves to submit
  fields: FillableField[]
}

export const FORMS: FillableForm[] = [
  {
    id: 'task',
    label: 'New Task',
    aliases: ['task', 'new task', 'add task', 'to-do', 'todo', 'action item'],
    formTestid: 'task-create-form',
    submitLabel: 'Create Task',
    fields: [
      { key: 'description', label: 'Task description (what needs doing)', testid: 'task-field-description', type: 'textarea' },
      { key: 'requested_by', label: 'Requested by (person name)', testid: 'task-field-requested-by', type: 'text' },
      { key: 'due_date', label: 'Due date (YYYY-MM-DD)', testid: 'task-field-due-date', type: 'date' },
    ],
  },
  {
    id: 'conversation',
    label: 'New Conversation',
    aliases: ['conversation', 'new conversation', 'create conversation', 'thread', 'new thread'],
    formTestid: 'conversation-create-form',
    submitLabel: 'Create',
    fields: [
      { key: 'subject', label: 'Conversation subject / topic', testid: 'conversation-field-subject', type: 'text' },
    ],
  },
]

export function getForm(id: string): FillableForm | undefined {
  return FORMS.find((f) => f.id === id)
}

/** Compact list sent to the backend per turn so fill_form's allowed forms/fields
 *  stay in sync. Deliberately omits the data-testids (frontend-only). */
export function formsForBackend(): {
  id: string
  label: string
  aliases: string[]
  submit_label: string
  fields: { key: string; label: string; type: string }[]
}[] {
  return FORMS.map(({ id, label, aliases, submitLabel, fields }) => ({
    id,
    label,
    aliases,
    submit_label: submitLabel,
    fields: fields.map(({ key, label, type }) => ({ key, label, type })),
  }))
}
