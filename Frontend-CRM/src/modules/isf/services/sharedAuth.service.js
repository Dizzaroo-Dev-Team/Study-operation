// Shared Authentication Service for Hub-Login-App Integration
// This service handles authentication between Hub-Login-App and Neurodoc-frontend

import { ROLES, hasPermission, getUserRoleInfo, canAccessTMFZone } from '../config/roles';
import { config } from '../config/env';
// Hub (SSO) session lives in module memory in the CRM shell, NOT localStorage.
// Imported so ISF can recover the user when running under hub-mode auth.
import crmHubAuth from '@/features/auth/services/sharedAuthService';

class SharedAuthService {
  constructor() {
    this.storageKey = 'platform_token';
    this.userStorageKey = 'platform_user';
    // CRM integration: CRM stores user/token under different keys
    this.crmTokenKey = 'auth_token';
    this.crmUserKey = 'auth_user';
    this.appId = 'neurodoc';
  }

  emailRoleMap = {
    'admin': ROLES.ADMIN,
    'study.manager': ROLES.STUDY_MANAGER,
    'study.monitor': ROLES.STUDY_MONITOR,
    'principal.investigator': ROLES.PRINCIPAL_INVESTIGATOR,
    'tmf.lead': ROLES.TMF_LEAD,
    'qa.reviewer': ROLES.QA_REVIEWER,
  };


  // Get current user from localStorage.
  // Tries the ISF Hub platform key first, then falls back to the CRM's auth_user key.
  getCurrentUser() {
    try {
      // ── 1. Try ISF Hub platform storage (original path) ──────────────────
      const userData = localStorage.getItem(this.userStorageKey);
      if (userData) {
        const user = JSON.parse(userData);
        const neurodocApp = user.applications?.find(app => app.appId === this.appId);
        const email = user.email || '';

        if (neurodocApp && neurodocApp.isActive) {
          return {
            ...user,
            neurodocRole: neurodocApp.role,
            neurodocPermissions: neurodocApp.permissions || [],
            isActive: neurodocApp.isActive,
            clinicalRole: this.mapToClinicalRole(neurodocApp.role, email)
          };
        }
      }

      // ── 2. CRM Integration fallback — read from auth_user ─────────────────
      // The CRM stores users with { role, is_privileged, name, email, … }
      // instead of the ISF Hub format.  Map CRM roles → ISF clinical roles.
      const crmUserData = localStorage.getItem(this.crmUserKey);
      if (crmUserData) {
        const crmUser = JSON.parse(crmUserData);
        if (crmUser && crmUser.email) {
          const crmRole = (crmUser.role || '').toUpperCase().trim();
          let clinicalRole;
          if (crmUser.is_privileged || ['ADMIN', 'SUPERADMIN', 'SYSTEM_ADMIN'].includes(crmRole)) {
            clinicalRole = ROLES.ADMIN;
          } else if (['STUDY_LEAD', 'LEAD', 'STUDY_MANAGER', 'SITE_MANAGER', 'SITE_LEAD'].includes(crmRole)) {
            clinicalRole = ROLES.STUDY_MANAGER;
          } else if (['MONITOR', 'CRA'].includes(crmRole)) {
            clinicalRole = ROLES.STUDY_MONITOR;
          } else if (['QA', 'QA_REVIEWER', 'QUALITY_ASSURANCE'].includes(crmRole)) {
            clinicalRole = ROLES.QA_REVIEWER;
          } else {
            // Any authenticated CRM user defaults to STUDY_MANAGER — full document access
            clinicalRole = ROLES.STUDY_MANAGER;
          }

          return {
            ...crmUser,
            // Provide ISF-expected fields so role detection in ISFDocumentList works
            neurodocRole: clinicalRole,
            clinicalRole,
            neurodocPermissions: [],
            isActive: true,
            // ISF Hub format aliases
            firstName: crmUser.name?.split(' ')[0] || '',
            lastName: crmUser.name?.split(' ').slice(1).join(' ') || '',
          };
        }
      }

      // ── 3. Hub (SSO) in-memory session fallback ───────────────────────────
      // In hub mode the CRM keeps {user, token} in module memory and purges the
      // legacy localStorage keys on load, so branches 1–2 find nothing. Recover
      // the user from the shared hub service and map its role → clinical role.
      const hubUser = crmHubAuth?.getUser?.();
      if (hubUser && hubUser.email) {
        const rawRole = (
          hubUser.role ||
          (Array.isArray(hubUser.hub_roles) ? hubUser.hub_roles[0] : hubUser.hub_roles) ||
          ''
        ).toString().toUpperCase().trim();
        const isPrivileged = hubUser.is_privileged === true || hubUser.is_privileged === 'true';
        let clinicalRole;
        if (isPrivileged || ['ADMIN', 'SUPERADMIN', 'SYSTEM_ADMIN'].includes(rawRole)) {
          clinicalRole = ROLES.ADMIN;
        } else if (['STUDY_LEAD', 'LEAD', 'STUDY_MANAGER', 'SITE_MANAGER', 'SITE_LEAD'].includes(rawRole)) {
          clinicalRole = ROLES.STUDY_MANAGER;
        } else if (['MONITOR', 'CRA'].includes(rawRole)) {
          clinicalRole = ROLES.STUDY_MONITOR;
        } else if (['QA', 'QA_REVIEWER', 'QUALITY_ASSURANCE'].includes(rawRole)) {
          clinicalRole = ROLES.QA_REVIEWER;
        } else {
          // Any authenticated hub user defaults to STUDY_MANAGER — full document access
          clinicalRole = ROLES.STUDY_MANAGER;
        }

        const name = hubUser.name || hubUser.displayName || '';
        return {
          ...hubUser,
          id: hubUser.id || hubUser.user_id || hubUser.userId,
          neurodocRole: clinicalRole,
          clinicalRole,
          neurodocPermissions: [],
          isActive: true,
          firstName: name.split(' ')[0] || '',
          lastName: name.split(' ').slice(1).join(' ') || '',
        };
      }

      return null;
    } catch (error) {
      console.error('Error getting current user:', error);
      return null;
    }
  }

