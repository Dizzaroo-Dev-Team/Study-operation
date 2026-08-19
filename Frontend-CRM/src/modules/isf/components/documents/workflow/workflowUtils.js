export const WORKFLOW_STATES = {
  INTAKE: 'INTAKE',
  QC_VALIDATION: 'QC_VALIDATION',
  REVIEW_PREPARATION: 'REVIEW_PREPARATION',
  IN_REVIEW: 'IN_REVIEW',
  PRE_APPROVAL: 'PRE_APPROVAL',
  APPROVAL: 'APPROVAL',
  ACTIVATION: 'ACTIVATION',
  MONITORING: 'MONITORING',
  REVISION: 'REVISION',
  OBSOLETE: 'OBSOLETE',
  ARCHIVED: 'ARCHIVED'
};

export const STAGE_STATUSES = {
  PENDING: 'PENDING',
  IN_PROGRESS: 'IN_PROGRESS',
  COMPLETED: 'COMPLETED',
  REJECTED: 'REJECTED',
  ESCALATED: 'ESCALATED'
};

export const STATUS_DISPLAY = {
  [WORKFLOW_STATES.INTAKE]: 'DRAFT',
  [WORKFLOW_STATES.QC_VALIDATION]: 'IN_QC',
  [WORKFLOW_STATES.REVIEW_PREPARATION]: 'DRAFT',
  [WORKFLOW_STATES.IN_REVIEW]: 'IN_REVIEW',
  [WORKFLOW_STATES.PRE_APPROVAL]: 'PENDING_APPROVAL',
  [WORKFLOW_STATES.APPROVAL]: 'PENDING_APPROVAL',
  [WORKFLOW_STATES.ACTIVATION]: 'APPROVED',
  [WORKFLOW_STATES.MONITORING]: 'APPROVED',
  [WORKFLOW_STATES.REVISION]: 'REVISION',
  [WORKFLOW_STATES.OBSOLETE]: 'ARCHIVED',
  [WORKFLOW_STATES.ARCHIVED]: 'ARCHIVED'
};

export const DISTRIBUTION_STATUSES = {
  NOT_STARTED: 'NOT_STARTED',
  IN_PROGRESS: 'IN_PROGRESS',
  COMPLETED: 'COMPLETED'
};

export const TRAINING_STATUSES = {
  NOT_STARTED: 'NOT_STARTED',
  IN_PROGRESS: 'IN_PROGRESS',
  COMPLETED: 'COMPLETED'
};

export const ESCALATION_LEVEL_OPTIONS = [
  'DOCUMENT_OWNER',
  'STUDY_LEAD',
  'QUALITY_MANAGER',
  'SYSTEM_ADMIN'
];

export const ESCALATION_METHOD_OPTIONS = ['EMAIL', 'SMS', 'SYSTEM', 'NONE'];

export const REVIEW_DECISION_OPTIONS = [
  { value: STAGE_STATUSES.COMPLETED, label: 'Approve' },
  { value: STAGE_STATUSES.REJECTED, label: 'Reject' },
  { value: STAGE_STATUSES.ESCALATED, label: 'Escalate' },
  { value: STAGE_STATUSES.IN_PROGRESS, label: 'Needs Follow-up' }
];

export const APPROVAL_DECISION_OPTIONS = [
  { value: STAGE_STATUSES.COMPLETED, label: 'Approve' },
  { value: STAGE_STATUSES.REJECTED, label: 'Reject' },
  { value: STAGE_STATUSES.ESCALATED, label: 'Escalate' }
];

export const toTitleCase = (value = '') =>
  value
    .toString()
    .toLowerCase()
    .split(/[_\s-]+/u)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');

export const humanizeWorkflowState = (state) => toTitleCase(state || '');

