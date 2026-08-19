// Guided-tour recipes (read-only). Whitelist: the assistant can only trigger a
// tour whose id is registered here — never arbitrary DOM. Tours perform ZERO
// writes — `clickNext` only opens tabs/modals (local UI state), never submits.
//
// Three kinds of recipe:
// 1. SCREEN TOURS — orientation-first: the opening step highlights the nav
//    entry on the CURRENT screen ("here's where this lives"), then a `screen`
//    step navigates and walks the destination's landmarks.
// 2. HOW-TO TOURS — "how do I create a budget?" — walk the exact click path,
//    with action-toned pulsing highlights on the real buttons.
// 3. THE GRAND TOUR (`app_overview`) — a multi-screen sweep of the whole app.
//
// Coverage guarantee: every SCREEN_CATALOG screen has a tour; screens without a
// curated recipe get an auto-generated one, and runTour renders narration as a
// centered popover when an anchor is missing — a demo never dead-ends.

import { SCREEN_CATALOG } from '../blocks/screenCatalog'

export interface TourStep {
  /** CSS selector, prefer [data-testid="…"]. Omit → centered narration popover. */
  selector?: string
  title: string
  description: string
  /** Navigate to this screenCatalog screen before showing this step. */
  screen?: string
  /** Advancing from this step clicks the highlighted element first (opens a tab/modal — local UI only, never a submit). */
  clickNext?: boolean
  /** Popover accent: nav = "where it lives", action = "what you'd click", info = context. Default info. */
  tone?: 'nav' | 'action' | 'info'
  /** Pulsing ring on the highlighted element — use on click targets. */
  pulse?: boolean
}

export interface TourRecipe {
  id: string
  label: string
  aliases: string[]
  /** Default screen for recipes whose steps don't declare per-step screens. */
  screen: string
  /** Fallback narration when no anchors render (empty state / slow data). */
  intro?: string
  steps: TourStep[]
}

// Shared orientation fragments -----------------------------------------------

const NAV = (id: string) => `[data-testid="nav-${id}"]`
const T = (id: string) => `[data-testid="${id}"]`
/** Site Profile appears either as a plain nav tab or as the forms dropdown. */
const NAV_SITE_PROFILE = `${T('nav-forms-dropdown')}, ${NAV('site-profile')}`

const pickStudySite = (what: string): TourStep => ({
  selector: T('nav-study-selector'),
  tone: 'nav',
  pulse: true,
  title: 'Pick your study & site',
  description: `${what} is scoped to the study and site chosen up here — set both first (or just tell me which one, I'll switch for you).`,
})

// ── Screen tours (orientation-first) ─────────────────────────────────────────

