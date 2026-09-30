/**
 * Too Fresh To Waste (TFTW) — Realtime WebSocket Client
 * Connects all three panels (Customer, Restaurant, Admin) to live events.
 */

(function () {
  const listeners = {};
  let socket = null;
  let reconnectAttempts = 0;
  let pingInterval = null;

  function getWsUrl() {
    const backendBase = window.TFTW_API_URL || 'http://127.0.0.1:8000';
    const wsProto = backendBase.startsWith('https') ? 'wss:' : 'ws:';
    const host = backendBase.replace(/^https?:\/\//, '');
    return `${wsProto}//${host}/ws/marketplace/`;
  }

  function emit(event, data) {
    if (listeners[event]) {
      listeners[event].forEach((cb) => {
        try {
          cb(data);
        } catch (e) {
          console.error(`Error in realtime listener for ${event}:`, e);
        }
      });
    }
  }

  function playAlertBeep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
      osc.frequency.setValueAtTime(880, ctx.currentTime + 0.1); // A5
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.3);
    } catch {
      // Audio context might be restricted before user gesture
    }
  }

  function showToast(title, message, type = 'info') {
    let container = document.getElementById('tftwToastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'tftwToastContainer';
      container.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 99999;
        display: flex;
        flex-direction: column;
        gap: 12px;
        pointer-events: none;
      `;
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.style.cssText = `
      pointer-events: auto;
      min-width: 280px;
      max-width: 380px;
      background: #FFFFFF;
      border-left: 4px solid var(--color-primary, #FF788D);
      border-radius: 12px;
      padding: 14px 16px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
      display: flex;
      align-items: flex-start;
      gap: 12px;
      transform: translateX(120%);
      transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
      font-family: inherit;
    `;

    const icon = type === 'success' ? '🎉' : type === 'warning' ? '⚠️' : '🔔';

    toast.innerHTML = `
      <div style="font-size: 20px; line-height: 1;">${icon}</div>
      <div style="flex: 1;">
        <div style="font-weight: 700; font-size: 14px; color: #242424; margin-bottom: 2px;">${title}</div>
        <div style="font-size: 13px; color: #666; line-height: 1.4;">${message}</div>
      </div>
      <button style="background: none; border: none; font-size: 16px; color: #aaa; cursor: pointer; padding: 0 2px;" onclick="this.parentElement.remove()">&times;</button>
    `;

    container.appendChild(toast);
    requestAnimationFrame(() => {
      toast.style.transform = 'translateX(0)';
    });

    setTimeout(() => {
      toast.style.transform = 'translateX(120%)';
      setTimeout(() => toast.remove(), 400);
    }, 4500);
  }

  const Realtime = {
    connect() {
      const url = getWsUrl();

      try {
        socket = new WebSocket(url);
      } catch (err) {
        console.warn('WebSocket init failed:', err);
        this.scheduleReconnect();
        return;
      }

      socket.onopen = () => {
        reconnectAttempts = 0;
        emit('connected');

        // Heartbeat ping
        clearInterval(pingInterval);
        pingInterval = setInterval(() => {
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'marketplace_broadcast' && payload.event) {
            emit(payload.event, payload.data);
            emit('*', payload);
          } else if (payload.event) {
            emit(payload.event, payload.data);
            emit('*', payload);
          }
        } catch (e) {
          console.error('Error handling WebSocket message:', e);
        }
      };

      socket.onclose = () => {
        clearInterval(pingInterval);
        emit('disconnected');
        this.scheduleReconnect();
      };

      socket.onerror = (err) => {
        console.warn('WebSocket connection error:', err);
        socket.close();
      };
    },

    scheduleReconnect() {
      reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts), 15000);
      setTimeout(() => this.connect(), delay);
    },

    on(event, callback) {
      if (!listeners[event]) listeners[event] = [];
      listeners[event].push(callback);
      return () => this.off(event, callback);
    },

    off(event, callback) {
      if (!listeners[event]) return;
      listeners[event] = listeners[event].filter((cb) => cb !== callback);
    },

    notify(title, message, type = 'info', playSound = true) {
      if (playSound) playAlertBeep();
      showToast(title, message, type);
    },
  };

  // Auto-connect on load
  if (typeof window !== 'undefined') {
    window.Realtime = Realtime;
    window.addEventListener('DOMContentLoaded', () => {
      Realtime.connect();
    });
  }
})();
