import axios from 'axios';
import { config } from '../config/config.js';
import sharedAuthService from '@/features/auth/services/sharedAuthService';

const IAM_AUTH_MODE =
  (import.meta.env && import.meta.env.VITE_IAM_AUTH_MODE) || 'local';
const HUB_MODE = IAM_AUTH_MODE === 'hub';

const api = axios.create({
  // config.API_URL already equals VITE_API_BASE which ends in /api — do NOT add /api again
  baseURL: config.API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token resolution mirrors src/lib/api.ts:
//   * hub mode  → in-memory session via sharedAuthService.
//   * local mode → existing localStorage flow.
api.interceptors.request.use(
  (cfg) => {
    const token = HUB_MODE
      ? sharedAuthService.getToken()
      : localStorage.getItem('auth_token') ||
        localStorage.getItem('token') ||
        localStorage.getItem('authToken');
    if (token) {
      cfg.headers.Authorization = 'Bearer ' + token;
    }
    return cfg;
  },
  (error) => Promise.reject(error)
);

// On 401 from CRM API: in hub mode, kick the user back through hub login;
// in local mode, clear the local JWT and bounce to root (existing behaviour).
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (HUB_MODE) {
        sharedAuthService.clear();
        sharedAuthService.redirectToHubLogin(window.location.href);
      } else {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
        window.location.href = '/';
      }
    }
    return Promise.reject(error);
  }
);

export default api;