  // Get authentication token — try ISF Hub key first, then CRM key
  getToken() {
    return localStorage.getItem(this.storageKey)
        || localStorage.getItem(this.crmTokenKey)
        || null;
  }

  // Check if user is authenticated
  isAuthenticated() {
    return !!(this.getToken() && this.getCurrentUser());
  }

  getRoleFromEmail(email) {
    if (!email) return ROLES.USER;

    // Remove domain
    const username = email.replace('@dizzaroo.com', '').toLowerCase();

    for (const key in this.emailRoleMap) {
      if (username.includes(key)) {
        console.log(`Found role mapping for key "${key}": ${this.emailRoleMap[key]}`);
        return this.emailRoleMap[key];
      }
    }
    return ROLES.USER;
  }

  // Map application roles to clinical trial roles
  mapToClinicalRole(appRole, email) {
    const roleMapping = {
      // Admin roles (backend uses ETMF_ADMIN and SYSTEM_ADMIN)
      'ADMIN': ROLES.ADMIN,
      'ETMF_ADMIN': ROLES.ADMIN,
      'SYSTEM_ADMIN': ROLES.ADMIN,
      'SUPER_ADMIN': ROLES.ADMIN,
      'PLATFORM_ADMIN': ROLES.ADMIN,
      
      // Study Management roles
      'STUDY_MANAGER': ROLES.STUDY_MANAGER,
      'PROJECT_MANAGER': ROLES.STUDY_MANAGER,
      
      // TMF Lead roles
      'TMF_LEAD': ROLES.TMF_LEAD,
      'FILING_LEVEL_MANAGER': ROLES.TMF_LEAD,
      
      // QA/Quality roles
      'QA_REVIEWER': ROLES.QA_REVIEWER,
      'QUALITY_ASSURANCE': ROLES.QA_REVIEWER,
      
      // Principal Investigator roles
      'PRINCIPAL_INVESTIGATOR': ROLES.PRINCIPAL_INVESTIGATOR,
      'INVESTIGATOR': ROLES.PRINCIPAL_INVESTIGATOR,
      'PI': ROLES.PRINCIPAL_INVESTIGATOR,
      
      // Study Monitor roles (CRA, Coordinators, etc.)
      'STUDY_MONITOR': ROLES.STUDY_MONITOR,
      'STUDY_COORDINATOR': ROLES.STUDY_MONITOR,
      'MONITOR_CRA': ROLES.STUDY_MONITOR,
      'COUNTRY_MANAGER': ROLES.STUDY_MONITOR,
      'CRO_PERSONNEL': ROLES.STUDY_MONITOR,

      // Default for regular users
      'USER': this.getRoleFromEmail(email),
      'FILING_LEVEL_UPLOADER': ROLES.STUDY_MONITOR,
      'FILING_LEVEL_VIEWER': ROLES.STUDY_MONITOR,
      'GENERAL_SITE_USER': ROLES.STUDY_MONITOR
    };
    
    return roleMapping[appRole] || ROLES.STUDY_MONITOR;
  }

