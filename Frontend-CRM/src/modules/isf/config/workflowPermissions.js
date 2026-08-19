// Workflow Stage Access Control Configuration
// Defines which roles can access and operate on each workflow stage

import { ROLES } from './roles';
import { WORKFLOW_STATES } from '../components/documents/workflow/workflowUtils';

// Define workflow stage permissions for each role
export const WORKFLOW_STAGE_PERMISSIONS = {
  [WORKFLOW_STATES.INTAKE]: {
    // Who can perform intake operations
    // ✅ = Can edit (in allowedRoles), 👁️ = Can view only (in operations.view), ❌ = Cannot access
    allowedRoles: [
      ROLES.ADMIN,
      ROLES.STUDY_MANAGER,
      ROLES.STUDY_MONITOR
    ],
    // Operations allowed in this stage
    operations: {
      view: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.STUDY_MONITOR, ROLES.PRINCIPAL_INVESTIGATOR, ROLES.QA_REVIEWER, ROLES.TMF_LEAD], // PRINCIPAL_INVESTIGATOR: 👁️ view only
      edit: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.STUDY_MONITOR],
      validate: [ROLES.ADMIN, ROLES.STUDY_MANAGER],
      complete: [ROLES.ADMIN, ROLES.STUDY_MANAGER]
    },
    description: 'Document intake and initial validation'
  },

  [WORKFLOW_STATES.QC_VALIDATION]: {
    // ✅ = Can edit (in allowedRoles), 👁️ = Can view only (in operations.view), ❌ = Cannot access
    allowedRoles: [
      ROLES.ADMIN,
      ROLES.STUDY_MANAGER,
      ROLES.TMF_LEAD,
      ROLES.QA_REVIEWER,
      ROLES.PRINCIPAL_INVESTIGATOR
    ],
    operations: {
      view: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD, ROLES.QA_REVIEWER, ROLES.STUDY_MONITOR, ROLES.PRINCIPAL_INVESTIGATOR], // STUDY_MONITOR: 👁️ view only
      edit: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD, ROLES.QA_REVIEWER],
      assignOwner: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD],
      review: [ROLES.ADMIN, ROLES.QA_REVIEWER, ROLES.TMF_LEAD],
      complete: [ROLES.ADMIN, ROLES.QA_REVIEWER, ROLES.TMF_LEAD]
    },
    description: 'Quality control validation and TMF owner assignment'
  },

  [WORKFLOW_STATES.REVIEW_PREPARATION]: {
    // ✅ = Can edit (in allowedRoles), 👁️ = Can view only (in operations.view), ❌ = Cannot access
    allowedRoles: [
      ROLES.ADMIN,
      ROLES.STUDY_MANAGER,
      ROLES.TMF_LEAD
    ],
    operations: {
      view: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD, ROLES.QA_REVIEWER], // QA_REVIEWER: 👁️ view only
      edit: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD],
      assignReviewers: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD],
      preparePacket: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD],
      complete: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD]
    },
    description: 'Review preparation and reviewer assignment'
  },

  [WORKFLOW_STATES.IN_REVIEW]: {
    allowedRoles: [
      ROLES.ADMIN,
      ROLES.STUDY_MANAGER,
      ROLES.TMF_LEAD,
      ROLES.QA_REVIEWER
    ],
    operations: {
      view: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD, ROLES.QA_REVIEWER, ROLES.STUDY_MONITOR],
      review: [ROLES.ADMIN, ROLES.QA_REVIEWER, ROLES.TMF_LEAD],
      facilitate: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD],
      escalate: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD],
      complete: [ROLES.ADMIN, ROLES.QA_REVIEWER, ROLES.TMF_LEAD]
    },
    description: 'Document review by assigned reviewers'
  },

  // Combined "Review & Approval" stage (used in UI as single stage)
  'REVIEW': {
    allowedRoles: [
      ROLES.ADMIN,
      ROLES.STUDY_MANAGER,
      ROLES.TMF_LEAD,
      ROLES.QA_REVIEWER,
      ROLES.PRINCIPAL_INVESTIGATOR
    ],
    // operations: {
    //   view: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD, ROLES.QA_REVIEWER, ROLES.PRINCIPAL_INVESTIGATOR, ROLES.STUDY_MONITOR],
    //   review: [ROLES.ADMIN, ROLES.QA_REVIEWER, ROLES.TMF_LEAD],
    //   approve: [ROLES.ADMIN, ROLES.STUDY_MANAGER],
    //   sign: [ROLES.ADMIN],
    //   complete: [ROLES.ADMIN, ROLES.QA_REVIEWER, ROLES.TMF_LEAD]
    // },
    operations: {
      view: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD, ROLES.QA_REVIEWER, ROLES.PRINCIPAL_INVESTIGATOR, ROLES.STUDY_MONITOR],
      review: [ROLES.ADMIN, ROLES.TMF_LEAD],
      approve: [ROLES.ADMIN, ROLES.STUDY_MANAGER],
      sign: [ROLES.ADMIN],
      complete: [ROLES.ADMIN, ROLES.TMF_LEAD]
    },
    description: 'Combined review and approval workflow with e-signatures'
  },

  [WORKFLOW_STATES.PRE_APPROVAL]: {
    allowedRoles: [
      ROLES.ADMIN,
      ROLES.STUDY_MANAGER,
      ROLES.TMF_LEAD
    ],
    operations: {
      view: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD, ROLES.QA_REVIEWER],
      resolveFindings: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD],
      shareSummary: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD],
      complete: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD]
    },
    description: 'Pre-approval findings resolution'
  },

  [WORKFLOW_STATES.APPROVAL]: {
    allowedRoles: [
      ROLES.ADMIN,
      ROLES.STUDY_MANAGER,
      ROLES.PRINCIPAL_INVESTIGATOR
    ],
    operations: {
      view: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.PRINCIPAL_INVESTIGATOR, ROLES.TMF_LEAD],
      requestSignature: [ROLES.ADMIN, ROLES.STUDY_MANAGER],
      sign: [ROLES.ADMIN, ROLES.PRINCIPAL_INVESTIGATOR],
      sendReminder: [ROLES.ADMIN, ROLES.STUDY_MANAGER],
      complete: [ROLES.ADMIN, ROLES.PRINCIPAL_INVESTIGATOR]
    },
    description: 'Document approval and signature collection'
  },

  [WORKFLOW_STATES.ACTIVATION]: {
    // ✅ = Can edit (in allowedRoles), 👁️ = Can view only (in operations.view), ❌ = Cannot access
    allowedRoles: [
      ROLES.ADMIN,
      ROLES.STUDY_MANAGER,
      ROLES.TMF_LEAD
    ],
    operations: {
      view: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD, ROLES.STUDY_MONITOR, ROLES.PRINCIPAL_INVESTIGATOR, ROLES.QA_REVIEWER], // STUDY_MONITOR & PRINCIPAL_INVESTIGATOR: 👁️ view only
      distribute: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD],
      registerTraining: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD],
      activate: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD],
      complete: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD]
    },
    description: 'Document activation and distribution'
  },

  [WORKFLOW_STATES.REVISION]: {
    // ✅ = Can edit (in allowedRoles), 👁️ = Can view only (in operations.view), ❌ = Cannot access
    allowedRoles: [
      ROLES.ADMIN,
      ROLES.TMF_LEAD
    ],
    operations: {
      view: [ROLES.ADMIN, ROLES.TMF_LEAD, ROLES.QA_REVIEWER], // QA_REVIEWER: 👁️ view only
      manageChange: [ROLES.ADMIN, ROLES.TMF_LEAD],
      archive: [ROLES.ADMIN, ROLES.TMF_LEAD],
      complete: [ROLES.ADMIN, ROLES.TMF_LEAD]
    },
    description: 'Document revision and archival management'
  },

  // Audit Reporting stage (compliance dashboard)
  'AUDIT_REPORTING': {
    allowedRoles: [
      ROLES.ADMIN,
      ROLES.STUDY_MANAGER,
      ROLES.TMF_LEAD,
      ROLES.QA_REVIEWER
    ],
    operations: {
      view: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD, ROLES.QA_REVIEWER, ROLES.STUDY_MONITOR, ROLES.PRINCIPAL_INVESTIGATOR],
      export: [ROLES.ADMIN, ROLES.STUDY_MANAGER, ROLES.TMF_LEAD, ROLES.QA_REVIEWER],
      complete: [ROLES.ADMIN, ROLES.TMF_LEAD]
    },
    description: 'Compliance reporting and audit trail'
  }
};

