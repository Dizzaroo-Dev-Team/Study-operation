import { config } from '../config/env';

class GoogleAuthService {
    constructor() {
        this.isGoogleLoaded = false;
        this.googleAuth = null;
        this.initPromise = null;
        this.allowedDomains = ['dizzaroo.com']; // Restrict to dizzaroo.com domain
    }

    // Initialize Google Auth API
    async initGoogleAuth() {
        console.log('🔍 initGoogleAuth() called');
        
        if (this.initPromise) {
            console.log('🔍 Using existing init promise');
            return this.initPromise;
        }

        console.log('🔍 Creating new init promise');
        this.initPromise = new Promise((resolve, reject) => {
            // Load Google API script if not already loaded
            if (!window.google) {
                console.log('🔍 Google API not loaded, loading script...');
                const script = document.createElement('script');
                script.src = 'https://accounts.google.com/gsi/client';
                script.async = true;
                script.defer = true;
                script.onload = () => {
                    console.log('🔍 Google API script loaded successfully');
                    this.setupGoogleAuth().then(resolve).catch(reject);
                };
                script.onerror = () => {
                    console.error('🔍 Failed to load Google API script');
                    reject(new Error('Failed to load Google Auth script'));
                };
                document.head.appendChild(script);
            } else {
                console.log('🔍 Google API already loaded');
                this.setupGoogleAuth().then(resolve).catch(reject);
            }
        });

        return this.initPromise;
    }

    // Setup Google Auth after script is loaded
    async setupGoogleAuth() {
        console.log('🔍 setupGoogleAuth() called');
        try {
            return new Promise((resolve) => {
                console.log('🔍 Initializing Google Auth with config:', {
                    client_id: config.GOOGLE_OAUTH.CLIENT_ID,
                    callback: 'function',
                    auto_select: false,
                    cancel_on_tap_outside: true,
                    allowed_parent_origin: window.location.origin,
                    login_hint: '',
                    prompt_parent_id: 'google-signin-container'
                });
                
                window.google.accounts.id.initialize({
                    client_id: config.GOOGLE_OAUTH.CLIENT_ID,
                    callback: this.handleCredentialResponse.bind(this),
                    auto_select: false,
                    cancel_on_tap_outside: true,
                    // Add domain restriction
                    allowed_parent_origin: window.location.origin,
                    // Add login hint for better UX
                    login_hint: '',
                    // Add prompt for domain restriction
                    prompt_parent_id: 'google-signin-container'
                });
                console.log('🔍 Google Auth initialized successfully');
                this.isGoogleLoaded = true;
                resolve();
            });
        } catch (error) {
            console.error('🔍 Error setting up Google Auth:', error);
            throw error;
        }
    }

    // Handle Google credential response
    handleCredentialResponse(response) {
        if (this.onSignInCallback) {
            this.onSignInCallback(response);
        }
    }

    // Validate domain restriction
    validateDomain(email) {
        if (!email) return false;
        const domain = email.split('@')[1];
        return this.allowedDomains.includes(domain);
    }

    // Sign in with Google
    async signIn() {
        console.log('🔍 GoogleAuthService.signIn() called');
        
        if (!this.isGoogleLoaded) {
            console.log('🔍 Google Auth not loaded, initializing...');
            await this.initGoogleAuth();
        }

        console.log('🔍 Using popup approach directly');
        return this.showPopup();
    }

    // Show Google Sign-In popup as fallback
    async showPopup() {
        console.log('🔍 showPopup() called');
        
        if (!this.isGoogleLoaded) {
            console.log('🔍 Google Auth not loaded, initializing...');
            await this.initGoogleAuth();
        }

        console.log('🔍 Creating OAuth2 token client');
        return new Promise((resolve, reject) => {
            const client = window.google.accounts.oauth2.initTokenClient({
                client_id: config.GOOGLE_OAUTH.CLIENT_ID,
                scope: config.GOOGLE_OAUTH.SCOPE,
                callback: async (response) => {
                    console.log('🔍 OAuth2 callback received:', response);
                    if (response.access_token) {
                        try {
                            console.log('🔍 Getting user info with access token');
                            // Get user info using access token
                            const userInfo = await this.getUserInfo(response.access_token);
                            console.log('🔍 User info received:', userInfo);
                            
                            // Check domain restriction
                            if (!this.validateDomain(userInfo.email)) {
                                reject(new Error(`Access denied. Only @dizzaroo.com accounts are allowed. Your email: ${userInfo.email}`));
                                return;
                            }

                            resolve(userInfo);
                        } catch (error) {
                            console.error('🔍 Error in OAuth2 callback:', error);
                            reject(error);
                        }
                    } else {
                        console.error('🔍 No access token received');
                        reject(new Error('No access token received'));
                    }
                },
            });
            console.log('🔍 Requesting access token');
            client.requestAccessToken();
        });
    }

    // Get user information from Google API
    async getUserInfo(accessToken) {
        try {
            const response = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
                headers: {
                    'Authorization': `Bearer ${accessToken}`
                }
            });
            
            if (!response.ok) {
                throw new Error('Failed to fetch user info');
            }
            
            return await response.json();
        } catch (error) {
            console.error('Error fetching user info:', error);
            throw error;
        }
    }

    // Decode JWT token from Google
    decodeJWT(token) {
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            return JSON.parse(jsonPayload);
        } catch (error) {
            console.error('Error decoding JWT:', error);
            return null;
        }
    }

    // Sign out from Google
    async signOut() {
        if (this.isGoogleLoaded && window.google) {
            try {
                await window.google.accounts.id.disableAutoSelect();
            } catch (error) {
                console.error('Error signing out from Google:', error);
            }
        }
    }

    // Render Google Sign-In button
    renderButton(elementId, options = {}) {
        if (!this.isGoogleLoaded) {
            this.initGoogleAuth().then(() => {
                this._renderButtonInternal(elementId, options);
            });
        } else {
            this._renderButtonInternal(elementId, options);
        }
    }

    _renderButtonInternal(elementId, options) {
        const defaultOptions = {
            theme: 'outline',
            size: 'large',
            type: 'standard',
            shape: 'rectangular',
            text: 'signin_with',
            logo_alignment: 'left',
            width: '100%'
        };

        window.google.accounts.id.renderButton(
            document.getElementById(elementId),
            { ...defaultOptions, ...options }
        );
    }
}

// Create singleton instance
export const googleAuthService = new GoogleAuthService();
export default googleAuthService;