const CURATED_TOURS: TourRecipe[] = [
  {
    id: 'app_overview',
    label: 'The whole application',
    aliases: ['the app', 'whole application', 'everything', 'full tour', 'overview of the app', 'the crm', 'all screens'],
    screen: 'dashboard',
    intro: 'A quick sweep of the whole CRM — navigation, dashboard, study setup, inbox, tasks, and monitoring.',
    steps: [
      {
        selector: T('app-navbar'),
        tone: 'nav',
        title: 'Your compass',
        description: 'Everything starts here — Dashboard, Study Setup, site screens, Documents, Tasks, Monitoring, and Conversations are one click away.',
      },
      {
        selector: T('nav-study-selector'),
        tone: 'nav',
        pulse: true,
        title: 'Pick your study',
        description: 'The golden rule: pick a study here first. Every screen shows data for the selected study.',
      },
      {
        selector: T('nav-site-selector'),
        tone: 'nav',
        pulse: true,
        title: 'Then pick your site',
        description: 'Site-level screens — Site Profile, Status, Monitoring, Documents, Agreements — also need a site. It unlocks once a study is chosen.',
      },
      {
        screen: 'dashboard',
        selector: T('dashboard-action-bar'),
        title: '1 · Study Dashboard',
        description: 'Your daily read — enrollment, activation, compliance, queries, and milestones, with persona views for Study manager, CRA, and Exec.',
      },
      {
        screen: 'study_setup',
        selector: T('study-setup-tabs'),
        title: '2 · Study Setup',
        description: 'The configuration home: study details, sites, team, agreement templates, agreements, the Budget Builder, and the MVR template.',
      },
      {
        screen: 'conversations',
        selector: T('inbox-header'),
        title: '3 · Conversations',
        description: 'The unified inbox — email-style conversations and grouped threads with your sites, all in one feed.',
      },
      {
        screen: 'tasks',
        selector: T('tasks-table'),
        title: '4 · Tasks',
        description: 'Every action item with assignee, due date, and status. I can create or fill tasks for you from chat.',
      },
      {
        screen: 'monitoring',
        selector: T('monitoring-root'),
        title: '5 · Monitoring',
        description: 'Site monitoring visits end-to-end — schedule visits, pre-visit letters, and monitoring visit reports.',
      },
      {
        title: 'That’s the lay of the land',
        description: 'Ask me for a demo of any screen ("demo the budget builder"), or how to do anything ("how do I create a task?") — I’ll walk you through it right here.',
      },
    ],
  },
  {
    id: 'dashboard',
    label: 'Study Dashboard',
    aliases: ['dashboard', 'home', 'overview', 'study dashboard', 'kpis'],
    screen: 'dashboard',
    intro: 'The study dashboard — enrollment, site activation, visit compliance, and more in one place.',
    steps: [
      {
        selector: NAV('dashboard'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Dashboard sits first in the top navigation — it’s your landing view.',
      },
      {
        screen: 'dashboard',
        selector: T('dashboard-action-bar'),
        title: 'Study & persona',
        description: 'The selected study, plus persona views — Study manager, CRA, and Exec each get a tailored slice.',
      },
      {
        selector: T('dashboard-nav'),
        title: 'Dashboard sections',
        description: 'Jump to any section — enrollment, country & site, disposition, activation, compliance, queries, deviations, milestones, and AI insights.',
      },
      {
        selector: '#d1',
        title: 'Enrollment',
        description: 'The enrollment overview — target vs enrolled, rate per month, funnel and S-curve.',
      },
    ],
  },
  {
    id: 'tasks',
    label: 'Tasks',
    aliases: ['task', 'tasks', 'to-dos', 'action items', 'task list'],
    screen: 'tasks',
    intro: 'The Tasks screen — every action item with due date, assignee, and status.',
    steps: [
      {
        selector: NAV('tasks'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Tasks has its own tab in the top navigation — the ✅ icon.',
      },
      {
        screen: 'tasks',
        selector: T('tasks-table'),
        title: 'Your tasks',
        description: 'Every action item lives here — due date, assignee, status, and updates in one table.',
      },
      {
        selector: T('tasks-search'),
        title: 'Search & filter',
        description: 'Search free-text, or narrow by status and role with the dropdowns beside this box.',
      },
      {
        selector: T('tasks-add-button'),
        tone: 'action',
        pulse: true,
        title: 'Add a task',
        description: 'Create a new task here — or just ask me to create or fill one for you.',
      },
    ],
  },
  {
    id: 'conversations',
    label: 'Conversations',
    aliases: ['conversation', 'conversations', 'inbox', 'messages'],
    screen: 'conversations',
    intro: 'The unified inbox — conversations and threads for the selected study and site.',
    steps: [
      {
        selector: NAV('conversations'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Conversations is the 💬 tab in the top navigation.',
      },
      pickStudySite('The inbox'),
      {
        screen: 'conversations',
        selector: T('inbox-header'),
        title: 'Conversations & Threads',
        description: 'Your unified inbox — switch between individual conversations and grouped threads with this toggle.',
      },
      {
        selector: T('inbox-list'),
        title: 'The list',
        description: 'Conversations for the selected study and site. Click one to read and reply.',
      },
      {
        selector: T('inbox-new-conversation'),
        tone: 'action',
        pulse: true,
        title: 'Start a conversation',
        description: 'Create a new conversation here — or ask me to start one for you.',
      },
    ],
  },
  {
    id: 'threads',
    label: 'Threads',
    aliases: ['thread', 'threads', 'thread groups'],
    screen: 'threads',
    intro: 'Threads — logical groupings of related conversations with status and priority.',
    steps: [
      {
        selector: NAV('conversations'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Threads share the inbox with Conversations — enter through the 💬 tab, then flip the Threads toggle.',
      },
      {
        screen: 'threads',
        selector: T('inbox-header'),
        title: 'Threads view',
        description: 'The inbox in thread mode — related conversations grouped into one logical thread.',
      },
      {
        selector: T('threads-list'),
        title: 'Your threads',
        description: 'Each card shows the thread’s type, status, priority, and participants. Click one to open it.',
      },
    ],
  },
  {
    id: 'study_setup',
    label: 'Study Setup',
    aliases: ['study setup', 'study configuration'],
    screen: 'study_setup',
    intro: 'Study Setup — one home for study details, sites, team, templates, agreements, budget, and MVR.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Study Setup is the 🔬 tab in the top navigation — pick a study first.',
      },
      {
        screen: 'study_setup',
        selector: T('study-setup-tabs'),
        title: 'Study Setup',
        description: 'Everything you configure for a study lives in these tabs — details, sites, team, templates, agreements, budget, and the MVR template.',
      },
    ],
  },
  {
    id: 'site_profile',
    label: 'Site Profile',
    aliases: ['site profile', 'site details', 'site identity'],
    screen: 'site_profile',
    intro: 'Site Profile — core site identity, PI, contacts, and ethics committee mapping.',
    steps: [
      {
        selector: NAV_SITE_PROFILE,
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Site Profile is in the top navigation — on wider screens it’s a small menu that also holds Site Staff and IRB info.',
      },
      pickStudySite('Site Profile'),
      {
        screen: 'site_profile',
        selector: T('site-profile-header'),
        title: 'Site Profile',
        description: 'Core identity for the selected site — with the current edit/view state shown up here.',
      },
      {
        selector: T('site-profile-sections'),
        title: 'Profile sections',
        description: 'Jump to any section — identification, PI, contract, address, contacts, and IRB/IEC mapping.',
      },
    ],
  },
  {
    id: 'site_status',
    label: 'Site Status',
    aliases: ['site status', 'site readiness', 'readiness'],
    screen: 'site_status',
    intro: 'Site Status — the site’s clinical lifecycle status with breakdown and timeline.',
    steps: [
      {
        selector: NAV('site-status'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Site Status has its own tab in the top navigation.',
      },
      pickStudySite('Site Status'),
      {
        screen: 'site_status',
        selector: T('site-status-header'),
        title: 'Site Status',
        description: 'The site’s clinical status overview, with operational, monitoring, and logistics context.',
      },
      {
        selector: T('site-status-primary'),
        title: 'Primary status',
        description: 'The site’s current primary status — the headline of where this site is in its lifecycle.',
      },
    ],
  },
  {
    id: 'site_staff',
    label: 'Site Staff',
    aliases: ['site staff', 'staff', 'site team', 'staff details'],
    screen: 'site_staff',
    intro: 'Site Staff Details — everyone assigned to this site, with add/edit in one place.',
    steps: [
      {
        selector: NAV_SITE_PROFILE,
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Site Staff Details is inside the Site Profile menu in the top navigation.',
      },
      {
        screen: 'site_staff',
        selector: T('site-staff-header'),
        title: 'Site Staff Details',
        description: 'All staff assigned to this site — search here, or add a new member with the button on the right.',
      },
      {
        selector: T('site-staff-table'),
        title: 'The staff list',
        description: 'Each member with their role and contact details. Click a row to edit.',
      },
    ],
  },
  {
    id: 'irb_administrative_info',
    label: 'IRB Administrative Info',
    aliases: ['irb', 'irb info', 'ethics', 'ethics committee', 'iec'],
    screen: 'irb_administrative_info',
    intro: 'IRB Administrative Info — details for the ethics committee linked to this site.',
    steps: [
      {
        selector: NAV_SITE_PROFILE,
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'IRB Administrative Info is inside the Site Profile menu in the top navigation.',
      },
      {
        screen: 'irb_administrative_info',
        selector: T('irb-header'),
        title: 'IRB Administrative Info',
        description: 'Administrative details for the IRB linked to your site — the committee itself is chosen in Site Profile.',
      },
    ],
  },
  {
    id: 'logistics',
    label: 'Logistics',
    aliases: ['logistics', 'site logistics', 'drug inventory', 'shipments'],
    screen: 'logistics',
    intro: 'Logistics — patients, drug inventory, and payments for this site.',
    steps: [
      pickStudySite('Logistics'),
      {
        screen: 'logistics',
        selector: T('logistics-header'),
        title: 'Logistics',
        description: 'Patients, drug inventory, and payments for the selected site. There’s no navbar tab for this one — ask me or use ⌘K to jump here.',
      },
      {
        selector: T('logistics-stats'),
        title: 'At a glance',
        description: 'Active patients, drug remaining, amount paid, and amount due — click the site card below for the full drill-down.',
      },
    ],
  },
  {
    id: 'monitoring',
    label: 'Monitoring',
    aliases: ['monitoring', 'monitoring visits', 'mvr', 'visits'],
    screen: 'monitoring',
    intro: 'Monitoring — site monitoring visits, reports, and compliance tracking.',
    steps: [
      {
        selector: NAV('monitoring'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Monitoring is the 📡 tab in the top navigation.',
      },
      pickStudySite('Monitoring'),
      {
        screen: 'monitoring',
        selector: T('monitoring-root'),
        title: 'Monitoring',
        description: 'The monitoring module — visits, pre-visit letters, reports, and compliance for the selected site.',
      },
      {
        selector: T('mon-create-visit-button'),
        tone: 'action',
        pulse: true,
        title: 'Create a visit',
        description: 'New monitoring visits start here — or ask me “how do I set up a monitoring visit?” for the full walkthrough.',
      },
    ],
  },
  {
    id: 'documents',
    label: 'Site Documents (ISF)',
    aliases: ['documents', 'isf', 'investigator site file', 'site file', 'site documents'],
    screen: 'documents',
    intro: 'The Investigator Site File — hierarchical document management for this site.',
    steps: [
      {
        selector: NAV('documents'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Documents is the 📁 tab in the top navigation.',
      },
      {
        screen: 'documents',
        selector: T('isf-sidebar'),
        title: 'ISF navigation',
        description: 'Switch between the ISF Viewer, the document workflow, and site packages here.',
      },
      {
        selector: T('isf-root'),
        title: 'The ISF module',
        description: 'Browse and manage the Investigator Site File — documents organized in their regulatory hierarchy.',
      },
    ],
  },
  {
    id: 'workflow_tasks',
    label: 'Workflow Inbox',
    aliases: ['workflow inbox', 'workflow tasks', 'my workflow steps', 'work items'],
    screen: 'workflow_tasks',
    intro: 'The Workflow Inbox — every open workflow step assigned to you, across all instances.',
    steps: [
      {
        screen: 'workflow_tasks',
        selector: T('workflow-inbox-header'),
        title: 'Workflow Tasks',
        description: 'Every open workflow step addressed to you, across all running workflows — it opens as its own page; use “Back to CRM” to return. Filter by status up here.',
      },
      {
        selector: T('workflow-inbox-list'),
        title: 'Your work items',
        description: 'Claim or reassign inline — clicking a task opens its workflow with the step panel ready.',
      },
    ],
  },
  // ── Study Setup tab tours ──────────────────────────────────────────────────
  {
    id: 'study_details',
    label: 'Study Details',
    aliases: ['study details', 'study info'],
    screen: 'study_details',
    intro: 'Study Details — the study’s core facts: phase, design, sponsor, and status.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Study Details is the first tab inside Study Setup (🔬 in the top navigation).',
      },
      {
        screen: 'study_details',
        selector: T('study-setup-tab-study-details'),
        title: 'Study Details tab',
        description: 'The first stop in Study Setup — the study’s core facts.',
      },
      {
        selector: T('study-details-card'),
        title: 'The study record',
        description: 'Name, therapeutic area, phase, design, sponsor, protocol version, and current status.',
      },
    ],
  },
  {
    id: 'site_setup',
    label: 'Site Setup',
    aliases: ['site setup', 'manage sites', 'site assignment'],
    screen: 'site_setup',
    intro: 'Site Setup — assign and manage the sites participating in this study.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Site Setup is a tab inside Study Setup (🔬 in the top navigation).',
      },
      {
        screen: 'site_setup',
        selector: T('study-setup-tab-site-setup'),
        title: 'Site Setup tab',
        description: 'Where sites are added to and managed for this study.',
      },
      {
        selector: T('site-assignments-table'),
        title: 'Site assignments',
        description: 'Each row is a study–facility–personnel combination. Edit inline, or add a new site with the button above.',
      },
    ],
  },
  {
    id: 'study_team',
    label: 'Study Team',
    aliases: ['study team', 'users', 'team', 'team members'],
    screen: 'study_team',
    intro: 'Users / Study Team — everyone on this study with their roles, sourced from IAM.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'The team list is a tab inside Study Setup (🔬 in the top navigation).',
      },
      {
        screen: 'study_team',
        selector: T('study-setup-tab-study-team'),
        title: 'Users / Study Team tab',
        description: 'The people on this study and their roles.',
      },
      {
        selector: T('study-team-header'),
        title: 'Team list',
        description: 'Sourced from the IAM hub — switch scope between this study and all studies, and search by name. Roles are managed in IAM, so this view is read-only.',
      },
    ],
  },
  {
    id: 'template_library',
    label: 'Template Library',
    aliases: ['template library', 'templates', 'agreement templates'],
    screen: 'template_library',
    intro: 'The Template Library — agreement templates and the reusable clause library.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'The Template Library is a tab inside Study Setup (🔬 in the top navigation).',
      },
      {
        screen: 'template_library',
        selector: T('template-library-subtabs'),
        title: 'Templates & Clauses',
        description: 'Two sub-views — the agreement templates themselves, and the reusable Clause Library they draw from.',
      },
      {
        selector: T('template-upload-button'),
        tone: 'action',
        pulse: true,
        title: 'Add a template',
        description: 'Upload a DOCX template here — then configure its placeholders from the list below.',
      },
    ],
  },
  {
    id: 'clause_library',
    label: 'Clause Library',
    aliases: ['clause library', 'clauses', 'clause', 'clause templates'],
    screen: 'clause_library',
    intro: 'The Clause Library — reusable clauses you can insert into any agreement template.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'The Clause Library is a sub-tab of the Template Library, inside Study Setup.',
      },
      {
        screen: 'clause_library',
        selector: T('clause-library-header'),
        title: 'Clause Library',
        description: 'Reusable clauses — insert them into any agreement template from the Clause Builder.',
      },
      {
        selector: T('clause-library-toolbar'),
        tone: 'action',
        pulse: true,
        title: 'Create, search, filter',
        description: 'Add a new clause, search by text, or filter by category here.',
      },
    ],
  },
  {
    id: 'agreements',
    label: 'Agreements',
    aliases: ['agreement', 'agreements', 'contracts', 'cda', 'cta'],
    screen: 'agreements',
    intro: 'The Agreements tab — the selected site’s contract workflow from draft to signature.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'Agreements is a tab inside Study Setup (🔬 in the top navigation) — pick the study and site first.',
      },
      {
        screen: 'agreements',
        selector: T('study-setup-tab-agreements'),
        title: 'Agreements tab',
        description: 'This tab holds the selected site’s agreement workflow.',
      },
      {
        selector: T('agreements-workflow'),
        title: 'The workflow',
        description: 'The agreement moves from draft through review to signature here — status, documents, and actions in one place.',
      },
    ],
  },
  {
    id: 'site_budgeting',
    label: 'Site Budgeting',
    aliases: ['budget', 'budgeting', 'budget builder', 'site budget'],
    screen: 'budget',
    intro: 'The Budget Builder — configure site budgets at study, country, and site level.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'The Budget Builder is a tab inside Study Setup (🔬 in the top navigation).',
      },
      {
        screen: 'budget',
        selector: T('study-setup-tab-budget'),
        title: 'Budget Builder',
        description: 'The Budget Builder tab is where you set up site budgets.',
      },
      {
        selector: T('budget-level-tabs'),
        title: 'Study · Country · Site',
        description: 'Budgets are built at three levels — study defaults first, then country, then each site.',
      },
    ],
  },
  {
    id: 'mvr_template',
    label: 'MVR Template',
    aliases: ['mvr template', 'monitoring template', 'visit report template'],
    screen: 'mvr_template',
    intro: 'The MVR Template studio — build and manage monitoring visit report templates.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Where it lives',
        description: 'The MVR Template studio is the last tab inside Study Setup.',
      },
      {
        screen: 'mvr_template',
        selector: T('study-setup-tab-mvr-template'),
        title: 'MVR Template tab',
        description: 'Monitoring visit report templates are managed from this Study Setup tab.',
      },
      {
        selector: T('mvr-template-root'),
        title: 'Template studio',
        description: 'Manage existing MVR templates or open the builder to create and edit one.',
      },
    ],
  },
]