// Helper function to check if a role can access a workflow stage
export const canAccessWorkflowStage = (userRole, stageKey) => {
  if (!userRole || !stageKey) return false;
  
  const stagePermissions = WORKFLOW_STAGE_PERMISSIONS[stageKey];
  if (!stagePermissions) return false;
  
  return stagePermissions.allowedRoles.includes(userRole);
};

// Helper function to check if a role can perform a specific operation in a stage
export const canPerformWorkflowOperation = (userRole, stageKey, operation) => {
  if (!userRole || !stageKey || !operation) return false;
  
  const stagePermissions = WORKFLOW_STAGE_PERMISSIONS[stageKey];
  if (!stagePermissions) return false;
  
  const operationPermissions = stagePermissions.operations[operation];
  if (!operationPermissions) return false;
  
  return operationPermissions.includes(userRole);
};

export const canPerformAnyWorkflowOperation = (userRole, stageKey, operations = []) => {
  if (!userRole || !stageKey || !Array.isArray(operations)) return false;

  const stagePermissions = WORKFLOW_STAGE_PERMISSIONS[stageKey];
  if (!stagePermissions) return false;

  return operations.some(operation =>
    stagePermissions.operations[operation]?.includes(userRole)
  );
};


// Get all accessible stages for a role
export const getAccessibleStages = (userRole) => {
  if (!userRole) return [];
  
  return Object.keys(WORKFLOW_STAGE_PERMISSIONS).filter(stageKey => 
    canAccessWorkflowStage(userRole, stageKey)
  );
};

// Get all operations a role can perform in a specific stage
export const getAvailableOperations = (userRole, stageKey) => {
  if (!userRole || !stageKey) return [];
  
  const stagePermissions = WORKFLOW_STAGE_PERMISSIONS[stageKey];
  if (!stagePermissions) return [];
  
  return Object.keys(stagePermissions.operations).filter(operation =>
    canPerformWorkflowOperation(userRole, stageKey, operation)
  );
};

// Get workflow stage info for a role
export const getWorkflowStageInfo = (stageKey) => {
  return WORKFLOW_STAGE_PERMISSIONS[stageKey] || null;
};

// Check if user can open/interact with a stage
export const canOpenWorkflowStage = (userRole, stageKey) => {
  // User can open if they can view the stage
  return canPerformWorkflowOperation(userRole, stageKey, 'view');
};

// Get role-based stage restrictions summary
export const getRoleStageRestrictions = (userRole) => {
  if (!userRole) return { accessible: [], restricted: [] };
  
  const allStages = Object.keys(WORKFLOW_STAGE_PERMISSIONS);
  const accessible = allStages.filter(stage => canAccessWorkflowStage(userRole, stage));
  const restricted = allStages.filter(stage => !canAccessWorkflowStage(userRole, stage));
  
  return { accessible, restricted };
};

