/**
 * Too Fresh To Waste (TFTW) — Marketplace API Client
 * Centralized HTTP communication with the backend.
 */

(function () {
  const BACKEND_URL = window.TFTW_API_URL || 'http://127.0.0.1:8000';
  const API_ROOT = `${BACKEND_URL}/api`;

  const API = {
    BASE_URL: BACKEND_URL,

    async request(path, options = {}) {
      const url = `${API_ROOT}${path}`;
      const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      };

      const token = window.Auth ? window.Auth.getAccessToken() : localStorage.getItem('tftw_access');
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      let response;
      try {
        response = await fetch(url, {
          ...options,
          headers,
          body: options.body ? JSON.stringify(options.body) : undefined,
        });
      } catch (err) {
        console.error(`Network error requesting ${url}:`, err);
        return { ok: false, status: 0, error: 'Network connection failed' };
      }

      // Handle token expiration (401)
      if (response.status === 401 && window.Auth && !options._retry) {
        const refreshed = await window.Auth.refreshAccessToken();
        if (refreshed) {
          options._retry = true;
          return this.request(path, options);
        }
      }

      let data = null;
      try {
        data = await response.json();
      } catch {
        data = {};
      }

      return {
        ok: response.ok,
        status: response.status,
        data,
      };
    },

    // ─── Listings ─────────────────────────────────────────────────────────────

    async getListings(params = {}) {
      const qs = new URLSearchParams();
      if (params.category && params.category !== 'all') qs.set('category', params.category);
      if (params.search) qs.set('search', params.search);
      if (params.city) qs.set('city', params.city);
      if (params.max_price) qs.set('max_price', params.max_price);
      if (params.sort) qs.set('sort', params.sort);

      const query = qs.toString() ? `?${qs.toString()}` : '';
      return this.request(`/listings/${query}`);
    },

    async getListing(id) {
      return this.request(`/listings/${id}/`);
    },

    async createListing(listingData) {
      return this.request('/listings/', {
        method: 'POST',
        body: listingData,
      });
    },

    async updateListing(id, updates) {
      return this.request(`/listings/${id}/`, {
        method: 'PATCH',
        body: updates,
      });
    },

    async deleteListing(id) {
      return this.request(`/listings/${id}/`, {
        method: 'DELETE',
      });
    },

    async getMyListings() {
      return this.request('/listings/my/');
    },

    // ─── Bookings ─────────────────────────────────────────────────────────────

    async getBookings(statusFilter) {
      const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
      return this.request(`/bookings/${q}`);
    },

    async getBooking(id) {
      return this.request(`/bookings/${id}/`);
    },

    async createBooking(bookingData) {
      return this.request('/bookings/', {
        method: 'POST',
        body: bookingData,
      });
    },

    async updateBookingStatus(id, newStatus, cancellationReason = '') {
      return this.request(`/bookings/${id}/status/`, {
        method: 'PATCH',
        body: {
          status: newStatus,
          cancellation_reason: cancellationReason,
        },
      });
    },

    // ─── Restaurants ──────────────────────────────────────────────────────────

    async getRestaurants(city, search) {
      const qs = new URLSearchParams();
      if (city) qs.set('city', city);
      if (search) qs.set('search', search);
      const query = qs.toString() ? `?${qs.toString()}` : '';
      return this.request(`/restaurants/${query}`);
    },

    async getRestaurant(id) {
      return this.request(`/restaurants/${id}/`);
    },

    async getMyRestaurantProfile() {
      return this.request('/restaurants/me/');
    },

    // ─── Notifications ────────────────────────────────────────────────────────

    async getNotifications() {
      return this.request('/notifications/');
    },

    async markNotificationRead(id) {
      return this.request(`/notifications/${id}/read/`, { method: 'PATCH' });
    },

    async markAllNotificationsRead() {
      return this.request('/notifications/read-all/', { method: 'POST' });
    },

    // ─── Admin Endpoints ──────────────────────────────────────────────────────

    async getAdminDashboard() {
      return this.request('/admin/dashboard/');
    },

    async getAdminUsers(search, role) {
      const qs = new URLSearchParams();
      if (search) qs.set('search', search);
      if (role) qs.set('role', role);
      const query = qs.toString() ? `?${qs.toString()}` : '';
      return this.request(`/admin/users/${query}`);
    },

    async toggleUserStatus(userId, isActive) {
      return this.request(`/admin/users/${userId}/status/`, {
        method: 'PATCH',
        body: { is_active: isActive },
      });
    },

    async toggleRestaurantStatus(restaurantId, newStatus) {
      return this.request(`/admin/restaurants/${restaurantId}/status/`, {
        method: 'PATCH',
        body: { status: newStatus },
      });
    },

    async getAdminAnalytics() {
      return this.request('/admin/analytics/');
    },
  };

  window.API = API;
})();
