import { ControlTowerStage, ControlStage, Milestone, Activity } from '@/features/sites/types/siteStatus'

/**
 * Control Tower Configuration
 * 
 * Defines all stages, milestones, and activities for the Site Control Tower.
 * This is a config-driven approach - changes here don't require code changes.
 */

// Helper function to check metadata for milestone completion
const checkMetadata = (metadata: Record<string, any> | null, key: string, value?: any): boolean => {
  if (!metadata) return false
  if (value !== undefined) {
    return metadata[key] === value
  }
  return !!metadata[key]
}

// ---------------------------------------------------------------------------
// Milestone Definitions
// ---------------------------------------------------------------------------

// Helper function to check workflow step completion
const checkWorkflowStep = (workflowSteps: any[] | null | undefined, stepName: string): boolean => {
  if (!workflowSteps || !Array.isArray(workflowSteps)) return false
  const step = workflowSteps.find(s => s.step_name === stepName)
  return step?.status === 'completed'
}

// Helper function to get workflow step data
const getWorkflowStepData = (workflowSteps: any[] | null | undefined, stepName: string): Record<string, any> | null => {
  if (!workflowSteps || !Array.isArray(workflowSteps)) return null
  const step = workflowSteps.find(s => s.step_name === stepName)
  return step?.step_data || null
}

const milestones: Record<string, Milestone> = {
  // Under Consideration milestones
  site_identification: {
    id: 'site_identification',
    label: 'Site Identification',
    description: 'Site has been identified for potential participation',
    completionRule: (_m, workflowSteps) => {
      // Check workflow step 1 (site_identification) is completed
      return checkWorkflowStep(workflowSteps, 'site_identification')
    },
  },
  cda_execution: {
    id: 'cda_execution',
    label: 'CDA Execution',
    description: 'Confidentiality Disclosure Agreement has been executed',
    completionRule: (_m, workflowSteps) => {
      // Check workflow step 2 (cda_execution) is completed
      return checkWorkflowStep(workflowSteps, 'cda_execution')
    },
  },
  feasibility: {
    id: 'feasibility',
    label: 'Feasibility',
    description: 'Feasibility completed and report available (artifact-backed)',
    completionRule: (_m, workflowSteps) => {
      // Check workflow step 3 (feasibility) is completed AND has response
      const stepData = getWorkflowStepData(workflowSteps, 'feasibility')
      return checkWorkflowStep(workflowSteps, 'feasibility') && 
             (stepData?.response_received === true || stepData?.response_received === 'true')
    },
  },
  site_selection_outcome: {
    id: 'site_selection_outcome',
    label: 'Site Selection Outcome',
    description: 'Site selection outcome: Selected, Not Selected, or Hold',
    completionRule: (_m, workflowSteps) => {
      // Check workflow step 4 (site_selection_outcome) is completed AND has decision
      const stepData = getWorkflowStepData(workflowSteps, 'site_selection_outcome')
      return checkWorkflowStep(workflowSteps, 'site_selection_outcome') && 
             (stepData?.decision === 'selected' || stepData?.decision === 'not_selected')
    },
    blocking: true, // Blocks if Not Selected
  },

  // Startup milestones
  cta_budget_finalized: {
    id: 'cta_budget_finalized',
    label: 'CTA & Budget Finalized',
    description: 'Clinical Trial Agreement and budget have been finalized',
    completionRule: (m) => checkMetadata(m, 'cta_finalized', true) && checkMetadata(m, 'budget_finalized', true),
  },
  irb_iec_submission: {
    id: 'irb_iec_submission',
    label: 'IRB/IEC Submission',
    description: 'IRB/IEC submission completed',
    completionRule: (m) => checkMetadata(m, 'irb_iec_submission', true),
  },
  irb_iec_review: {
    id: 'irb_iec_review',
    label: 'IRB/IEC Review',
    description: 'IRB/IEC review status: Pending or Done',
    completionRule: (m) => {
      const reviewStatus = m?.irb_iec_review_status
      return reviewStatus === 'Done'
    },
  },
  irb_iec_approval: {
    id: 'irb_iec_approval',
    label: 'IRB/IEC Approval',
    description: 'IRB/IEC approval status: Approved, Received Query, or Rejected',
    completionRule: (m) => {
      const approvalStatus = m?.irb_iec_approval_status
      return approvalStatus === 'Approved'
    },
    blocking: true, // Blocks if Rejected
  },

  // Enrollment Initiation milestones
  siv_kit_dispatched: {
    id: 'siv_kit_dispatched',
    label: 'SIV Kit Dispatched',
    description: 'Site Initiation Visit kit has been dispatched',
    completionRule: (m) => checkMetadata(m, 'siv_kit_dispatched', true),
  },
  all_study_materials_available: {
    id: 'all_study_materials_available',
    label: 'All Study Materials Available',
    description: 'All study materials are available at site',
    completionRule: (m) => checkMetadata(m, 'all_study_materials_available', true),
  },
  ip_non_ip_available: {
    id: 'ip_non_ip_available',
    label: 'IP / Non-IP Available',
    description: 'Investigational Product and non-investigational products are available',
    completionRule: (m) => checkMetadata(m, 'ip_available', true) && checkMetadata(m, 'non_ip_available', true),
  },
  site_initiation_completed: {
    id: 'site_initiation_completed',
    label: 'Site Initiation Completed',
    description: 'Site initiation has been completed',
    completionRule: (m) => checkMetadata(m, 'site_initiation_completed', true),
  },
  training_system_access_completed: {
    id: 'training_system_access_completed',
    label: 'Training & System Access Completed',
    description: 'Training and system access have been completed',
    completionRule: (m) => checkMetadata(m, 'training_completed', true) && checkMetadata(m, 'system_access_completed', true),
  },

  // Initiated Post-SIV milestones
  initiation_completed: {
    id: 'initiation_completed',
    label: 'Initiation Completed',
    description: 'Site initiation process has been completed',
    completionRule: (m) => !!m?.initiation_completed_at,
  },
  siv_action_items_closed: {
    id: 'siv_action_items_closed',
    label: 'SIV Action Items Closed',
    description: 'All SIV action items have been closed',
    completionRule: (m) => checkMetadata(m, 'siv_action_items_closed', true),
  },

  // Open for Recruitment milestones
  recruitment_enabled: {
    id: 'recruitment_enabled',
    label: 'Recruitment Enabled',
    description: 'Site has been authorized to start recruitment',
    completionRule: (m) => !!m?.recruitment_enabled_at,
  },

  // Active Not Recruiting milestones
  enrollment_closed: {
    id: 'enrollment_closed',
    label: 'Enrollment Closed',
    description: 'Patient enrollment has been closed',
    completionRule: (m) => !!m?.enrollment_closed_at,
  },

  // Closed milestones
  all_subjects_completed: {
    id: 'all_subjects_completed',
    label: 'All Subjects Completed',
    description: 'All subjects have completed the study',
    completionRule: (m) => !!m?.all_subjects_completed_at,
  },
  closeout_visit_completed: {
    id: 'closeout_visit_completed',
    label: 'Close-out Visit Completed',
    description: 'Site close-out visit has been completed',
    completionRule: (m) => !!m?.close_out_visit_date,
  },
}

