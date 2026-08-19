// Entity registry (extensible). Declares the record types the assistant can find
// (via a guarded search command) and open. Whitelist-only: the resolver picks
// from these types + their registered commands — never arbitrary routes.
//
// `openable: 'record'` = we can open the exact record (real detail route/event).
// `openable: 'screen'` = we resolve the record (scoped to the user) then open its
//   containing screen/tab (honest — per-record detail view not built yet).

export interface EntityDef {
  type: string
  aliases: string[]
  openable: 'record' | 'screen'
  search?: string // registered search command (backend); required to resolve by name
  create?: string // registered create command, if any
  // How to open, given a resolved id (handled by AssistantWidget.openEntity):
  open: { url?: (id: string) => string; screen?: string; event?: string; select?: 'study' | 'site' }
}

export const ENTITIES: EntityDef[] = [
  {
    type: 'template',
    aliases: ['template', 'clause template', 'agreement template', 'document template'],
    openable: 'record',
    search: 'list_study_templates',
    open: { url: (id) => `/templates/${id}/builder` },
  },
  {
    type: 'conversation',
    aliases: ['conversation', 'thread', 'message thread'],
    openable: 'record',
    search: 'list_my_conversations',
    create: 'create_conversation',
    open: { event: 'crm:select-conversation', screen: 'conversations' },
  },
  {
    type: 'agreement',
    aliases: ['agreement', 'cta', 'cda', 'contract'],
    openable: 'screen',
    search: 'list_site_agreements',
    open: { screen: 'agreements' }, // Study Setup → Agreements tab
  },
  {
    type: 'task',
    aliases: ['task', 'action item', 'to-do'],
    openable: 'record',
    search: 'list_my_tasks',
    create: 'create_task',
    // TasksTab listens for this event and opens the task's detail (edit modal).
    open: { event: 'crm:select-task', screen: 'tasks' },
  },
  {
    type: 'study',
    aliases: ['study', 'trial'],
    openable: 'screen',
    search: 'list_studies',
    open: { screen: 'dashboard', select: 'study' },
  },
  {
    type: 'site',
    aliases: ['site', 'hospital', 'clinic'],
    openable: 'screen',
    search: 'list_study_sites',
    open: { screen: 'site_profile', select: 'site' },
  },
]

export function getEntity(type: string): EntityDef | undefined {
  return ENTITIES.find((e) => e.type === type)
}

/** Compact catalog sent to the backend to drive open_entity + the resolver. */
export function entitiesForBackend(): {
  type: string
  aliases: string[]
  openable: string
  search?: string
  create?: string
}[] {
  return ENTITIES.map(({ type, aliases, openable, search, create }) => ({
    type,
    aliases,
    openable,
    search,
    create,
  }))
}
