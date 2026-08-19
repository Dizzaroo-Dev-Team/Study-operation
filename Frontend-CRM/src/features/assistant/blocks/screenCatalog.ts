// Auto-derived catalog of navigable screens.
//
// The app is a hybrid: most screens are NOT React Router routes — they're a
// `Mode` routed inside UnifiedInbox, or a tab inside Study Setup. So a router-only
// enumeration would be incomplete (that's how "agreements" was missed). Instead we
// derive the catalog from the app's own declared sources:
//   - the mode screens (Navbar/Sidebar/UnifiedInbox modes),
//   - the Study Setup tabs (imported — adding a tab auto-appears here),
//   - routed pages worth opening.
// Each entry declares the context it needs so the resolver can fill it.

import { tabs as STUDY_SETUP_TABS } from '@/features/study-setup/StudySetup'

export type ScreenRequires = 'none' | 'study' | 'study_site'

export interface ScreenEntry {
  name: string // stable token the model selects
  aliases: string[]
  requires: ScreenRequires
  // `subtab` deep-links a sub-view inside a tab (e.g. Clause Library inside the
  // Template Library tab) — activated after navigating to the parent tab.
  target: { mode?: string; tab?: string; subtab?: string; path?: string }
}

// Mode screens (the UnifiedInbox mode-router surface).
const MODE_SCREENS: ScreenEntry[] = [
  { name: 'dashboard', aliases: ['home', 'overview', 'study dashboard', 'studies'], requires: 'none', target: { mode: 'dashboard' } },
  { name: 'tasks', aliases: ['my tasks', 'to-dos', 'action items'], requires: 'none', target: { mode: 'tasks' } },
  { name: 'conversations', aliases: ['inbox', 'messages'], requires: 'none', target: { mode: 'conversations' } },
  { name: 'threads', aliases: [], requires: 'none', target: { mode: 'threads' } },
  { name: 'study_setup', aliases: ['study configuration'], requires: 'study', target: { mode: 'study-setup' } },
  { name: 'site_profile', aliases: ['site details'], requires: 'study_site', target: { mode: 'site-profile' } },
  { name: 'site_status', aliases: ['site readiness'], requires: 'study_site', target: { mode: 'site-status' } },
  { name: 'site_staff', aliases: ['site staff details', 'site team'], requires: 'study_site', target: { mode: 'site-staff-details' } },
  { name: 'irb_administrative_info', aliases: ['irb', 'irb info', 'ethics'], requires: 'study_site', target: { mode: 'irb-administrative-info' } },
  { name: 'logistics', aliases: ['site logistics'], requires: 'study_site', target: { mode: 'logistics' } },
  { name: 'monitoring', aliases: ['monitoring visits', 'mvr'], requires: 'study_site', target: { mode: 'monitoring' } },
  { name: 'documents', aliases: ['isf', 'investigator site file', 'site file', 'site documents'], requires: 'study_site', target: { mode: 'documents' } },
]

// Declared SUB-VIEW destinations (sub-tabs inside a tab). Tabs aren't routes and
// sub-tabs are hard-coded per component, so these finite, known destinations are
// declared here (parent mode + tab + subtab). Routes stay auto-derived.
const SUBTAB_SCREENS: ScreenEntry[] = [
  {
    name: 'clause_library',
    aliases: ['clause library', 'clauses', 'clause', 'clause templates'],
    requires: 'study',
    target: { mode: 'study-setup', tab: 'template-library', subtab: 'clauses' },
  },
]

// Routed pages worth opening directly.
const ROUTED_SCREENS: ScreenEntry[] = [
  { name: 'workflow_tasks', aliases: ['workflow inbox', 'my workflow steps'], requires: 'none', target: { path: '/workflows/inbox' } },
]

// Aliases for specific Study Setup tabs (fallback = the tab label).
const TAB_ALIASES: Record<string, string[]> = {
  'study-details': ['study details'],
  'site-setup': ['site setup', 'add site', 'manage sites'],
  'study-team': ['study team', 'users', 'team'],
  'template-library': ['template library', 'templates'],
  'agreements': ['agreements', 'contracts', 'cda', 'cta'],
  'budget': ['budget', 'budgeting', 'budget builder', 'site budget'],
  'mvr-template': ['mvr template', 'monitoring template'],
}

// Study Setup tabs — derived from the exported tabs array (complete by construction).
const TAB_SCREENS: ScreenEntry[] = STUDY_SETUP_TABS.map((t) => ({
  name: t.id.replace(/-/g, '_'),
  aliases: TAB_ALIASES[t.id] || [t.label.toLowerCase()],
  requires: 'study' as ScreenRequires,
  target: { mode: 'study-setup', tab: t.id },
}))

// Merge, de-dup by name (mode/routed win over tabs on collision).
const byName = new Map<string, ScreenEntry>()
for (const e of [...TAB_SCREENS, ...SUBTAB_SCREENS, ...MODE_SCREENS, ...ROUTED_SCREENS]) {
  byName.set(e.name, e)
}

export const SCREEN_CATALOG: ScreenEntry[] = Array.from(byName.values())

export function getScreen(name: string): ScreenEntry | undefined {
  return byName.get(name)
}

/** Compact catalog sent to the backend to drive navigate_to's allowed screens. */
export function catalogForBackend(): { name: string; aliases: string[]; requires: ScreenRequires }[] {
  return SCREEN_CATALOG.map(({ name, aliases, requires }) => ({ name, aliases, requires }))
}