export const timelineStatusStyles = {
  completed: {
    dot: 'border-green-500 bg-green-500',
    pill: 'border-green-100 bg-green-50/80',
    badge: 'border-green-300 bg-green-50 text-green-700',
    label: 'text-green-700',
    connector: 'bg-green-200'
  },
  current: {
    dot: 'border-primary bg-primary',
    pill: 'border-primary/20 bg-primary/5',
    badge: 'border-primary bg-primary text-white',
    label: 'text-primary',
    connector: 'bg-primary/40'
  },
  upcoming: {
    dot: 'border-slate-300 bg-slate-200',
    pill: 'border-slate-200 bg-white',
    badge: 'border-slate-200 bg-slate-50 text-slate-500',
    label: 'text-slate-500',
    connector: 'bg-slate-200'
  }
};

export const normalizeStatus = (value) => String(value || '').toLowerCase();

export const isStageCompleted = (status) =>
  normalizeStatus(status).includes('complete') || normalizeStatus(status).includes('signed');

export const isStagePending = (status) => {
  const key = normalizeStatus(status);
  return key.includes('pending') || key.includes('progress') || key.includes('not started');
};

export const isStageOverdue = (stage, now = new Date()) => {
  if (!stage?.dueDate) return false;
  const due = new Date(stage.dueDate);
  if (Number.isNaN(due.getTime())) return false;
  return due < now && !isStageCompleted(stage.status);
};

export const formatEscalationSummary = (escalation) => {
  if (!escalation) return 'None';
  const { level, method, reason } = escalation;
  const parts = [];
  if (level) parts.push(level.replace(/_/g, ' '));
  if (method) parts.push(`via ${method}`);
  let summary = parts.join(' ');
  if (!summary && reason) summary = reason;
  if (summary && reason) summary = `${summary} – ${reason}`;
  return summary || 'None';
};

export const getLastReassignment = (stage) => {
  const history = Array.isArray(stage?.reassignments) ? stage.reassignments : [];
  return history.length ? history[history.length - 1] : null;
};

export const formatCycleDays = (startValue) => {
  if (!startValue) return '—';
  const start = new Date(startValue);
  if (Number.isNaN(start.getTime())) return '—';
  const diff = (Date.now() - start.getTime()) / (1000 * 60 * 60 * 24);
  return Math.max(diff, 0).toFixed(1);
};

