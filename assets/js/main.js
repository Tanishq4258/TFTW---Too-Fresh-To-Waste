/* =============================================
   TOO FRESH TO WASTE — Main JavaScript
   ============================================= */

// ---- Navbar scroll behavior ----
(function initNavbar() {
  const navbar = document.getElementById('navbar');
  if (!navbar) return;

  let lastScroll = 0;
  window.addEventListener('scroll', () => {
    const current = window.scrollY;
    if (current > 20) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
    lastScroll = current;
  }, { passive: true });
})();

// ---- Hamburger / Mobile Nav ----
(function initMobileNav() {
  const hamburger = document.getElementById('hamburger');
  const mobileNav = document.getElementById('mobileNav');
  if (!hamburger || !mobileNav) return;

  hamburger.addEventListener('click', () => {
    const isOpen = hamburger.classList.toggle('open');
    mobileNav.classList.toggle('open', isOpen);
    hamburger.setAttribute('aria-expanded', isOpen);
    document.body.style.overflow = isOpen ? 'hidden' : '';
  });

  // Close on link click
  mobileNav.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      hamburger.classList.remove('open');
      mobileNav.classList.remove('open');
      hamburger.setAttribute('aria-expanded', 'false');
      document.body.style.overflow = '';
    });
  });

  // Close on outside click
  document.addEventListener('click', (e) => {
    if (!hamburger.contains(e.target) && !mobileNav.contains(e.target)) {
      hamburger.classList.remove('open');
      mobileNav.classList.remove('open');
      hamburger.setAttribute('aria-expanded', 'false');
      document.body.style.overflow = '';
    }
  });
})();

// ---- Scroll Reveal Animations ----
(function initScrollReveal() {
  const elements = document.querySelectorAll('.reveal');
  if (!elements.length) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        // Stagger delay for siblings
        const siblings = [...entry.target.parentElement.children].filter(el => el.classList.contains('reveal'));
        const index = siblings.indexOf(entry.target);
        setTimeout(() => {
          entry.target.classList.add('visible');
        }, index * 80);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

  elements.forEach(el => observer.observe(el));
})();

// ---- Counter Animation for Stats ----
(function initCounters() {
  const counters = document.querySelectorAll('[data-count]');
  if (!counters.length) return;

  const easeOutQuart = t => 1 - Math.pow(1 - t, 4);

  function animateCounter(el) {
    const target = el.getAttribute('data-count');
    const suffix = el.getAttribute('data-suffix') || '';
    const prefix = el.getAttribute('data-prefix') || '';
    const duration = 2000;
    const start = performance.now();
    const isFloat = target.includes('.');
    const numTarget = parseFloat(target);

    function update(now) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = easeOutQuart(progress);
      const current = eased * numTarget;
      el.textContent = prefix + (isFloat ? current.toFixed(1) : Math.round(current).toLocaleString('en-IN')) + suffix;
      if (progress < 1) requestAnimationFrame(update);
    }

    requestAnimationFrame(update);
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        animateCounter(entry.target);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });

  counters.forEach(c => observer.observe(c));
})();

// ---- Smooth scrolling for anchor links ----
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function (e) {
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      e.preventDefault();
      const navbarHeight = document.getElementById('navbar')?.offsetHeight || 72;
      const top = target.getBoundingClientRect().top + window.scrollY - navbarHeight - 16;
      window.scrollTo({ top, behavior: 'smooth' });
    }
  });
});

// =============================================
// AUTH FORMS LOGIC
// =============================================

// ---- Password visibility toggle ----
function initPasswordToggles() {
  document.querySelectorAll('[data-toggle-password]').forEach(btn => {
    btn.addEventListener('click', function () {
      const targetId = this.getAttribute('data-toggle-password');
      const input = document.getElementById(targetId);
      if (!input) return;
      const isText = input.type === 'text';
      input.type = isText ? 'password' : 'text';
      this.innerHTML = isText ? getEyeIcon() : getEyeOffIcon();
    });
  });
}

function getEyeIcon() {
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
    <circle cx="12" cy="12" r="3"/>
  </svg>`;
}

function getEyeOffIcon() {
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
    <line x1="1" y1="1" x2="23" y2="23"/>
  </svg>`;
}

