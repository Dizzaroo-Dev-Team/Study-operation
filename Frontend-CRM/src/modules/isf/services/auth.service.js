// ISF Auth Service - CRM Integration Adapter
// Reads authentication state from whichever source the host CRM is using:
//   * hub mode  → in-memory sharedAuthService (no localStorage).
//   * local mode → existing CRM localStorage keys.

import sharedAuthService from '@/features/auth/services/sharedAuthService';

const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';

const IAM_AUTH_MODE =
  (import.meta.env && import.meta.env.VITE_IAM_AUTH_MODE) || 'local';
const HUB_MODE = IAM_AUTH_MODE === 'hub';

const authService = {
  getToken() {
    if (HUB_MODE) return sharedAuthService.getToken();
    return (
      localStorage.getItem(TOKEN_KEY) ||
      localStorage.getItem('token') ||
      localStorage.getItem('authToken') ||
      null
    );
  },

  getCurrentUser() {
    if (HUB_MODE) return sharedAuthService.getUser();
    const raw = localStorage.getItem(USER_KEY) || localStorage.getItem('user');
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  },

  isAuthenticated() {
    return !!this.getToken();
  },

  logout() {
    if (HUB_MODE) {
      sharedAuthService.clear();
      sharedAuthService.redirectToHubLogout();
      return;
    }
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

export { authService };
export default authService;