export const buildDefaultWorkflow = (document = {}) => {
  const now = new Date().toISOString();
  return {
    lifecycleState: WORKFLOW_STATES.INTAKE,
    previousState: null,
    initializedAt: now,
    lastTransitionAt: now,
    stateHistory: [
      {
        id: 'history-initial',
        fromState: null,
        toState: WORKFLOW_STATES.INTAKE,
        changedAt: now,
        notes: 'Workflow initialised'
      }
    ],
    review: {
      stages: [
        {
          key: 'medical-review',
          name: 'Medical Review',
          role: 'Medical Monitor',
          assignees: ['Dr. Sarah Nguyen'],
          status: STAGE_STATUSES.PENDING,
          dueDate: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString(),
          comments: '',
          escalation: null,
          reassignments: [],
          history: []
        },
        {
          key: 'qa-review',
          name: 'Regulatory QA Review',
          role: 'Regulatory QA Manager',
          assignees: ['Helen Ortiz'],
          status: STAGE_STATUSES.PENDING,
          dueDate: new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString(),
          comments: '',
          escalation: null,
          reassignments: [],
          history: []
        }
      ]
    },
    approval: {
      stages: [
        {
          key: 'clinical-operations',
          name: 'Clinical Operations Approval',
          role: 'Principal Investigator',
          assignees: ['Michael Chen'],
          status: STAGE_STATUSES.PENDING,
          dueDate: new Date(Date.now() + 6 * 24 * 60 * 60 * 1000).toISOString(),
          meaning: 'Approve for site distribution',
          escalation: null,
          reassignments: [],
          history: []
        },
        {
          key: 'qa-release',
          name: 'Quality Release',
          role: 'QA Director',
          assignees: ['Priya Malhotra'],
          status: STAGE_STATUSES.PENDING,
          dueDate: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
          meaning: 'Release for controlled distribution',
          escalation: null,
          reassignments: [],
          history: []
        }
      ]
    },
    activation: {
      plannedEffectiveDate: null,
      actualEffectiveDate: null,
      distributionStatus: DISTRIBUTION_STATUSES.NOT_STARTED,
      trainingStatus: TRAINING_STATUSES.NOT_STARTED,
      controlledCopies: { issued: 0, acknowledged: 0, lastIssuedAt: null }
    },
    auditTrail: [
      {
        id: 'audit-intake',
        timestamp: now,
        actor: 'System',
        role: 'Workflow Engine',
        component: 'Workflow',
        action: 'Workflow initiated',
        details: 'Document entered intake stage'
      }
    ],
    documentContext: {
      effectiveDate: document.effectiveDate || '2025-10-05T09:00:00Z',
      retentionCategory: document.retentionCategory || 'ICH-GCP Essential Document',
      tmfZone: document.tmfZone || 'Zone 08 · Trial Management',
      artifact: document.artifact || '08.02.02 · Investigator Brochure',
      relatedRecords: [
        { type: 'Change Control', id: 'CC-2025-117', status: 'In Assessment' },
        { type: 'CAPA', id: 'CAPA-24-041', status: 'Monitoring' }
      ],
      controlledCopies: [
        { location: 'Site 101 · Boston', status: 'Active' },
        { location: 'QA Archive', status: 'Pending Acknowledgement' }
      ]
    },
    signatures: [
      {
        id: 'sig-1',
        name: 'Michael Chen',
        role: 'Principal Investigator',
        meaning: 'Approved for use in study',
        status: STAGE_STATUSES.PENDING,
        provider: 'Zoho Sign (queued)'
      },
      {
        id: 'sig-2',
        name: 'Priya Malhotra',
        role: 'QA Director',
        meaning: 'Quality release',
        status: STAGE_STATUSES.PENDING,
        provider: 'Zoho Sign (queued)'
      }
    ],
    compliance: {
      training: {
        required: true,
        assignments: 12,
        completed: 9,
        dueDate: '2025-10-10T00:00:00Z'
      },
      distribution: {
        controlledCopies: 6,
        pendingAcknowledgements: 2,
        lastRun: '2025-09-30T19:15:00Z'
      },
      regulatory: {
        tmfCompleteness: 98,
        lastInspection: '2025-09-28T13:00:00Z',
        issuesOpen: 1
      },
      validation: {
        aiValidation: 'Pass',
        metadataCompleteness: '98%',
        checksum: 'Verified'
      }
    },
    metrics: {
      reviewProgress: 0,
      approvalProgress: 0,
      overdueCount: 0,
      cycleTimeDays: 0,
      lastEvaluatedAt: now
    },
    revision: {
      changeControlId: null,
      clonedFromVersion: null,
      initiatedBy: null,
      initiatedAt: null,
      reason: null
    },
    archive: {
      archivedAt: null,
      archivedBy: null,
      bundleLocation: null,
      manifestUrl: null,
      reason: null
    }
  };
};

export const recalculateMetrics = (workflow) => {
  const now = new Date();
  const reviewStages = workflow.review?.stages || [];
  const approvalStages = workflow.approval?.stages || [];
  const reviewProgress = reviewStages.length
    ? Math.round((reviewStages.filter((stage) => isStageCompleted(stage.status)).length / reviewStages.length) * 100)
    : 0;
  const approvalProgress = approvalStages.length
    ? Math.round((approvalStages.filter((stage) => isStageCompleted(stage.status)).length / approvalStages.length) * 100)
    : 0;
  const overdueCount = [...reviewStages, ...approvalStages].filter((stage) => isStageOverdue(stage, now)).length;
  const firstHistory = workflow.stateHistory?.[0];
  const cycleTimeDays = firstHistory?.changedAt
    ? Math.max((now.getTime() - new Date(firstHistory.changedAt).getTime()) / (1000 * 60 * 60 * 24), 0)
    : 0;

  return {
    reviewProgress,
    approvalProgress,
    overdueCount,
    cycleTimeDays,
    lastEvaluatedAt: now.toISOString()
  };
};

