/* Study_Gateway AI — welcome page script.
   No libraries. No network calls of its own. Passwords are never stored, logged or kept in variables
   longer than one function call. All real security (sessions, CSRF, rate limits) lives on the Flask server. */
(() => {
  'use strict';

  /* =====================================================================
     INTEGRATION POINTS — edit only this block.
     ===================================================================== */
  const CONFIG = {
    // REAL: starts Google sign-in through Supabase (your Flask route /auth/google).
    googleUrl: '/auth/google',

    // Where signed-in users go. Must start with "/" (same site only).
    dashboardUrl: '/',

    // PENDING: your Flask backend has no email/password login yet.
    // When you add one, set this to an async function that sends the details to YOUR server
    // over HTTPS (with the CSRF token) and returns { ok: true } or { ok: false, message: '...' }.
    // Never call a third-party service from here with a secret key.
    //   emailLogin: async ({ email, password }) => { ... }
    emailLogin: null,

    // PENDING: set to a URL (e.g. '/signup') once those pages exist.
    createAccountUrl: null,
    forgotPasswordUrl: null,
  };
  /* ===================================================================== */

  const $ = (sel, root = document) => root.querySelector(sel);

  /* ------------------------- form ------------------------- */
  const form = $('#login-form');
  const email = $('#email');
  const password = $('#password');
  const emailErr = $('#email-err');
  const passwordErr = $('#password-err');
  const formMsg = $('#form-msg');
  const loginBtn = $('#login-btn');
  const toggle = $('#toggle-pw');
  const googleBtn = $('#google-btn');

  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  const isLocalPreview = location.protocol === 'file:';

  function setFieldError(input, el, message) {
    el.textContent = message || '';
    const field = input.closest('.field');
    if (message) {
      field.setAttribute('data-invalid', 'true');
      input.setAttribute('aria-invalid', 'true');
    } else {
      field.removeAttribute('data-invalid');
      input.removeAttribute('aria-invalid');
    }
  }

  function showMessage(text, tone) {
    formMsg.textContent = text || '';
    if (text) formMsg.setAttribute('data-tone', tone || 'info');
    else formMsg.removeAttribute('data-tone');
  }

  function validate() {
    const value = email.value.trim();
    let firstBad = null;

    if (!value) {
      setFieldError(email, emailErr, 'Please enter your email address.');
      firstBad = email;
    } else if (value.length > 254 || !EMAIL_RE.test(value)) {
      setFieldError(email, emailErr, "That email doesn't look right. Please check for typos.");
      firstBad = email;
    } else {
      setFieldError(email, emailErr, '');
    }

    if (!password.value) {
      setFieldError(password, passwordErr, 'Please enter your password.');
      firstBad = firstBad || password;
    } else if (password.value.length > 128) {
      setFieldError(password, passwordErr, 'That password is too long.');
      firstBad = firstBad || password;
    } else {
      setFieldError(password, passwordErr, '');
    }
    return { ok: !firstBad, firstBad, email: value };
  }

  const safeDashboard = () =>
    typeof CONFIG.dashboardUrl === 'string' && /^\/(?!\/)/.test(CONFIG.dashboardUrl) ? CONFIG.dashboardUrl : '/';

  email.addEventListener('input', () => emailErr.textContent && setFieldError(email, emailErr, ''));
  password.addEventListener('input', () => passwordErr.textContent && setFieldError(password, passwordErr, ''));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    showMessage('');
    const result = validate();
    if (!result.ok) {
      result.firstBad.focus();
      return;
    }

    if (typeof CONFIG.emailLogin !== 'function') {
      // Honest placeholder: never pretend a login worked.
      showMessage("Email and password sign-in isn't switched on yet. Please use “Continue with Google” — it's quick and safe.", 'info');
      return;
    }

    loginBtn.setAttribute('aria-busy', 'true');
    loginBtn.disabled = true;
    try {
      const outcome = await CONFIG.emailLogin({ email: result.email, password: password.value });
      if (outcome && outcome.ok === true) {
        window.location.assign(safeDashboard());
        return;
      }
      password.value = '';
      showMessage((outcome && outcome.message) || "We couldn't log you in. Please check your details and try again.", 'error');
    } catch (_err) {
      password.value = '';
      showMessage('Something went wrong. Please try again in a moment.', 'error');
    } finally {
      loginBtn.removeAttribute('aria-busy');
      loginBtn.disabled = false;
    }
  });

  toggle.addEventListener('click', () => {
    const show = password.type === 'password';
    password.type = show ? 'text' : 'password';
    toggle.setAttribute('aria-pressed', String(show));
    toggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    password.focus();
  });

  googleBtn.setAttribute('href', CONFIG.googleUrl);
  googleBtn.addEventListener('click', (event) => {
    if (isLocalPreview) {
      event.preventDefault();
      showMessage('Preview mode: Google sign-in only works when this page is served by your Flask app (see README).', 'info');
    }
  });

  [['create-link', 'createAccountUrl', 'Creating an account with email is coming soon. For now, use “Continue with Google”.'],
   ['forgot-link', 'forgotPasswordUrl', 'Password recovery isn’t needed for Google sign-in. Email passwords are coming soon.']]
    .forEach(([id, key, pendingText]) => {
      const link = document.getElementById(id);
      if (CONFIG[key]) {
        link.setAttribute('href', CONFIG[key]);
      } else {
        link.addEventListener('click', (event) => {
          event.preventDefault();
          showMessage(pendingText, 'info');
        });
      }
    });

  /* ------------------------- puppies: paw trails + hearts ------------------------- */
  const reduce = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)')
                                   : { matches: false, addEventListener() {} };
  const stage = $('.stage');
  const trail = $('#trail');
  const pups = ['#pup-lead', '#pup-follow'].map((sel) => ({ svg: $(sel + ' .pup-svg'), lastX: null, foot: 1 }));

  const PAW = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="#i-paw"/></svg>';
  const HEART = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="#i-heart"/></svg>';
  const MAX_TRAIL = 26;

  let onScreen = true;
  let pawTimer = null;
  let heartTimer = null;

  function spawn(className, html, x, y, vars) {
    const el = document.createElement('span');
    el.className = className;
    el.innerHTML = html; // constant strings above, no user data
    el.style.left = x + 'px';
    el.style.top = y + 'px';
    Object.keys(vars || {}).forEach((k) => el.style.setProperty(k, vars[k]));
    el.addEventListener('animationend', () => el.remove());
    trail.appendChild(el);
    while (trail.childElementCount > MAX_TRAIL) trail.firstElementChild.remove();
  }

  function dropPaws() {
    const box = stage.getBoundingClientRect();
    pups.forEach((p) => {
      const r = p.svg.getBoundingClientRect();
      const x = r.left + r.width / 2 - box.left;
      if (p.lastX !== null && Math.abs(x - p.lastX) > 3) { // only while actually running
        const dir = x > p.lastX ? 1 : -1;
        p.foot *= -1;
        spawn('paw', PAW, x - dir * r.width * 0.2, r.bottom - box.top - 6 + p.foot * 5, { '--rot': dir > 0 ? '90deg' : '-90deg' });
      }
      p.lastX = x;
    });
  }

  function floatHeart() {
    const p = pups[Math.floor(Math.random() * pups.length)];
    const box = stage.getBoundingClientRect();
    const r = p.svg.getBoundingClientRect();
    spawn('heart-pop', HEART, r.left + r.width * (0.35 + Math.random() * 0.3) - box.left, r.top - box.top + r.height * 0.15,
      { '--dx': Math.round(Math.random() * 28 - 14) + 'px' });
    heartTimer = setTimeout(floatHeart, 2800 + Math.random() * 2400);
  }

  function startEffects() {
    if (pawTimer || reduce.matches || document.hidden || !onScreen) return;
    pawTimer = setInterval(dropPaws, 420);
    heartTimer = setTimeout(floatHeart, 2500);
  }

  function stopEffects() {
    clearInterval(pawTimer);
    clearTimeout(heartTimer);
    pawTimer = heartTimer = null;
    pups.forEach((p) => { p.lastX = null; });
  }

  function syncEffects() {
    document.documentElement.classList.toggle('is-paused', document.hidden);
    if (reduce.matches || document.hidden || !onScreen) {
      stopEffects();
      if (reduce.matches) trail.textContent = '';
    } else {
      startEffects();
    }
  }

  document.addEventListener('visibilitychange', syncEffects);
  if (reduce.addEventListener) reduce.addEventListener('change', syncEffects);
  if ('IntersectionObserver' in window) {
    new IntersectionObserver((entries) => {
      onScreen = entries[entries.length - 1].isIntersecting;
      syncEffects();
    }).observe(stage);
  }
  // wait for the entrance bounce before leaving prints
  setTimeout(syncEffects, 1500);
})();