  // Check if user has specific permission
  hasPermission(permission) {
    const user = this.getCurrentUser();
    if (!user) return false;
    
    // Check both clinical role permissions and application permissions
    const clinicalRole = user.clinicalRole;
    const hasClinicalPermission = hasPermission(clinicalRole, permission);
    
    // Also check if permission is explicitly granted in application permissions
    const hasAppPermission = user.neurodocPermissions?.includes(permission);
    
    return hasClinicalPermission || hasAppPermission;
  }

  // Check if user can access specific TMF zone
  canAccessTMFZone(zone) {
    const user = this.getCurrentUser();
    if (!user) return false;
    
    return canAccessTMFZone(user.clinicalRole, zone);
  }

  // Get user's role information
  getUserRoleInfo() {
    const user = this.getCurrentUser();
    if (!user) return null;
    
    return getUserRoleInfo(user.clinicalRole);
  }

  // Get user's available TMF zones
  getAvailableTMFZones() {
    const user = this.getCurrentUser();
    if (!user) return [];
    
    const roleInfo = this.getUserRoleInfo();
    if (!roleInfo) return [];
    
    // Return zones based on role
    switch (user.clinicalRole) {
      case ROLES.STUDY_MONITOR:
        return ['Zone 05 - Site Management', 'Zone 06 - Investigational Product', 'Zone 08 - Trial Management'];
      case ROLES.PRINCIPAL_INVESTIGATOR:
        return ['Zone 05 - Site Management', 'Zone 06 - Investigational Product', 'Zone 08 - Trial Management'];
      case ROLES.ADMIN:
        return ['All Zones'];
      default:
        return [];
    }
  }

  // Check if user can perform document actions
  canPerformDocumentAction(action, documentType = null) {
    const user = this.getCurrentUser();
    if (!user) return false;
    
    switch (action) {
      case 'view':
        return this.hasPermission('VIEW_DOCUMENTS');
      case 'upload':
        return this.hasPermission('UPLOAD_DOCUMENTS');
      case 'edit':
        return this.hasPermission('EDIT_DOCUMENTS');
      case 'delete':
        return this.hasPermission('DELETE_DOCUMENTS');
      case 'approve':
        return this.hasPermission('APPROVE_DOCUMENTS');
      case 'reject':
        return this.hasPermission('REJECT_DOCUMENTS');
      case 'sign':
        return this.hasPermission('E_SIGN');
      default:
        return false;
    }
  }

  // Get user's site restrictions
  getUserSiteRestrictions() {
    const user = this.getCurrentUser();
    if (!user) return null;
    
    // For STUDY_MONITOR and PI, they should only see their assigned sites
    if ([ROLES.STUDY_MONITOR, ROLES.PRINCIPAL_INVESTIGATOR].includes(user.clinicalRole)) {
      return {
        restricted: true,
        allowedSites: user.assignedSites || ['Current Site Only'],
        message: 'Access limited to assigned sites only'
      };
    }
    
    return { restricted: false };
  }