// ── How-to tours ("how do I …?") ──────────────────────────────────────────────

const HOWTO_TOURS: TourRecipe[] = [
  {
    id: 'how_to_create_budget',
    label: 'How to create a budget',
    aliases: ['how to create a budget', 'create a budget', 'set up a budget', 'build a budget', 'make a budget', 'how to build a budget'],
    screen: 'budget',
    intro: 'Creating a budget: Study Setup → Budget Builder → start at Study level → import the SOA → review elements and the visit matrix.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Step 1 — open Study Setup',
        description: 'Budgets live inside Study Setup. Pick your study up top, then head here.',
      },
      {
        screen: 'budget',
        selector: T('budget-level-tabs'),
        title: 'Step 2 — three levels',
        description: 'A budget is built top-down: Study defaults → Country adjustments → per-Site overrides. Always start at Study.',
      },
      {
        selector: T('budget-tab-study'),
        tone: 'action',
        pulse: true,
        title: 'Step 3 — start at Study',
        description: 'The Study tab holds the master template every country and site inherits from.',
      },
      {
        selector: T('budget-config-tab-soa'),
        tone: 'action',
        pulse: true,
        title: 'Step 4 — import the SOA',
        description: 'The Schedule of Activities import builds your visit structure automatically — much faster than typing visits by hand.',
      },
      {
        selector: T('soa-generate-button'),
        tone: 'action',
        pulse: true,
        title: 'Step 5 — generate the visit matrix',
        description: 'After uploading your SOA file, this button turns it into the per-visit grid.',
      },
      {
        selector: T('budget-config-tab-elements'),
        tone: 'action',
        pulse: true,
        title: 'Step 6 — cost elements',
        description: 'Then define the cost line items — what gets paid, per visit or per event.',
      },
      {
        selector: T('budget-config-tab-visits'),
        title: 'Step 7 — review the matrix',
        description: 'The Visit Matrix ties it together: every visit × every cost element. From here, refine country and site levels the same way.',
      },
    ],
  },
  {
    id: 'how_to_setup_monitoring_visit',
    label: 'How to set up a monitoring visit',
    aliases: ['how to set up a monitoring visit', 'create a monitoring visit', 'schedule a monitoring visit', 'new monitoring visit', 'set up a visit', 'schedule a visit'],
    screen: 'monitoring',
    intro: 'Setting up a monitoring visit: Monitoring tab → Create Visit → fill the visit form → the visit then drives the pre-visit letter and the report.',
    steps: [
      {
        selector: NAV('monitoring'),
        tone: 'nav',
        pulse: true,
        title: 'Step 1 — open Monitoring',
        description: 'Monitoring visits live under the 📡 Monitoring tab.',
      },
      pickStudySite('A monitoring visit'),
      {
        screen: 'monitoring',
        selector: T('mon-create-visit-button'),
        tone: 'action',
        pulse: true,
        title: 'Step 2 — Create Visit',
        description: 'This opens the visit form — visit type, dates, and monitor. The study and site must be selected first.',
      },
      {
        selector: T('monitoring-root'),
        title: 'Step 3 — the visit lifecycle',
        description: 'Once created, the visit appears in the list below. From its detail page you send the pre-visit letter, then complete the Monitoring Visit Report after the visit.',
      },
    ],
  },
  {
    id: 'how_to_create_task',
    label: 'How to create a task',
    aliases: ['how to create a task', 'create a task', 'add a task', 'new task', 'how to add a task'],
    screen: 'tasks',
    intro: 'Creating a task: Tasks tab → Add Task → fill description, assignee, and due date → Create.',
    steps: [
      {
        selector: NAV('tasks'),
        tone: 'nav',
        pulse: true,
        title: 'Step 1 — open Tasks',
        description: 'Tasks live under the ✅ tab in the top navigation.',
      },
      {
        screen: 'tasks',
        selector: T('tasks-add-button'),
        tone: 'action',
        pulse: true,
        clickNext: true,
        title: 'Step 2 — Add Task',
        description: 'Click here to open the task form. (I’ll open it for you when you press Next.)',
      },
      {
        selector: T('task-create-form'),
        title: 'Step 3 — fill the form',
        description: 'Who requested it, who it’s assigned to, the description, and the due date. Only the description is strictly required.',
      },
      {
        selector: T('task-submit'),
        tone: 'action',
        pulse: true,
        title: 'Step 4 — create it',
        description: 'This button saves the task. I’ll leave the form open so you can fill it in — or just tell me the details and I’ll create it for you.',
      },
    ],
  },
  {
    id: 'how_to_start_conversation',
    label: 'How to start a conversation',
    aliases: ['how to start a conversation', 'start a conversation', 'new conversation', 'send a message', 'how to send a message'],
    screen: 'conversations',
    intro: 'Starting a conversation: Conversations tab → the + button → subject → Create, then write your first message.',
    steps: [
      {
        selector: NAV('conversations'),
        tone: 'nav',
        pulse: true,
        title: 'Step 1 — open Conversations',
        description: 'The inbox lives under the 💬 tab.',
      },
      pickStudySite('A conversation'),
      {
        screen: 'conversations',
        selector: T('inbox-new-conversation'),
        tone: 'action',
        pulse: true,
        clickNext: true,
        title: 'Step 2 — new conversation',
        description: 'This + button starts one. (I’ll open the form when you press Next.)',
      },
      {
        selector: T('conversation-field-subject'),
        tone: 'action',
        pulse: true,
        title: 'Step 3 — give it a subject',
        description: 'The subject is required — then Create, and write your first message in the thread. Or just tell me the subject and I’ll start it for you.',
      },
    ],
  },
  {
    id: 'how_to_add_site',
    label: 'How to add a site',
    aliases: ['how to add a site', 'add a site', 'add site', 'new site', 'assign a site'],
    screen: 'site_setup',
    intro: 'Adding a site: Study Setup → Site Setup tab → Add New Site → pick facility and personnel → save.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Step 1 — open Study Setup',
        description: 'Sites are added per study, inside Study Setup.',
      },
      {
        screen: 'site_setup',
        selector: T('study-setup-tab-site-setup'),
        title: 'Step 2 — the Site Setup tab',
        description: 'This tab manages which sites participate in the study.',
      },
      {
        selector: T('site-assignments-table'),
        title: 'Step 3 — current assignments',
        description: 'Each row is a study–facility–personnel combination, with the site code the rest of the app uses.',
      },
      {
        selector: T('site-add-button'),
        tone: 'action',
        pulse: true,
        title: 'Step 4 — Add New Site',
        description: 'Click here to open the assignment form — choose the facility, assign personnel, and save.',
      },
    ],
  },
  {
    id: 'how_to_create_agreement',
    label: 'How to create an agreement',
    aliases: ['how to create an agreement', 'create an agreement', 'new agreement', 'send an agreement', 'how to send an agreement for review', 'how to sign an agreement'],
    screen: 'agreements',
    intro: 'Creating an agreement: Study Setup → Agreements tab → Create from Template → then follow the “Next step” box: send for review → complete review → send for signature.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Step 1 — open Study Setup',
        description: 'Agreements are per study + site, inside Study Setup. Pick both up top.',
      },
      {
        screen: 'agreements',
        selector: T('study-setup-tab-agreements'),
        title: 'Step 2 — the Agreements tab',
        description: 'One agreement workflow per site — CDA or CTA.',
      },
      {
        selector: T('agreement-create-from-template'),
        tone: 'action',
        pulse: true,
        title: 'Step 3 — Create from Template',
        description: 'New agreements start from a template in your Template Library. (If an agreement already exists you won’t see this — skip ahead.)',
      },
      {
        selector: T('agreement-next-step'),
        tone: 'action',
        pulse: true,
        title: 'Step 4 — follow “Next step”',
        description: 'Once a document exists, this box always shows the one action to take: Mark Ready & Send for Review → Complete Review → Send for Signature. The reviewer and signer get secure email links.',
      },
      {
        selector: T('agreements-workflow'),
        title: 'Step 5 — the full picture',
        description: 'Status, documents, review rounds, and signatures all live in this panel — the agreement is done when it reaches EXECUTED.',
      },
    ],
  },
  {
    id: 'how_to_create_template',
    label: 'How to create an agreement template',
    aliases: ['how to create a template', 'create a template', 'upload a template', 'new template', 'add a template'],
    screen: 'template_library',
    intro: 'Creating a template: Study Setup → Template Library → Upload Template (DOCX) → Configure its placeholders.',
    steps: [
      {
        selector: NAV('study-setup'),
        tone: 'nav',
        pulse: true,
        title: 'Step 1 — open Study Setup',
        description: 'Templates are managed per study, inside Study Setup.',
      },
      {
        screen: 'template_library',
        selector: T('template-library-subtabs'),
        title: 'Step 2 — the Template Library',
        description: 'Templates on the left sub-tab; the reusable Clause Library on the right.',
      },
      {
        selector: T('template-upload-button'),
        tone: 'action',
        pulse: true,
        title: 'Step 3 — Upload Template',
        description: 'Upload a DOCX with {{placeholders}} — study, site, and PI fields fill automatically when an agreement is generated.',
      },
      {
        selector: T('template-list-table'),
        title: 'Step 4 — configure placeholders',
        description: 'Each uploaded template appears here — use View to preview and Configure to map its placeholders.',
      },
    ],
  },
]