// ---- Password Strength ----
function checkPasswordStrength(password) {
  let score = 0;
  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (/[A-Z]/.test(password)) score++;
  if (/[0-9]/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;
  return score;
}

function updateStrengthBar(password, barId, labelId) {
  const bar = document.getElementById(barId);
  const label = document.getElementById(labelId);
  if (!bar || !label) return;

  const segments = bar.querySelectorAll('.strength-segment');
  const score = checkPasswordStrength(password);

  const levels = [
    { min: 0, max: 0, label: '', cls: '' },
    { min: 1, max: 2, label: 'Weak', cls: 'weak' },
    { min: 2, max: 3, label: 'Fair', cls: 'fair' },
    { min: 3, max: 4, label: 'Good', cls: 'good' },
    { min: 5, max: 5, label: 'Strong', cls: 'good' },
  ];

  segments.forEach((seg, i) => {
    seg.className = 'strength-segment';
    if (password.length > 0 && i < Math.ceil(score * segments.length / 5)) {
      const cls = score <= 2 ? 'weak' : score <= 3 ? 'fair' : 'good';
      seg.classList.add(cls);
    }
  });

  if (password.length === 0) {
    label.textContent = '';
  } else if (score <= 2) {
    label.textContent = 'Weak password';
    label.style.color = '#EF4444';
  } else if (score <= 3) {
    label.textContent = 'Fair password';
    label.style.color = '#F39C12';
  } else {
    label.textContent = 'Strong password';
    label.style.color = '#2ECC71';
  }
}

// ---- Email validation ----
function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// ---- Show / Hide form error ----
function showError(inputId, message) {
  const input = document.getElementById(inputId);
  const errorEl = document.getElementById(inputId + 'Error');
  if (input) {
    input.classList.add('error');
    input.classList.remove('success');
  }
  if (errorEl) {
    const span = errorEl.querySelector('span');
    if (span) span.textContent = message;
    else errorEl.textContent = message;
    errorEl.classList.add('show');
  }
}

function clearError(inputId) {
  const input = document.getElementById(inputId);
  const errorEl = document.getElementById(inputId + 'Error');
  if (input) {
    input.classList.remove('error');
  }
  if (errorEl) {
    errorEl.classList.remove('show');
  }
}

function markSuccess(inputId) {
  const input = document.getElementById(inputId);
  if (input) {
    input.classList.remove('error');
    input.classList.add('success');
  }
}

// ---- LOGIN FORM ----
function initLoginForm() {
  const form = document.getElementById('loginForm');
  if (!form) return;

  const emailInput = document.getElementById('loginEmail');
  const passwordInput = document.getElementById('loginPassword');
  const submitBtn = document.getElementById('loginSubmit');

  // ── Wire "Forgot password?" link ──
  const forgotLink = form.closest('.auth-form-inner')?.querySelector('.form-forgot') ||
                     document.querySelector('.form-forgot');
  if (forgotLink) {
    forgotLink.href = 'forgot-password.html';
  }

  // ── Wire Google Sign-In button ──
  const googleLoginBtn = document.getElementById('googleLoginBtn');
  if (googleLoginBtn) {
    googleLoginBtn.addEventListener('click', async () => {
      googleLoginBtn.disabled = true;
      googleLoginBtn.textContent = 'Connecting to Google…';
      if (window.Auth) {
        const result = await window.Auth.initiateGoogleLogin();
        // If we get here, it means the redirect didn't happen (error)
        if (result && !result.ok) {
          googleLoginBtn.disabled = false;
          googleLoginBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
          </svg> Continue with Google`;
          showError('loginEmail', result.error || 'Google Sign-In is not available right now.');
        }
      }
    });
  }

  if (emailInput) {
    emailInput.addEventListener('blur', () => {
      const val = emailInput.value.trim();
      if (!val) {
        showError('loginEmail', 'Email is required.');
      } else if (!isValidEmail(val)) {
        showError('loginEmail', 'Please enter a valid email address.');
      } else {
        clearError('loginEmail');
        markSuccess('loginEmail');
      }
    });
    emailInput.addEventListener('input', () => clearError('loginEmail'));
  }

  if (passwordInput) {
    passwordInput.addEventListener('blur', () => {
      if (!passwordInput.value) {
        showError('loginPassword', 'Password is required.');
      } else {
        clearError('loginPassword');
      }
    });
    passwordInput.addEventListener('input', () => clearError('loginPassword'));
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    let valid = true;

    const email = emailInput?.value.trim() || '';
    const password = passwordInput?.value || '';

    if (!email) { showError('loginEmail', 'Email is required.'); valid = false; }
    else if (!isValidEmail(email)) { showError('loginEmail', 'Please enter a valid email address.'); valid = false; }
    else { clearError('loginEmail'); }

    if (!password) { showError('loginPassword', 'Password is required.'); valid = false; }
    else { clearError('loginPassword'); }

    if (!valid) return;

    submitBtn.classList.add('btn-loading');
    submitBtn.disabled = true;

    try {
      const res = await window.Auth.login(email, password);

      if (res.ok) {
        const u = res.data?.user || window.Auth.getUser();



        // Normal success — show success banner then redirect
        const successEl = document.getElementById('loginSuccess');
        if (successEl) successEl.classList.add('show');

        let target = 'index.html';
        if (u?.account_type === 'admin' || u?.is_staff || u?.is_superuser) {
          target = 'admin-dashboard.html';
        } else if (u?.account_type === 'restaurant' || u?.account_type === 'business') {
          target = 'restaurant-dashboard.html';
        }
        setTimeout(() => { window.location.href = target; }, 1000);
      } else {
        if (res.data?.error === 'unverified_email') {
          const successEl = document.getElementById('loginSuccess');
          if (successEl) {
            successEl.style.background = '#FEF3C7';
            successEl.style.borderColor = '#FCD34D';
            successEl.style.color = '#92400E';
            successEl.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              Please verify your email to log in. <a href="#" id="resendFromLogin" style="color:#92400E;font-weight:700;text-decoration:underline;">Resend verification email</a>`;
            successEl.classList.add('show');

            document.getElementById('resendFromLogin')?.addEventListener('click', async (ev) => {
              ev.preventDefault();
              if (window.Auth) {
                const r = await window.Auth.resendVerification(email);
                const msg = r.data?.message || 'Verification email sent! Check your inbox.';
                successEl.innerHTML = `✓ ${msg}`;
                successEl.style.background = '';
                successEl.style.borderColor = '';
                successEl.style.color = '';
              }
            });
          }
          submitBtn.classList.remove('btn-loading');
          submitBtn.disabled = false;
          return;
        }

        // Map backend field errors to the UI
        const errors = res.data?.errors || {};
        const nonField = errors.non_field_errors || errors.detail;
        if (nonField) {
          showError('loginPassword', Array.isArray(nonField) ? nonField[0] : nonField);
        }
        if (errors.email) showError('loginEmail', Array.isArray(errors.email) ? errors.email[0] : errors.email);
        if (errors.password) showError('loginPassword', Array.isArray(errors.password) ? errors.password[0] : errors.password);
        // Rate limit
        if (res.data?.error && (res.status === 429 || res.data.error.includes('Too many'))) {
          showError('loginPassword', res.data.error);
        }

        submitBtn.classList.remove('btn-loading');
        submitBtn.disabled = false;
      }
    } catch (err) {
      showError('loginPassword', 'Network error. Please check your connection.');
      submitBtn.classList.remove('btn-loading');
      submitBtn.disabled = false;
    }
  });
}

