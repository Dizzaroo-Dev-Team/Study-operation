// Role-Based Access Control Configuration for Clinical Trial Platform
// Based on demo requirements for STUDY MONITOR and PRINCIPAL INVESTIGATOR roles

export const ROLES = {
  STUDY_MONITOR: 'STUDY_MONITOR',
  PRINCIPAL_INVESTIGATOR: 'PRINCIPAL_INVESTIGATOR',
  ADMIN: 'ADMIN',
  STUDY_MANAGER: 'STUDY_MANAGER',
  TMF_LEAD: 'TMF_LEAD',
  QA_REVIEWER: 'QA_REVIEWER'
};

export const PERMISSIONS = {
  // Document permissions
  VIEW_DOCUMENTS: 'VIEW_DOCUMENTS',
  UPLOAD_DOCUMENTS: 'UPLOAD_DOCUMENTS',
  EDIT_DOCUMENTS: 'EDIT_DOCUMENTS',
  DELETE_DOCUMENTS: 'DELETE_DOCUMENTS',
  APPROVE_DOCUMENTS: 'APPROVE_DOCUMENTS',
  REJECT_DOCUMENTS: 'REJECT_DOCUMENTS',
  
  // TMF specific permissions
  VIEW_TMF_REFERENCE: 'VIEW_TMF_REFERENCE',
  VIEW_SITE_DOCUMENTS: 'VIEW_SITE_DOCUMENTS',
  VIEW_REGULATORY_PACKAGE: 'VIEW_REGULATORY_PACKAGE',
  VIEW_SITE_PACKAGE: 'VIEW_SITE_PACKAGE',
  
  // Review and QC permissions
  VIEW_QC_STATUS: 'VIEW_QC_STATUS',
  EDIT_QC_STATUS: 'EDIT_QC_STATUS',
  VIEW_AUDIT_TRAIL: 'VIEW_AUDIT_TRAIL',
  
  // Signature permissions
  E_SIGN: 'E_SIGN',
  VIEW_ESIGNATURES: 'VIEW_ESIGNATURES',
  
  // Reports and dashboards
  VIEW_REPORTS: 'VIEW_REPORTS',
  VIEW_DASHBOARDS: 'VIEW_DASHBOARDS',
  
  // Administrative permissions
  MANAGE_USERS: 'MANAGE_USERS',
  MANAGE_STUDIES: 'MANAGE_STUDIES',
  MANAGE_SITES: 'MANAGE_SITES'
};