// ── Auto-generated fallback ───────────────────────────────────────────────────
// Any catalog screen not covered by a curated recipe still gets a tour
// (navigate + narration popover), keeping coverage complete when new
// screens/tabs are added to the catalog.

const coveredScreens = new Set(CURATED_TOURS.map((t) => t.screen))
const curatedIds = new Set([...CURATED_TOURS, ...HOWTO_TOURS].map((t) => t.id))

function labelFor(name: string): string {
  return name
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

const GENERATED_TOURS: TourRecipe[] = SCREEN_CATALOG.filter(
  (s) => !coveredScreens.has(s.name) && !curatedIds.has(s.name),
).map((s) => ({
  id: s.name,
  label: labelFor(s.name),
  aliases: s.aliases,
  screen: s.name,
  intro: `You're now on the ${labelFor(s.name)} screen.`,
  steps: [
    {
      selector: 'main, [role="main"], #root > div',
      title: labelFor(s.name),
      description: `This is the ${labelFor(s.name)} screen.`,
    },
  ],
}))

export const TOURS: TourRecipe[] = [...CURATED_TOURS, ...HOWTO_TOURS, ...GENERATED_TOURS]

export function getTour(id: string): TourRecipe | undefined {
  return TOURS.find((t) => t.id === id)
}

/** Compact list sent to the backend so start_tour's allowed ids stay in sync. */
export function toursForBackend(): { id: string; label: string; aliases: string[]; kind: 'tour' }[] {
  return TOURS.map(({ id, label, aliases }) => ({ id, label, aliases, kind: 'tour' }))
}