// ---- SIGNUP FORM ----
function initSignupForm() {
  const form = document.getElementById('signupForm');
  if (!form) return;

  const fields = {
    firstName: document.getElementById('signupFirstName'),
    lastName: document.getElementById('signupLastName'),
    email: document.getElementById('signupEmail'),
    password: document.getElementById('signupPassword'),
    confirmPassword: document.getElementById('signupConfirmPassword'),
    phone: document.getElementById('signupPhone'),
  };

  const submitBtn = document.getElementById('signupSubmit');

  // ── Wire Google Sign-Up button ──
  const googleSignupBtn = document.getElementById('googleSignupBtn');
  if (googleSignupBtn) {
    googleSignupBtn.addEventListener('click', async () => {
      googleSignupBtn.disabled = true;
      googleSignupBtn.textContent = 'Connecting to Google…';
      if (window.Auth) {
        const result = await window.Auth.initiateGoogleLogin();
        if (result && !result.ok) {
          googleSignupBtn.disabled = false;
          googleSignupBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
          </svg> Continue with Google`;
          showError('signupEmail', result.error || 'Google Sign-In is not available right now.');
        }
      }
    });
  }

  // Account type toggle
  document.querySelectorAll('.account-type-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.account-type-btn').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
    });
  });

  // Live validation
  if (fields.firstName) {
    fields.firstName.addEventListener('blur', () => {
      if (!fields.firstName.value.trim()) showError('signupFirstName', 'First name is required.');
      else { clearError('signupFirstName'); markSuccess('signupFirstName'); }
    });
    fields.firstName.addEventListener('input', () => clearError('signupFirstName'));
  }

  if (fields.lastName) {
    fields.lastName.addEventListener('blur', () => {
      if (!fields.lastName.value.trim()) showError('signupLastName', 'Last name is required.');
      else { clearError('signupLastName'); markSuccess('signupLastName'); }
    });
    fields.lastName.addEventListener('input', () => clearError('signupLastName'));
  }

  if (fields.email) {
    fields.email.addEventListener('blur', () => {
      const val = fields.email.value.trim();
      if (!val) showError('signupEmail', 'Email is required.');
      else if (!isValidEmail(val)) showError('signupEmail', 'Please enter a valid email address.');
      else { clearError('signupEmail'); markSuccess('signupEmail'); }
    });
    fields.email.addEventListener('input', () => clearError('signupEmail'));
  }

  if (fields.password) {
    fields.password.addEventListener('input', () => {
      clearError('signupPassword');
      updateStrengthBar(fields.password.value, 'strengthBar', 'strengthLabel');
    });
    fields.password.addEventListener('blur', () => {
      const val = fields.password.value;
      if (!val) showError('signupPassword', 'Password is required.');
      else if (val.length < 8) showError('signupPassword', 'Password must be at least 8 characters.');
      else { clearError('signupPassword'); }
    });
  }

  if (fields.confirmPassword) {
    fields.confirmPassword.addEventListener('input', () => clearError('signupConfirmPassword'));
    fields.confirmPassword.addEventListener('blur', () => {
      const val = fields.confirmPassword.value;
      if (!val) showError('signupConfirmPassword', 'Please confirm your password.');
      else if (val !== fields.password?.value) showError('signupConfirmPassword', 'Passwords do not match.');
      else { clearError('signupConfirmPassword'); markSuccess('signupConfirmPassword'); }
    });
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    let valid = true;

    if (!fields.firstName?.value.trim()) { showError('signupFirstName', 'First name is required.'); valid = false; }
    if (!fields.lastName?.value.trim()) { showError('signupLastName', 'Last name is required.'); valid = false; }

    const email = fields.email?.value.trim() || '';
    if (!email) { showError('signupEmail', 'Email is required.'); valid = false; }
    else if (!isValidEmail(email)) { showError('signupEmail', 'Please enter a valid email address.'); valid = false; }

    const pwd = fields.password?.value || '';
    if (!pwd) { showError('signupPassword', 'Password is required.'); valid = false; }
    else if (pwd.length < 8) { showError('signupPassword', 'Password must be at least 8 characters.'); valid = false; }

    const confirm = fields.confirmPassword?.value || '';
    if (!confirm) { showError('signupConfirmPassword', 'Please confirm your password.'); valid = false; }
    else if (confirm !== pwd) { showError('signupConfirmPassword', 'Passwords do not match.'); valid = false; }

    if (!valid) return;

    submitBtn.classList.add('btn-loading');
    submitBtn.disabled = true;

    // Determine selected account type
    const activeTypeBtn = document.querySelector('.account-type-btn.active');
    const accountType = activeTypeBtn?.id === 'typeBusinessBtn' ? 'business' : 'customer';

    try {
      const res = await window.Auth.register({
        first_name: fields.firstName.value.trim(),
        last_name: fields.lastName.value.trim(),
        email,
        password: pwd,
        confirm_password: confirm,
        account_type: accountType,
        phone: fields.phone?.value.trim() || '',
      });

      if (res.ok) {
        const successEl = document.getElementById('signupSuccess');
        if (successEl) {
          // Show email verification notice
          successEl.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20,6 9,17 4,12"/></svg>
            Account created! Check your email to verify your address 📧`;
          successEl.classList.add('show');
        }
        form.reset();
        document.querySelectorAll('.account-type-btn').forEach((b, i) => {
          b.classList.toggle('active', i === 0);
        });
        updateStrengthBar('', 'strengthBar', 'strengthLabel');
        // Redirect based on role
        const u = res.data?.user || window.Auth.getUser();
        let target = 'index.html';
        if (u?.account_type === 'restaurant' || u?.account_type === 'business') {
          target = 'restaurant-dashboard.html';
        }
        setTimeout(() => { window.location.href = target; }, 1800);
      } else {
        // Map backend validation errors to form fields
        const errors = res.data?.errors || {};
        if (errors.first_name) showError('signupFirstName', Array.isArray(errors.first_name) ? errors.first_name[0] : errors.first_name);
        if (errors.last_name)  showError('signupLastName',  Array.isArray(errors.last_name)  ? errors.last_name[0]  : errors.last_name);
        if (errors.email)      showError('signupEmail',     Array.isArray(errors.email)      ? errors.email[0]      : errors.email);
        if (errors.password)   showError('signupPassword',  Array.isArray(errors.password)   ? errors.password[0]   : errors.password);
        if (errors.confirm_password) showError('signupConfirmPassword', Array.isArray(errors.confirm_password) ? errors.confirm_password[0] : errors.confirm_password);
        if (errors.non_field_errors) showError('signupEmail', Array.isArray(errors.non_field_errors) ? errors.non_field_errors[0] : errors.non_field_errors);
        if (res.data?.error) showError('signupEmail', res.data.error);

        submitBtn.classList.remove('btn-loading');
        submitBtn.disabled = false;
      }
    } catch (err) {
      showError('signupEmail', 'Network error. Please check your connection.');
      submitBtn.classList.remove('btn-loading');
      submitBtn.disabled = false;
    }
  });
}