  // Logout (clear local storage)
  logout() {
    localStorage.removeItem(this.storageKey);
    localStorage.removeItem(this.userStorageKey);
    
    // Redirect to Hub-Login-App (environment-aware)
    const hubLoginUrl = this.getHubLoginUrl();
    window.location.href = `${hubLoginUrl}/login`;
  }

  // Get Hub-Login-App URL (environment-aware)
  getHubLoginUrl() {
    // Use config if available
    if (config && config.HUB_LOGIN_URL) {
      return config.HUB_LOGIN_URL;
    }
    
    // Fallback: determine URL based on current environment
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      return 'http://localhost:5000';
    }
    
    // Production fallback
    return 'https://hub-app.dizzaroo.com';
  }

  // Get user display information
  getUserDisplayInfo() {
    const user = this.getCurrentUser();
    if (!user) return null;
    
    return {
      name: `${user.firstName || ''} ${user.lastName || ''}`.trim() || user.email,
      email: user.email,
      role: user.clinicalRole,
      roleDisplayName: this.getUserRoleInfo()?.name || 'Unknown Role',
      avatar: user.picture || null,
      organization: user.organization || 'Clinical Trial Platform'
    };
  }

  // Check if user is admin
  isAdmin() {
    const user = this.getCurrentUser();
    return user?.clinicalRole === ROLES.ADMIN;
  }

  // Check if user is study monitor
  isStudyMonitor() {
    const user = this.getCurrentUser();
    return user?.clinicalRole === ROLES.STUDY_MONITOR;
  }

  // Check if user is principal investigator
  isPrincipalInvestigator() {
    const user = this.getCurrentUser();
    return user?.clinicalRole === ROLES.PRINCIPAL_INVESTIGATOR;
  }

  // Get demo user data for testing
  getDemoUser(role = ROLES.STUDY_MONITOR) {
    const demoUsers = {
      [ROLES.STUDY_MONITOR]: {
        id: 'default-study-id-monitor',
        email: 'study.monitor@dizzaroo.com',
        firstName: 'Sarah',
        lastName: 'Johnson',
        applications: [{
          appId: 'neurodoc',
          role: 'STUDY_COORDINATOR',
          permissions: ['READ', 'WRITE'],
          isActive: true
        }],
        clinicalRole: ROLES.STUDY_MONITOR,
        assignedSites: ['Site 101', 'Site 102']
      },
      [ROLES.PRINCIPAL_INVESTIGATOR]: {
        id: 'demo-pi',
        email: 'principal.investigator@dizzaroo.com',
        firstName: 'Dr. Michael',
        lastName: 'Chen',
        applications: [{
          appId: 'neurodoc',
          role: 'INVESTIGATOR',
          permissions: ['READ', 'WRITE', 'SIGN'],
          isActive: true
        }],
        clinicalRole: ROLES.PRINCIPAL_INVESTIGATOR,
        assignedSites: ['Site 101']
      },
      [ROLES.ADMIN]: {
        id: 'demo-admin',
        email: 'admin@dizzaroo.com',
        firstName: 'Admin',
        lastName: 'User',
        applications: [{
          appId: 'neurodoc',
          role: 'ADMIN',
          permissions: ['READ', 'WRITE', 'MANAGE_USERS'],
          isActive: true
        }],
        clinicalRole: ROLES.ADMIN
      }
    };
    
    return demoUsers[role] || demoUsers[ROLES.STUDY_MONITOR];
  }

  // Set demo user (for testing purposes)
  setDemoUser(role = ROLES.STUDY_MONITOR) {
    const demoUser = this.getDemoUser(role);
    localStorage.setItem(this.userStorageKey, JSON.stringify(demoUser));
    localStorage.setItem(this.storageKey, 'demo-token-' + Date.now());
    return demoUser;
  }
}

// Create singleton instance
const sharedAuthService = new SharedAuthService();

export default sharedAuthService;