// Role-based permission mapping
export const ROLE_PERMISSIONS = {
  [ROLES.STUDY_MONITOR]: {
    name: 'Study Monitor (CRO/Sponsor Level Employee)',
    description: 'CRA with site-level TMF document access and monitoring capabilities',
    permissions: [
      // Site-Level TMF Documents (eISF copies)
      PERMISSIONS.VIEW_SITE_DOCUMENTS,
      PERMISSIONS.UPLOAD_DOCUMENTS,
      
      // Monitoring Visit Reports
      PERMISSIONS.VIEW_DOCUMENTS,
      PERMISSIONS.UPLOAD_DOCUMENTS,
      PERMISSIONS.EDIT_DOCUMENTS, // own documents only
      
      // Quality Review / QC Status
      PERMISSIONS.VIEW_QC_STATUS,
      
      // Audit Trail / Version History
      PERMISSIONS.VIEW_AUDIT_TRAIL,
      
      // Metadata Fields
      PERMISSIONS.EDIT_DOCUMENTS, // for uploads
      
      // eSignatures / Approvals
      PERMISSIONS.VIEW_ESIGNATURES,
      
      // Reports and Dashboards
      PERMISSIONS.VIEW_REPORTS, // limited
      PERMISSIONS.VIEW_DASHBOARDS, // limited
      
      // Regulatory Package
      PERMISSIONS.VIEW_REGULATORY_PACKAGE,
      
      // Site Package
      PERMISSIONS.VIEW_SITE_PACKAGE
    ],
    restrictions: [
      'Cannot access sponsor-internal documents',
      'Cannot perform QC approval',
      'Cannot access other site documents',
      'Limited to assigned sites only'
    ]
  },
  
  [ROLES.PRINCIPAL_INVESTIGATOR]: {
    name: 'Principal Investigator (Site Level)',
    description: 'Site-level PI with document approval and signature capabilities',
    permissions: [
      // Site-Level Documents (Investigator Folder)
      PERMISSIONS.VIEW_SITE_DOCUMENTS,
      PERMISSIONS.APPROVE_DOCUMENTS,
      PERMISSIONS.E_SIGN,
      
      // Study Correspondence
      PERMISSIONS.VIEW_DOCUMENTS,
      
      // Monitoring Visit Reports & Follow-up Letters
      PERMISSIONS.VIEW_DOCUMENTS,
      
      // Regulatory Package
      PERMISSIONS.VIEW_REGULATORY_PACKAGE,
      PERMISSIONS.UPLOAD_DOCUMENTS, // selected docs if delegated
      
      // PI Signature Items
      PERMISSIONS.E_SIGN,
      PERMISSIONS.VIEW_ESIGNATURES,
      
      // Training Documentation
      PERMISSIONS.VIEW_DOCUMENTS,
      PERMISSIONS.UPLOAD_DOCUMENTS, // optional
      
      // Safety and SAE Documentation
      PERMISSIONS.VIEW_DOCUMENTS,
      PERMISSIONS.UPLOAD_DOCUMENTS, // optional
      
      // Site Package
      PERMISSIONS.VIEW_SITE_PACKAGE,
      PERMISSIONS.E_SIGN, // for site package
      
      // Reports and Dashboards
      PERMISSIONS.VIEW_REPORTS, // own site only
      PERMISSIONS.VIEW_DASHBOARDS // own site only
    ],
    restrictions: [
      'Cannot access sponsor-internal or other-site documents',
      'Limited to site-related TMF sections (Zone 05, 06, 08)',
      'Cannot perform QC or document lifecycle management',
      'Cannot access other site data'
    ]
  },
  
  [ROLES.ADMIN]: {
    name: 'System Administrator',
    description: 'Full system access with administrative privileges',
    permissions: Object.values(PERMISSIONS),
    restrictions: []
  },
  
  [ROLES.STUDY_MANAGER]: {
    name: 'Study Manager',
    description: 'Study-level management with oversight capabilities',
    permissions: [
      PERMISSIONS.VIEW_DOCUMENTS,
      PERMISSIONS.APPROVE_DOCUMENTS,
      PERMISSIONS.REJECT_DOCUMENTS,
      PERMISSIONS.VIEW_QC_STATUS,
      PERMISSIONS.EDIT_QC_STATUS,
      PERMISSIONS.VIEW_AUDIT_TRAIL,
      PERMISSIONS.VIEW_REPORTS,
      PERMISSIONS.VIEW_DASHBOARDS,
      PERMISSIONS.MANAGE_STUDIES,
      PERMISSIONS.VIEW_TMF_REFERENCE,
      PERMISSIONS.VIEW_REGULATORY_PACKAGE,
      PERMISSIONS.VIEW_SITE_PACKAGE
    ],
    restrictions: []
  },
  
  [ROLES.TMF_LEAD]: {
    name: 'TMF Lead',
    description: 'TMF-specific leadership role with document oversight',
    permissions: [
      PERMISSIONS.VIEW_DOCUMENTS,
      PERMISSIONS.APPROVE_DOCUMENTS,
      PERMISSIONS.REJECT_DOCUMENTS,
      PERMISSIONS.VIEW_QC_STATUS,
      PERMISSIONS.EDIT_QC_STATUS,
      PERMISSIONS.VIEW_AUDIT_TRAIL,
      PERMISSIONS.VIEW_TMF_REFERENCE,
      PERMISSIONS.VIEW_REGULATORY_PACKAGE,
      PERMISSIONS.VIEW_SITE_PACKAGE,
      PERMISSIONS.VIEW_REPORTS,
      PERMISSIONS.VIEW_DASHBOARDS
    ],
    restrictions: []
  },
  
  [ROLES.QA_REVIEWER]: {
    name: 'QA Reviewer',
    description: 'Quality assurance reviewer with QC capabilities',
    permissions: [
      PERMISSIONS.VIEW_DOCUMENTS,
      PERMISSIONS.VIEW_QC_STATUS,
      PERMISSIONS.EDIT_QC_STATUS,
      PERMISSIONS.APPROVE_DOCUMENTS,
      PERMISSIONS.REJECT_DOCUMENTS,
      PERMISSIONS.VIEW_AUDIT_TRAIL,
      PERMISSIONS.VIEW_REPORTS,
      PERMISSIONS.VIEW_DASHBOARDS
    ],
    restrictions: []
  }
};

// TMF Zone access mapping
export const TMF_ZONE_ACCESS = {
  [ROLES.STUDY_MONITOR]: {
    allowedZones: ['Zone 05', 'Zone 06', 'Zone 08'], // Site Management, Investigational Product, Trial Management
    restrictedZones: ['Zone 01', 'Zone 02', 'Zone 03', 'Zone 04', 'Zone 07'] // Core sponsor documents
  },
  [ROLES.PRINCIPAL_INVESTIGATOR]: {
    allowedZones: ['Zone 05', 'Zone 06', 'Zone 08'], // Site-specific zones only
    restrictedZones: ['Zone 01', 'Zone 02', 'Zone 03', 'Zone 04', 'Zone 07']
  },
  [ROLES.ADMIN]: {
    allowedZones: 'ALL',
    restrictedZones: []
  }
};

// Helper functions
export const hasPermission = (userRole, permission) => {
  const rolePermissions = ROLE_PERMISSIONS[userRole];
  return rolePermissions ? rolePermissions.permissions.includes(permission) : false;
};

export const hasAnyPermission = (userRole, permissions) => {
  return permissions.some(permission => hasPermission(userRole, permission));
};

export const hasAllPermissions = (userRole, permissions) => {
  return permissions.every(permission => hasPermission(userRole, permission));
};

export const canAccessTMFZone = (userRole, zone) => {
  const access = TMF_ZONE_ACCESS[userRole];
  if (!access) return false;
  
  if (access.allowedZones === 'ALL') return true;
  return access.allowedZones.includes(zone);
};

export const getUserRoleInfo = (userRole) => {
  return ROLE_PERMISSIONS[userRole] || null;
};

export const getAvailableRoles = () => {
  return Object.keys(ROLE_PERMISSIONS).map(role => ({
    value: role,
    label: ROLE_PERMISSIONS[role].name,
    description: ROLE_PERMISSIONS[role].description
  }));
};