// ---- Auth-aware UI ----
function updateAuthUI() {
  if (!window.Auth || !window.Auth.isLoggedIn()) return;

  const user = window.Auth.getUser();
  const firstName = user?.first_name || 'User';

  let portalBtn = '';
  if (user?.account_type === 'admin' || user?.is_staff || user?.is_superuser) {
    portalBtn = `<a href="admin-dashboard.html" class="btn btn-outline btn-sm" style="color:white; border-color:rgba(255,255,255,0.7); margin-right:8px;">Admin Console</a>`;
  } else if (user?.account_type === 'restaurant' || user?.account_type === 'business') {
    portalBtn = `<a href="restaurant-dashboard.html" class="btn btn-outline btn-sm" style="color:white; border-color:rgba(255,255,255,0.7); margin-right:8px;">Kitchen Dashboard</a>`;
  } else {
    portalBtn = `<a href="customer-bookings.html" class="btn btn-outline btn-sm" style="color:white; border-color:rgba(255,255,255,0.7); margin-right:8px;">My Bookings</a>`;
  }

  // ── Desktop navbar ──
  const navActions = document.querySelector('.nav-actions');
  if (navActions) {
    navActions.innerHTML = `
      ${portalBtn}
      <span class="nav-greeting" style="color:white; font-size:0.9rem; opacity:0.9; margin-right:8px;">
        Hi, <strong>${firstName}</strong>
      </span>
      <button class="btn btn-white btn-sm" id="navLogoutBtn" style="color:var(--color-primary); cursor:pointer; border:none;">
        Log Out
      </button>
    `;
    document.getElementById('navLogoutBtn').addEventListener('click', handleLogout);
  }

  // ── Mobile navbar ──
  const mobileNavActions = document.querySelector('.mobile-nav-actions');
  if (mobileNavActions) {
    mobileNavActions.innerHTML = `
      <div style="margin-bottom:8px;">${portalBtn}</div>
      <span style="color:var(--color-text-muted); font-size:0.95rem; margin-bottom:8px; display:block;">
        Signed in as <strong>${firstName}</strong>
      </span>
      <button class="btn btn-primary" id="mobileLogoutBtn" style="cursor:pointer; border:none; width:100%;">
        Log Out
      </button>
    `;
    document.getElementById('mobileLogoutBtn').addEventListener('click', handleLogout);
  }

  // ── Update CTA links ──
  document.querySelectorAll('a[href="signup.html"], a[href="login.html"]').forEach(link => {
    if (link.closest('.nav-actions') || link.closest('.mobile-nav-actions')) return;
    if (link.id === 'ctaSignupBtn' || link.id === 'partnerBtn') {
      link.href = '#discover';
      if (link.id === 'ctaSignupBtn') link.textContent = '🍽️ Browse Surplus Deals';
    }
  });
}