// ---------------------------------------------------------------------------
// Activity Definitions
// ---------------------------------------------------------------------------

const activities: Record<string, Activity> = {
  view_site_details: {
    id: 'view_site_details',
    label: 'View Site Details',
    type: 'link',
    enabledRule: () => true, // Always enabled
  },
  initiate_econsent: {
    id: 'initiate_econsent',
    label: 'Initiate eConsent',
    type: 'button',
    enabledRule: (stage) => stage === 'open_for_recruitment',
    tooltip: 'Site must be in "Open for Recruitment" stage',
  },
  start_screening: {
    id: 'start_screening',
    label: 'Start Screening',
    type: 'button',
    enabledRule: (stage) => stage === 'open_for_recruitment',
    tooltip: 'Site must be in "Open for Recruitment" stage',
  },
  schedule_siv: {
    id: 'schedule_siv',
    label: 'Schedule SIV',
    type: 'button',
    enabledRule: (stage) => stage === 'enrollment_initiation',
    tooltip: 'Available during Enrollment Initiation stage',
  },
  enable_recruitment: {
    id: 'enable_recruitment',
    label: 'Enable Recruitment',
    type: 'button',
    enabledRule: (stage) => stage === 'initiated_post_siv',
    tooltip: 'Available after SIV completion and action items closed',
  },
}

// ---------------------------------------------------------------------------
// Stage Configurations
// ---------------------------------------------------------------------------

