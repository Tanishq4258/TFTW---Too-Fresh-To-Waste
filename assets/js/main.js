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

    // Simulate loading
    submitBtn.classList.add('btn-loading');
    submitBtn.disabled = true;

    await new Promise(resolve => setTimeout(resolve, 1800));

    submitBtn.classList.remove('btn-loading');
    submitBtn.disabled = false;

    // Show mock success (redirect would happen here)
    const successEl = document.getElementById('loginSuccess');
    if (successEl) {
      successEl.classList.add('show');
      setTimeout(() => successEl.classList.remove('show'), 4000);
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
  };

  const submitBtn = document.getElementById('signupSubmit');

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

    await new Promise(resolve => setTimeout(resolve, 2000));

    submitBtn.classList.remove('btn-loading');
    submitBtn.disabled = false;

    const successEl = document.getElementById('signupSuccess');
    if (successEl) {
      successEl.classList.add('show');
      form.reset();
      document.querySelectorAll('.account-type-btn').forEach((b, i) => {
        b.classList.toggle('active', i === 0);
      });
      updateStrengthBar('', 'strengthBar', 'strengthLabel');
    }
  });
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  initPasswordToggles();
  initLoginForm();
  initSignupForm();
});