async function handleLogout() {
  if (!window.Auth) return;
  await window.Auth.logout();
  window.location.href = 'index.html';
}

// =============================================
// LIVE MARKETPLACE & RESERVATION SYSTEM
// =============================================

let activeCategory = 'all';
let currentListings = [];
let currentModalListing = null;
let currentModalQty = 1;
let currentPayMethod = 'UPI';

async function initMarketplace() {
  const grid = document.getElementById('marketplaceFoodGrid');
  if (!grid) return;

  // Category filter pills
  document.querySelectorAll('#categoryFilterBar .cat-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#categoryFilterBar .cat-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeCategory = btn.dataset.category || 'all';
      loadMarketplaceListings();
    });
  });

  // Search input
  const searchInput = document.getElementById('locationSearch');
  if (searchInput) {
    let searchTimeout = null;
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(loadMarketplaceListings, 300);
    });
  }

  // Price sort
  const sortSelect = document.getElementById('priceSortSelect');
  if (sortSelect) {
    sortSelect.addEventListener('change', loadMarketplaceListings);
  }

  // Initial load
  await loadMarketplaceListings();
  initModalListeners();
  initRealtimeMarketplace();
}

async function loadMarketplaceListings() {
  const grid = document.getElementById('marketplaceFoodGrid');
  if (!grid || !window.API) return;

  const search = document.getElementById('locationSearch')?.value || '';
  const sort = document.getElementById('priceSortSelect')?.value || 'newest';

  const res = await window.API.getListings({
    category: activeCategory,
    search,
    sort,
  });

  if (!res.ok || !res.data) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <div class="empty-state-icon">⚠️</div>
        <div class="empty-state-title">Unable to reach the food network</div>
        <p>Please ensure backend server is active and try again.</p>
      </div>
    `;
    return;
  }

  currentListings = res.data;
  renderMarketplaceCards();
}

function renderMarketplaceCards() {
  const grid = document.getElementById('marketplaceFoodGrid');
  if (!grid) return;

  if (currentListings.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <div class="empty-state-icon">🍽️</div>
        <div class="empty-state-title">No surplus food available right now</div>
        <p>Check back shortly as local cafes and bakeries post their evening surplus!</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = currentListings.map(item => {
    const isSoldOut = item.quantity_available <= 0 || item.status === 'sold_out';
    const availClass = isSoldOut ? 'sold-out' : (item.quantity_available <= 2 ? 'warning' : '');
    const availText = isSoldOut ? 'Sold Out' : (item.quantity_available === 1 ? 'Last 1 left!' : `${item.quantity_available} left`);
    const discountText = item.discount_percent > 0 ? `${item.discount_percent}% OFF` : 'DEAL';

    return `
      <article class="food-card" id="foodCard-${item.id}" aria-label="${item.name} listing">
        <div class="food-card-image">
          <img src="${item.image}" alt="${item.name}" loading="lazy" onerror="this.src='assets/images/bakery_box.jpg'"/>
          <span class="food-card-discount">${discountText}</span>
          <div class="food-card-availability ${availClass}" id="cardAvail-${item.id}">
            <span class="dot" aria-hidden="true"></span>
            ${availText}
          </div>
        </div>
        <div class="food-card-body">
          <p class="food-card-business">${item.restaurant_name} · ${item.restaurant_city}</p>
          <h3 class="food-card-title">${item.name}</h3>
          <p class="food-card-desc">${item.description}</p>
          <div class="food-card-meta">
            <div class="food-card-meta-row">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
              </svg>
              Pickup ${item.pickup_start} – ${item.pickup_end}
            </div>
            <div class="food-card-meta-row">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>
              </svg>
              ${item.restaurant_address}
            </div>
          </div>
          <div class="food-card-footer">
            <div class="food-card-pricing">
              <span class="food-card-price">₹${parseFloat(item.discounted_price).toFixed(0)}</span>
              <span class="food-card-original">₹${parseFloat(item.original_price).toFixed(0)}</span>
            </div>
            <button class="food-card-btn" onclick="openFoodModalById(${item.id})" ${isSoldOut ? 'disabled style="opacity:0.6; cursor:not-allowed;"' : ''}>
              ${isSoldOut ? 'Sold Out' : 'View Details'}
            </button>
          </div>
        </div>
      </article>
    `;
  }).join('');
}

// Modal controls
window.openFoodModalById = function (id) {
  if (window.Auth && !window.Auth.isLoggedIn()) {
    window.location.href = 'login.html';
    return;
  }

  const listing = currentListings.find(l => l.id === id);
  if (!listing) return;

  currentModalListing = listing;
  currentModalQty = 1;
  currentPayMethod = 'UPI';

  document.getElementById('resModalTitle').textContent = listing.name;
  document.getElementById('resModalFoodName').textContent = listing.name;
  document.getElementById('resModalRestaurant').textContent = listing.restaurant_name;
  document.getElementById('resModalAddress').textContent = listing.restaurant_address + ', ' + listing.restaurant_city;
  document.getElementById('resModalDesc').textContent = listing.description;
  document.getElementById('resModalImage').src = listing.image || 'assets/images/bakery_box.jpg';
  document.getElementById('resModalPrice').textContent = `₹${parseFloat(listing.discounted_price).toFixed(2)}`;
  document.getElementById('resModalOrigPrice').textContent = `₹${parseFloat(listing.original_price).toFixed(2)}`;
  document.getElementById('resModalPickup').textContent = `${listing.pickup_start} – ${listing.pickup_end}`;
  document.getElementById('resModalRemaining').textContent = `${listing.quantity_available} available`;
  document.getElementById('resModalQtyVal').textContent = '1';

  // Reset payment selection to UPI
  document.querySelectorAll('input[name="payMethod"]').forEach(r => {
    r.checked = r.value === 'UPI';
    r.parentElement.classList.toggle('active', r.value === 'UPI');
  });

  const errEl = document.getElementById('bookingErrorNotice');
  if (errEl) errEl.style.display = 'none';

  updateModalTotal();

  // Reset footer buttons
  const footer = document.getElementById('resModalFooter');
  footer.innerHTML = `
    <button type="button" class="btn btn-outline" onclick="closeFoodModal()">Cancel</button>
    <button type="button" class="btn btn-primary" id="confirmReservationBtn">Book &amp; Reserve Now ✓</button>
  `;
  document.getElementById('confirmReservationBtn').addEventListener('click', handleConfirmReservation);

  document.getElementById('foodReservationModal').classList.add('open');
};

window.closeFoodModal = function () {
  const m = document.getElementById('foodReservationModal');
  if (m) m.classList.remove('open');
};

function updateModalTotal() {
  if (!currentModalListing) return;
  const unit = parseFloat(currentModalListing.discounted_price);
  const total = unit * currentModalQty;
  document.getElementById('resModalTotal').textContent = `₹${total.toFixed(2)}`;
}

function initModalListeners() {
  const minusBtn = document.getElementById('qtyMinusBtn');
  const plusBtn = document.getElementById('qtyPlusBtn');

  if (minusBtn && plusBtn) {
    minusBtn.addEventListener('click', () => {
      if (currentModalQty > 1) {
        currentModalQty--;
        document.getElementById('resModalQtyVal').textContent = currentModalQty;
        updateModalTotal();
      }
    });

    plusBtn.addEventListener('click', () => {
      if (currentModalListing && currentModalQty < currentModalListing.quantity_available) {
        currentModalQty++;
        document.getElementById('resModalQtyVal').textContent = currentModalQty;
        updateModalTotal();
      }
    });
  }

  // Payment radio buttons
  document.querySelectorAll('input[name="payMethod"]').forEach(radio => {
    radio.parentElement.addEventListener('click', () => {
      document.querySelectorAll('input[name="payMethod"]').forEach(r => {
        r.parentElement.classList.remove('active');
      });
      radio.checked = true;
      radio.parentElement.classList.add('active');
      currentPayMethod = radio.value;
    });
  });
}

async function handleConfirmReservation() {
  if (!window.Auth || !window.Auth.isLoggedIn()) {
    alert('Please log in or create an account to book surplus food!');
    window.location.href = 'login.html';
    return;
  }

  const btn = document.getElementById('confirmReservationBtn');
  const errEl = document.getElementById('bookingErrorNotice');
  btn.disabled = true;
  btn.textContent = 'Reserving in database...';
  if (errEl) errEl.style.display = 'none';

  const payload = {
    listing_id: currentModalListing.id,
    quantity: currentModalQty,
    payment_method: currentPayMethod,
    notes: 'Pick up via customer app',
  };

  const res = await window.API.createBooking(payload);
  btn.disabled = false;
  btn.textContent = 'Book & Reserve Now ✓';

  if (res.ok && res.data) {
    const booking = res.data;
    // Show confirmation inside modal
    const body = document.getElementById('resModalBody');
    body.innerHTML = `
      <div style="text-align:center; padding:10px 0 20px;">
        <div style="width:64px; height:64px; background:#D1FAE5; color:#10B981; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font-size:32px; margin-bottom:14px;">
          ✓
        </div>
        <h4 style="font-size:1.4rem; font-weight:800; color:#1E293B; margin-bottom:4px;">Reservation Confirmed!</h4>
        <p style="color:#64748B; font-size:0.9rem; margin-bottom:20px;">Your food box has been successfully locked and reserved.</p>

        <div style="background:#F8FAFC; border:2px dashed #CBD5E1; border-radius:var(--radius-lg); padding:18px; text-align:left; margin-bottom:20px;">
          <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
            <span style="color:#64748B; font-size:0.85rem;">Booking Reference:</span>
            <strong style="color:var(--color-primary); font-size:1.05rem;">#${booking.booking_number}</strong>
          </div>
          <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
            <span style="color:#64748B; font-size:0.85rem;">Food Item:</span>
            <strong>${booking.quantity}x ${booking.listing_name}</strong>
          </div>
          <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
            <span style="color:#64748B; font-size:0.85rem;">Amount:</span>
            <strong>₹${parseFloat(booking.total_amount).toFixed(2)}</strong>
          </div>
          <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
            <span style="color:#64748B; font-size:0.85rem;">Pickup Time:</span>
            <strong style="color:#2563EB;">${booking.pickup_start} – ${booking.pickup_end}</strong>
          </div>
          <div style="display:flex; justify-content:space-between; padding-top:10px; border-top:1px solid #E2E8F0; align-items:center;">
            <span style="color:#64748B; font-size:0.85rem;">Verification PIN:</span>
            <code style="background:var(--color-primary-light); color:var(--color-primary); padding:4px 10px; border-radius:6px; font-weight:800; font-size:1.1rem;">${booking.pickup_code || '----'}</code>
          </div>
        </div>

        <p style="font-size:0.8rem; color:#888;">Show your Verification PIN at the counter during the pickup window to collect your food.</p>
      </div>
    `;

    document.getElementById('resModalFooter').innerHTML = `
      <a href="customer-bookings.html" class="btn btn-primary" style="width:100%; text-align:center;">View in My Bookings →</a>
    `;

    if (window.Realtime) {
      window.Realtime.notify('Reservation Placed!', `Reserved ${booking.quantity}x ${booking.listing_name} (Order #${booking.booking_number})`, 'success');
    }

    // Refresh marketplace listings to reflect decreased stock
    loadMarketplaceListings();
  } else {
    const errorMsg = res.data?.error || 'Unable to place booking. Item may be out of stock.';
    if (errEl) {
      errEl.textContent = errorMsg;
      errEl.style.display = 'block';
    } else {
      alert(errorMsg);
    }
  }
}

