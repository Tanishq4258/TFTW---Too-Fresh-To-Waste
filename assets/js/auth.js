/* =============================================
   TOO FRESH TO WASTE — Auth API Client
   Handles all communication with the Django backend.

   Backend URL: http://127.0.0.1:8000
   Override by setting window.TFTW_API_URL before this script loads.
   ============================================= */

const API_BASE = (window.TFTW_API_URL || 'http://127.0.0.1:8000') + '/api/auth';

// ─── Token Storage ────────────────────────────────────────────────────────────

const Auth = {
  // ── Storage helpers ────────────────────────────────────────────────────────

  saveTokens(access, refresh) {
    localStorage.setItem('tftw_access', access);
    localStorage.setItem('tftw_refresh', refresh);
  },

  getAccessToken() {
    return localStorage.getItem('tftw_access');
  },

  getRefreshToken() {
    return localStorage.getItem('tftw_refresh');
  },

  clearTokens() {
    localStorage.removeItem('tftw_access');
    localStorage.removeItem('tftw_refresh');
    localStorage.removeItem('tftw_user');
  },

  saveUser(user) {
    localStorage.setItem('tftw_user', JSON.stringify(user));
  },

  getUser() {
    try {
      return JSON.parse(localStorage.getItem('tftw_user'));
    } catch {
      return null;
    }
  },

  isLoggedIn() {
    return !!this.getAccessToken();
  },

  // ── HTTP helpers ───────────────────────────────────────────────────────────

  async _request(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };

    const accessToken = this.getAccessToken();
    if (accessToken) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });

    let data = null;
    try {
      data = await response.json();
    } catch {
      data = {};
    }

    return { ok: response.ok, status: response.status, data };
  },

  // ── Auth actions ───────────────────────────────────────────────────────────

  /**
   * Register a new user.
   * @param {object} payload - { first_name, last_name, email, password, confirm_password, account_type }
   */
  async register(payload) {
    const res = await this._request('/register/', {
      method: 'POST',
      body: payload,
    });

    if (res.ok) {
      this.saveTokens(res.data.tokens.access, res.data.tokens.refresh);
      this.saveUser(res.data.user);
    }

    return res;
  },

  /**
   * Log in an existing user.
   * @param {string} email
   * @param {string} password
   */
  async login(email, password) {
    const res = await this._request('/login/', {
      method: 'POST',
      body: { email, password },
    });

    if (res.ok) {
      this.saveTokens(res.data.tokens.access, res.data.tokens.refresh);
      this.saveUser(res.data.user);
    }

    return res;
  },

  /**
   * Log out: blacklist the refresh token on the server, then clear local storage.
   */
  async logout() {
    const refresh = this.getRefreshToken();
    if (refresh) {
      // Best-effort — clear locally even if request fails
      await this._request('/logout/', {
        method: 'POST',
        body: { refresh },
      }).catch(() => {});
    }
    this.clearTokens();
  },

  /**
   * Fetch the currently logged-in user's profile from the server.
   * Attempts a token refresh if the access token has expired.
   */
  async me() {
    let res = await this._request('/me/', { method: 'GET' });

    if (res.status === 401) {
      // Try to refresh the access token
      const refreshed = await this.refreshAccessToken();
      if (refreshed) {
        res = await this._request('/me/', { method: 'GET' });
      }
    }

    if (res.ok) {
      this.saveUser(res.data);
    }

    return res;
  },

  /**
   * Use the stored refresh token to get a new access token.
   * Returns true on success, false on failure.
   */
  async refreshAccessToken() {
    const refresh = this.getRefreshToken();
    if (!refresh) return false;

    const res = await this._request('/token/refresh/', {
      method: 'POST',
      body: { refresh },
    });

    if (res.ok && res.data.access) {
      localStorage.setItem('tftw_access', res.data.access);
      if (res.data.refresh) {
        localStorage.setItem('tftw_refresh', res.data.refresh);
      }
      return true;
    }

    // Refresh token expired — force logout
    this.clearTokens();
    return false;
  },
};

// Make Auth globally available
window.Auth = Auth;