export const controlTowerStages: ControlTowerStage[] = [
  {
    id: 'under_consideration',
    label: 'Under Consideration',
    order: 0,
    description: 'Feasibility and pre-selection phase – site identified, CDA/SFQ/SQV in progress.',
    definition: 'Site identified by the central feasibility group as a potential site.',
    milestones: [
      milestones.site_identification,
      milestones.cda_execution,
      milestones.feasibility,
      milestones.site_selection_outcome,
    ],
    activities: [activities.view_site_details],
    readinessRules: [],
  },
  {
    id: 'startup_site_selection',
    label: 'Under Start-up',
    order: 1,
    description: 'Contracting and regulatory start-up – CTA and ethics approvals, essential documents collection.',
    definition: 'Site considered eligible at the end of feasibility/site selection.',
    milestones: [
      milestones.cta_budget_finalized,
      milestones.irb_iec_submission,
      milestones.irb_iec_review,
      milestones.irb_iec_approval,
    ],
    activities: [activities.view_site_details],
    readinessRules: [],
  },
  {
    id: 'enrollment_initiation',
    label: 'Enrollment Initiation (Pre-SIV)',
    order: 2,
    description: 'Site initiation activities – SIV kit dispatch, training, and readiness checks.',
    definition: 'Site readiness for initiation and completion of site initiation.',
    milestones: [
      milestones.siv_kit_dispatched,
      milestones.all_study_materials_available,
      milestones.ip_non_ip_available,
      milestones.site_initiation_completed,
      milestones.training_system_access_completed,
    ],
    activities: [activities.view_site_details, activities.schedule_siv],
    readinessRules: [],
  },
  {
    id: 'initiated_post_siv',
    label: 'Initiated (Post-SIV)',
    order: 3,
    description: 'Initiation complete; site activated but not yet opened for patient recruitment.',
    milestones: [
      milestones.initiation_completed,
      milestones.siv_action_items_closed,
    ],
    activities: [activities.view_site_details, activities.enable_recruitment],
    readinessRules: [
      {
        stage: 'initiated_post_siv',
        blockingMilestones: ['siv_action_items_closed'],
      },
    ],
  },
  {
    id: 'open_for_recruitment',
    label: 'Open for Recruitment',
    order: 4,
    description: 'Site is authorised to start screening and enrolling subjects.',
    definition: 'Ready for patient screening and enrollment.',
    milestones: [milestones.recruitment_enabled],
    activities: [
      activities.view_site_details,
      activities.initiate_econsent,
      activities.start_screening,
    ],
    readinessRules: [],
  },
  {
    id: 'active_not_recruiting',
    label: 'Recruitment Completed / Follow-up',
    order: 5,
    description: 'Enrollment closed; subjects remain on treatment or in follow-up.',
    definition: 'Enrollment closed; patients under treatment or follow-up.',
    milestones: [milestones.enrollment_closed],
    activities: [activities.view_site_details],
    readinessRules: [],
  },
  {
    id: 'on_hold',
    label: 'Suspended / On Hold',
    order: -1, // Special overlay stage
    description: 'Temporary pause of study activities at this site (may resume to previous status).',
    definition: 'Temporarily stopped recruiting and/or treating participants.',
    milestones: [],
    activities: [activities.view_site_details],
    readinessRules: [],
  },
  {
    id: 'closed_final',
    label: 'Closed',
    order: 6,
    description: 'Site close-out visit completed and all close-out activities finalised.',
    definition: 'Site close-out done after completion of all site-related activities.',
    milestones: [milestones.all_subjects_completed, milestones.closeout_visit_completed],
    activities: [activities.view_site_details],
    readinessRules: [],
  },
]

/**
 * Get stage configuration by ID
 */
export function getStageConfig(stageId: ControlStage): ControlTowerStage | undefined {
  return controlTowerStages.find((s) => s.id === stageId)
}

/**
 * Get all stages in order (excluding on_hold overlay)
 */
export function getStagesInOrder(): ControlTowerStage[] {
  return controlTowerStages.filter((s) => s.order >= 0).sort((a, b) => a.order - b.order)
}

/**
 * Get milestone by ID
 */
export function getMilestone(milestoneId: string): Milestone | undefined {
  for (const stage of controlTowerStages) {
    const milestone = stage.milestones.find((m) => m.id === milestoneId)
    if (milestone) return milestone
  }
  return undefined
}