function initRealtimeMarketplace() {
  if (!window.Realtime) return;

  // When a new listing is created by a restaurant
  window.Realtime.on('listing_created', (data) => {
    window.Realtime.notify('New Surplus Food Available!', `${data.name} just listed by ${data.restaurant_name}!`, 'info');
    loadMarketplaceListings();
  });

  // When a booking occurs (atomic inventory decrement)
  window.Realtime.on('booking_created', (data) => {
    const cardAvail = document.getElementById(`cardAvail-${data.listing_id}`);
    if (cardAvail) {
      const remaining = data.quantity_available;
      if (remaining <= 0 || data.listing_status === 'sold_out') {
        cardAvail.className = 'food-card-availability sold-out';
        cardAvail.innerHTML = '<span class="dot"></span>Sold Out';
        const btn = document.querySelector(`#foodCard-${data.listing_id} .food-card-btn`);
        if (btn) {
          btn.disabled = true;
          btn.style.opacity = '0.6';
          btn.style.cursor = 'not-allowed';
          btn.textContent = 'Sold Out';
        }
      } else {
        cardAvail.innerHTML = `<span class="dot"></span>${remaining} left`;
      }
    }
  });

  // When listing is updated
  window.Realtime.on('listing_updated', () => loadMarketplaceListings());
  window.Realtime.on('listing_deleted', () => loadMarketplaceListings());
}

// ─── Route Guards ──────────────────────────────────────────────────────────────

/**
 * requireAuth: Verify with the backend that the user is authenticated.
 * If not, redirect to login. Used on protected pages.
 * @param {string} redirectTo - page to redirect to if not authenticated
 */
async function requireAuth(redirectTo = 'login.html') {
  if (!window.Auth || !window.Auth.isLoggedIn()) {
    window.location.href = redirectTo;
    return false;
  }
  // Verify token is still valid with backend
  const res = await window.Auth.me();
  if (!res.ok) {
    window.Auth.clearTokens();
    window.location.href = redirectTo;
    return false;
  }
  return true;
}

/**
 * requireAdmin: Verify with the backend that the user has admin role.
 * If not, redirect to login. Admin status is ALWAYS verified server-side.
 */
async function requireAdmin(redirectTo = 'login.html') {
  if (!window.Auth || !window.Auth.isLoggedIn()) {
    window.location.href = redirectTo;
    return false;
  }
  const res = await window.Auth.me();
  if (!res.ok) {
    window.Auth.clearTokens();
    window.location.href = redirectTo;
    return false;
  }
  const user = res.data;
  const isAdmin = user?.account_type === 'admin' || user?.is_staff || user?.is_superuser;
  if (!isAdmin) {
    // Do NOT redirect to a page that reveals admin exists — just go to login
    window.location.href = redirectTo;
    return false;
  }
  return true;
}

/**
 * requireRestaurant: Verify with the backend that the user has restaurant/business role.
 */
async function requireRestaurant(redirectTo = 'login.html') {
  if (!window.Auth || !window.Auth.isLoggedIn()) {
    window.location.href = redirectTo;
    return false;
  }
  const res = await window.Auth.me();
  if (!res.ok) {
    window.Auth.clearTokens();
    window.location.href = redirectTo;
    return false;
  }
  const user = res.data;
  const isRestaurant = user?.account_type === 'restaurant' || user?.account_type === 'business' ||
                       user?.is_staff || user?.is_superuser;
  if (!isRestaurant) {
    window.location.href = redirectTo;
    return false;
  }
  return true;
}

// Expose guards globally so dashboard pages can use them
window.requireAuth = requireAuth;
window.requireAdmin = requireAdmin;
window.requireRestaurant = requireRestaurant;

// ---- Init ----
document.addEventListener('DOMContentLoaded', async () => {
  initPasswordToggles();
  initLoginForm();
  initSignupForm();
  updateAuthUI();
  initMarketplace();

  // ─── Auth persistence: redirect logged-in users away from auth pages ────────
  const isAuthPage = !!document.getElementById('loginPage') || !!document.getElementById('signupPage');
  if (isAuthPage && window.Auth && window.Auth.isLoggedIn()) {
    const user = window.Auth.getUser();
    if (user?.account_type === 'admin' || user?.is_staff || user?.is_superuser) {
      window.location.href = 'admin-dashboard.html';
    } else if (user?.account_type === 'restaurant' || user?.account_type === 'business') {
      window.location.href = 'restaurant-dashboard.html';
    } else {
      window.location.href = 'index.html';
    }
    return;
  }

  // ─── Protected page route guards ──────────────────────────────────────────
  const isAdminPage = !!document.getElementById('adminDashboard') ||
                      document.title.includes('Admin') && document.querySelector('.dash-layout');
  const isCustomerBookingsPage = !!document.getElementById('customerBookingsPage') ||
                                  document.title.includes('My Bookings');
  const isRestaurantPage = !!document.getElementById('restaurantDashboard') ||
                            document.title.includes('Restaurant Dashboard') ||
                            document.title.includes('Kitchen Dashboard');

  if (isAdminPage) {
    // Admin pages: verify server-side that user has admin role
    await requireAdmin('login.html');
  } else if (isCustomerBookingsPage) {
    // Customer bookings: require any authenticated user
    await requireAuth('login.html');
  } else if (isRestaurantPage) {
    // Restaurant dashboard: require restaurant role
    await requireRestaurant('login.html');
  }
});

