/* ============================================================
   Libra — Library OS front-end
   Vanilla JS single-page app served by FastAPI.
   ============================================================ */
'use strict';

const API = '/api/v1';
const TOKEN_KEY = 'libra.access';
const REFRESH_KEY = 'libra.refresh';
const THEME_KEY = 'libra.theme';

const state = {
  user: null,
  view: 'dashboard',
  categories: [],
  notifications: [],
  loansTab: 'active',
  books: { q: '', category: '', sort: 'newest', page: 1, pageSize: 12, pages: 1, total: 0 },
  browseReq: 0,
  shelfTab: 'all',
  shelves: {
    items: [],
    byBook: new Map(),
    counts: { want_to_read: 0, reading: 0, finished: 0 },
    goal: { target: 12, finished: 0, year: new Date().getFullYear(), percent: 0 },
    loaded: false,
  },
};

/* ----------------------------- helpers ----------------------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const escapeHTML = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));

const number = (n) => new Intl.NumberFormat('en-US').format(Number(n || 0));
const money = (n, currency = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(Number(n || 0));

function parseDate(value) {
  if (!value) return null;
  const raw = String(value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    const dateOnly = new Date(`${raw}T00:00:00Z`);
    return Number.isNaN(dateOnly.getTime()) ? null : dateOnly;
  }
  const hasTimezone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(raw);
  const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const date = new Date(hasTimezone ? raw : `${normalized}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}
const fmtDate = (value) => {
  const d = parseDate(value);
  return d ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
};
const fmtShortDate = (value) => {
  const d = parseDate(value);
  return d ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—';
};
const fmtDateTime = (value) => {
  const d = parseDate(value);
  return d ? d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—';
};
const fmtTime = (value) => {
  const d = parseDate(value);
  return d ? d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) : '—';
};
const localInputValue = (date) => {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};
const fmtMonthDay = (value) => {
  const d = parseDate(value);
  return d ? { day: d.toLocaleDateString('en-US', { day: '2-digit' }), month: d.toLocaleDateString('en-US', { month: 'short' }), year: d.getFullYear() } : { day: '—', month: '—', year: '' };
};
function timeAgo(value) {
  const d = parseDate(value);
  if (!d) return '';
  const sec = Math.round((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return 'just now';
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} hr ago`;
  if (sec < 604800) return `${Math.floor(sec / 86400)} d ago`;
  return fmtShortDate(value);
}
const initialsOf = (name) =>
  String(name || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
const firstName = () => (state.user?.full_name || 'Reader').split(' ')[0];
const isStaff = () => !!state.user && ['admin', 'librarian'].includes(state.user.role);
const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
};
const fullDateToday = () =>
  new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
const roleLabel = (role) => ({ admin: 'Administrator', librarian: 'Librarian', member: 'Member' }[role] || role);
const tierLabel = (tier) => ({ basic: 'Basic', student: 'Student', premium: 'Premium', family: 'Family' }[tier] || tier);
const debounce = (fn, wait = 300) => {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
};

/* ------------------------------- icons ------------------------------ */
const ICON = {
  book: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 5.5A2.5 2.5 0 016.5 3H20v18H6.5A2.5 2.5 0 014 18.5v-13z" stroke="currentColor" stroke-width="1.8"/><path d="M8 3v18M12 8h5M12 12h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  books: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 4.5A1.5 1.5 0 015.5 3H9v18H5.5A1.5 1.5 0 014 19.5v-15z" stroke="currentColor" stroke-width="1.8"/><path d="M11 3h3.5A1.5 1.5 0 0116 4.5v15a1.5 1.5 0 01-1.5 1.5H11V3z" stroke="currentColor" stroke-width="1.8"/><path d="M18.2 4.4l2.2 15.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  users: '<svg viewBox="0 0 24 24" fill="none"><circle cx="9" cy="8" r="3.2" stroke="currentColor" stroke-width="1.8"/><path d="M3.5 19c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M15.5 5.6a3.2 3.2 0 010 6.2M17.5 14.6c2 .5 3.2 2.2 3.6 4.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  loans: '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.8"/><path d="M12 7.5V12l3 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  cash: '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="6" width="18" height="13" rx="2.5" stroke="currentColor" stroke-width="1.8"/><path d="M3 10h18" stroke="currentColor" stroke-width="1.8"/><path d="M7 15h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9L12 3.5z"/></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.8"/><path d="M12 7.5V12l3 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  arrow: '<svg viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none"><path d="M5 12.5l4.5 4.5L19 7.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  warning: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 4l8.5 15h-17L12 4z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 9.5v4M12 16.5v.1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  calendar: '<svg viewBox="0 0 24 24" fill="none"><rect x="3.5" y="5" width="17" height="16" rx="2.5" stroke="currentColor" stroke-width="1.8"/><path d="M3.5 9.5h17M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  card: '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="6" width="18" height="13" rx="2.5" stroke="currentColor" stroke-width="1.8"/><path d="M3 10h18" stroke="currentColor" stroke-width="1.8"/><path d="M7 15h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="6.5" stroke="currentColor" stroke-width="1.8"/><path d="M16 16l4.5 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  spark: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2z" fill="currentColor"/></svg>',
  shield: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3l7 3v5.2c0 4.4-3 8.2-7 9.8-4-1.6-7-5.4-7-9.8V6l7-3z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M9.5 12.2l1.7 1.7 3.5-3.6" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  spaces: '<svg viewBox="0 0 24 24" fill="none"><path d="M3 20h18M5 20V9.5L12 4l7 5.5V20" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M9 20v-5h6v5M9 9.5h.01M15 9.5h.01" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  bookmark: '<svg viewBox="0 0 24 24" fill="none"><path d="M6.5 4.5h11A1.5 1.5 0 0119 6v13.5l-6.5-3-6.5 3V6a1.5 1.5 0 011.5-1.5z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
  bookmarkFill: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6.5 4.5h11A1.5 1.5 0 0119 6v13.5l-6.5-3-6.5 3V6a1.5 1.5 0 011.5-1.5z"/></svg>',
  target: '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.8"/><path d="M12 8v4l2.5 1.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  logout: '<svg viewBox="0 0 24 24" fill="none"><path d="M14 8V5.5A1.5 1.5 0 0012.5 4h-6A1.5 1.5 0 005 5.5v13A1.5 1.5 0 006.5 20h6a1.5 1.5 0 001.5-1.5V16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M10 12h11M17.5 8.5L21 12l-3.5 3.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

/* ----------------------------- session ----------------------------- */
const prefersReducedMotion = () =>
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, prefersReducedMotion() ? 0 : ms));
const getAccess = () => localStorage.getItem(TOKEN_KEY);
const getRefresh = () => localStorage.getItem(REFRESH_KEY);
const saveSession = (tokens) => {
  localStorage.setItem(TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
};
const clearSession = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
};

async function refreshSession() {
  const refreshToken = getRefresh();
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${API}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    saveSession(await res.json());
    return true;
  } catch {
    return false;
  }
}

async function api(path, { method = 'GET', body, retry = true } = {}) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const token = getAccess();
  if (token) opts.headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${API}${path}`, opts);
  } catch {
    throw new Error('Network error — please check your connection.');
  }

  if (res.status === 401 && retry && getRefresh()) {
    if (await refreshSession()) return api(path, { method, body, retry: false });
    forceSignOut();
    throw new Error('Your session expired. Please sign in again.');
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === 'string') detail = data.detail;
      else if (Array.isArray(data.detail)) detail = data.detail.map((d) => d.msg).join(', ');
      else if (data.message) detail = data.message;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

/* ------------------------------ toast ------------------------------ */
function toast(message, type = 'success') {
  const root = $('#toast-root');
  if (!root) return;
  const existing = $$('.toast', root);
  if (existing.length >= 3) existing.slice(0, existing.length - 2).forEach((el) => el.remove());
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const glyph = type === 'error' ? '!' : type === 'info' ? 'i' : '✓';
  el.innerHTML = `<span class="toast-icon">${glyph}</span><span>${escapeHTML(message)}</span>`;
  root.appendChild(el);
  setTimeout(() => {
    el.classList.add('out');
    setTimeout(() => el.remove(), 300);
  }, 3800);
}

/* ------------------------------ modal ------------------------------ */
function openModal(html) {
  const root = $('#modal-root');
  root.innerHTML = `
    <div class="modal-backdrop" id="modal-backdrop">
      <div class="modal" role="dialog" aria-modal="true">
        <button class="modal-close" data-close type="button" aria-label="Close">×</button>
        ${html}
      </div>
    </div>`;
  document.body.classList.add('no-scroll');
  setTimeout(() => {
    const focusable = $('#modal-root input, #modal-root select, #modal-root textarea, #modal-root button.btn');
    focusable?.focus({ preventScroll: true });
  }, 90);
}
function setModalHTML(html) {
  const modal = $('#modal-root .modal');
  if (!modal) return openModal(html);
  modal.innerHTML = `<button class="modal-close" data-close type="button" aria-label="Close">×</button>${html}`;
}
function closeModal() {
  $('#modal-root').innerHTML = '';
  document.body.classList.remove('no-scroll');
}

/* ----------------------------- theme ------------------------------- */
function applyTheme(theme, persist = true) {
  document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : 'light';
  if (persist) localStorage.setItem(THEME_KEY, theme);
}
function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
}

/* ------------------------------ auth ------------------------------- */
const DEMO_ACCOUNTS = {
  member: ['member@library.com', 'Member@123'],
  librarian: ['librarian@library.com', 'Librarian@123'],
  admin: ['admin@library.com', 'Admin@123'],
};

function switchAuthTab(tab) {
  if ($('#auth-card')?.classList.contains('is-submitting')) return;
  $$('.auth-tab').forEach((b) => b.classList.toggle('active', b.dataset.authTab === tab));
  const form = $(tab === 'login' ? '#login-form' : '#register-form');
  const other = $(tab === 'login' ? '#register-form' : '#login-form');
  other?.classList.add('hidden');
  form?.classList.remove('hidden', 'form-in');
  if (form) {
    void form.offsetWidth;
    form.classList.add('form-in');
  }
  setAuthLive('');
}

function shakeAuthCard() {
  const card = $('#auth-card');
  if (!card || prefersReducedMotion()) return;
  card.classList.remove('auth-shake');
  void card.offsetWidth;
  card.classList.add('auth-shake');
  setTimeout(() => card.classList.remove('auth-shake'), 500);
}

function setAuthLive(message = '') {
  const live = $('#auth-live');
  if (live) live.textContent = message;
}

function setAuthBusy(card, form, busy) {
  if (!card) return;
  card.classList.toggle('is-submitting', busy);
  card.setAttribute('aria-busy', String(busy));
  form?.setAttribute('aria-busy', String(busy));
}

function setAuthSuccess(card, form, message) {
  if (!card) return;
  card.classList.remove('is-submitting');
  card.classList.add('is-success');
  card.setAttribute('aria-busy', 'false');
  form?.setAttribute('aria-busy', 'false');
  setAuthLive(message);
}

function playAuthTransition() {
  if (prefersReducedMotion()) return;
  const curtain = $('#auth-transition');
  if (!curtain) return;
  curtain.classList.remove('hidden', 'active', 'done');
  void curtain.offsetWidth;
  curtain.classList.add('active');
  setTimeout(() => curtain.classList.add('done'), 520);
  setTimeout(() => curtain.classList.add('hidden'), 940);
}

function resetShelvesState() {
  state.shelves = {
    items: [],
    byBook: new Map(),
    counts: { want_to_read: 0, reading: 0, finished: 0 },
    goal: { target: 12, finished: 0, year: new Date().getFullYear(), percent: 0 },
    loaded: false,
  };
}

async function handleLogin(event) {
  event.preventDefault();
  const card = $('#auth-card');
  const form = $('#login-form');
  const button = $('#login-submit');
  const label = button.querySelector('span');
  if (card?.classList.contains('is-submitting')) return;
  card?.classList.remove('is-success');
  $('#toast-root')?.replaceChildren();
  button.disabled = true;
  button.classList.add('is-busy');
  label.textContent = 'Signing in…';
  setAuthBusy(card, form, true);
  setAuthLive('Checking your library card…');
  try {
    const tokens = await api('/auth/login', {
      method: 'POST',
      body: { email: $('#login-email').value.trim(), password: $('#login-password').value },
    });
    saveSession(tokens);
    state.user = await api('/auth/me');
    button.classList.remove('is-busy');
    button.classList.add('is-success');
    label.textContent = 'Welcome back';
    setAuthSuccess(card, form, `Welcome back, ${firstName()}. Opening your library.`);
    const transitionLabel = $('#auth-transition-label');
    if (transitionLabel) transitionLabel.textContent = `Opening your library, ${firstName()}…`;
    await wait(420);
    await enterApp({ animate: true });
    toast(`Welcome back, ${firstName()}!`);
  } catch (error) {
    card?.classList.remove('is-submitting', 'is-success');
    button.classList.remove('is-busy', 'is-success');
    setAuthLive(error.message);
    shakeAuthCard();
    toast(error.message, 'error');
  } finally {
    button.classList.remove('is-busy', 'is-success');
    button.disabled = false;
    label.textContent = 'Sign in';
    card?.classList.remove('is-submitting', 'is-success');
    card?.setAttribute('aria-busy', 'false');
    form?.setAttribute('aria-busy', 'false');
  }
}

async function handleRegister(event) {
  event.preventDefault();
  const card = $('#auth-card');
  const form = $('#register-form');
  const button = $('#register-submit');
  const label = button.querySelector('span');
  if (card?.classList.contains('is-submitting')) return;
  card?.classList.remove('is-success');
  $('#toast-root')?.replaceChildren();
  button.disabled = true;
  button.classList.add('is-busy');
  label.textContent = 'Creating…';
  setAuthBusy(card, form, true);
  setAuthLive('Creating your library card…');
  try {
    const tokens = await api('/auth/register', {
      method: 'POST',
      body: {
        full_name: $('#register-name').value.trim(),
        email: $('#register-email').value.trim(),
        password: $('#register-password').value,
      },
    });
    saveSession(tokens);
    state.user = await api('/auth/me');
    button.classList.remove('is-busy');
    button.classList.add('is-success');
    label.textContent = 'Your card is ready';
    setAuthSuccess(card, form, `Your library card is ready, ${firstName()}. Opening your library.`);
    const transitionLabel = $('#auth-transition-label');
    if (transitionLabel) transitionLabel.textContent = `Opening your library, ${firstName()}…`;
    await wait(420);
    await enterApp({ animate: true });
    toast(`Welcome to Libra, ${firstName()}! Your library card and shelves are ready.`);
  } catch (error) {
    card?.classList.remove('is-submitting', 'is-success');
    button.classList.remove('is-busy', 'is-success');
    setAuthLive(error.message);
    shakeAuthCard();
    toast(error.message, 'error');
  } finally {
    button.classList.remove('is-busy', 'is-success');
    button.disabled = false;
    label.textContent = 'Create my account';
    card?.classList.remove('is-submitting', 'is-success');
    card?.setAttribute('aria-busy', 'false');
    form?.setAttribute('aria-busy', 'false');
  }
}

function showAuth() {
  $('#app-shell').classList.add('hidden');
  $('#app-shell').classList.remove('app-entering');
  const auth = $('#auth-screen');
  auth.classList.remove('hidden', 'auth-leaving', 'auth-visible');
  const card = $('#auth-card');
  card?.classList.remove('is-submitting', 'is-success', 'auth-shake');
  card?.setAttribute('aria-busy', 'false');
  $('#login-form')?.setAttribute('aria-busy', 'false');
  $('#register-form')?.setAttribute('aria-busy', 'false');
  const transitionLabel = $('#auth-transition-label');
  if (transitionLabel) transitionLabel.textContent = 'Opening your library…';
  setAuthLive('');
  void auth.offsetWidth;
  requestAnimationFrame(() => auth.classList.add('auth-visible'));
  $('#auth-transition')?.classList.add('hidden');
  document.body.classList.remove('no-scroll');
}

async function enterApp({ animate = false } = {}) {
  if (animate) {
    $('#auth-screen').classList.add('auth-leaving');
    playAuthTransition();
    await wait(240);
  }
  $('#auth-screen').classList.add('hidden');
  $('#auth-screen').classList.remove('auth-leaving', 'auth-visible');
  const shell = $('#app-shell');
  shell.classList.remove('hidden', 'app-entering');
  void shell.offsetWidth;
  shell.classList.add('app-entering');
  $('#toast-root')?.replaceChildren();
  renderUserChrome();
  state.loansTab = 'active';
  resetShelvesState();
  await loadShelves().catch(() => {});
  const params = new URLSearchParams(location.search);
  const requestedView = params.get('view');
  await setView(requestedView && RENDERERS[requestedView] ? requestedView : 'dashboard');
  loadNotifications();
  setTimeout(() => shell.classList.remove('app-entering'), 980);
  if (params.get('checkout') === 'success') {
    const sessionId = params.get('session_id');
    if (sessionId) {
      try {
        const result = await api(`/payments/checkout/${encodeURIComponent(sessionId)}/confirm`, { method: 'POST' });
        state.user = await api('/auth/me');
        renderUserChrome();
        await loadShelves();
        await setView(state.view);
        toast(result.message || 'Payment successful — thank you!');
      } catch (error) {
        toast(error.message, 'error');
      }
    } else {
      toast('Payment successful — thank you for supporting the library!');
    }
    history.replaceState({}, '', location.pathname);
  } else if (params.get('checkout') === 'cancelled') {
    toast('Checkout cancelled — no charge was made.', 'info');
    history.replaceState({}, '', location.pathname);
  }
}

async function logout() {
  const overlay = $('#logout-overlay');
  overlay.classList.remove('hidden');
  try { await api('/auth/logout', { method: 'POST' }); } catch { /* offline is fine */ }
  await wait(1050);
  clearSession();
  state.user = null;
  state.notifications = [];
  resetShelvesState();
  overlay.classList.add('hidden');
  showAuth();
  $('#login-form').reset();
  $('#register-form').reset();
  switchAuthTab('login');
  closeMenus();
  $('#notif-panel')?.classList.add('hidden');
  toast('Signed out. See you at the library again soon!', 'info');
}

function forceSignOut() {
  clearSession();
  state.user = null;
  resetShelvesState();
  closeModal();
  showAuth();
  switchAuthTab('login');
}

function renderUserChrome() {
  if (!state.user) return;
  const staff = isStaff();
  $('#avatar-initials').textContent = initialsOf(state.user.full_name);
  $('#menu-name').textContent = state.user.full_name;
  $('#menu-email').textContent = state.user.email;
  $$('[data-staff-only]').forEach((el) => { el.style.display = staff ? '' : 'none'; });
  $('#nav-loans-label').textContent = staff ? 'Circulation' : 'My loans';
}

/* -------------------------- navigation ----------------------------- */
const STAFF_VIEWS = new Set(['members', 'payments', 'audit']);

async function setView(view, options = {}) {
  if (!RENDERERS[view]) view = 'dashboard';
  if (STAFF_VIEWS.has(view) && !isStaff()) view = 'dashboard';
  state.view = view;
  if (options.q !== undefined) {
    state.books.q = options.q;
    state.books.page = 1;
  }
  $$('.nav-item[data-view], .mobile-nav-item[data-view], .brand-btn[data-view]').forEach((el) => {
    el.classList.toggle('active', el.dataset.view === view);
  });
  const root = $('#view');
  root.innerHTML = skeletonView();
  root.classList.remove('view-enter');
  void root.offsetWidth;
  root.classList.add('view-enter');
  try {
    await RENDERERS[view](root);
  } catch (error) {
    root.innerHTML = errorState(error.message);
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
  closeMenus();
}

function skeletonView() {
  return `
    <div class="page-head">
      <div style="width:min(360px,80%)">
        <div class="skeleton skel-line" style="width:35%;height:10px"></div>
        <div class="skeleton" style="height:34px;width:70%;margin:10px 0 8px"></div>
        <div class="skeleton skel-line" style="width:55%"></div>
      </div>
    </div>
    <div class="stat-grid">
      ${Array.from({ length: 4 }).map(() => '<div class="skeleton" style="height:118px;border-radius:22px"></div>').join('')}
    </div>
    <div class="skeleton" style="height:300px;border-radius:22px"></div>`;
}

function errorState(message) {
  return `<div class="empty" style="margin-top:40px">
    <div class="empty-icon">!</div>
    <h3>Something went wrong</h3>
    <p>${escapeHTML(message || 'Please try again in a moment.')}</p>
    <button class="btn btn-primary" data-action="retry-view">Try again</button>
  </div>`;
}

function emptyState(icon, title, text, action = '') {
  return `<div class="empty">
    <div class="empty-icon">${icon}</div>
    <h3>${escapeHTML(title)}</h3>
    <p>${escapeHTML(text)}</p>
    ${action}
  </div>`;
}

/* --------------------------- chrome menus -------------------------- */
function closeMenus() {
  $('#avatar-menu')?.classList.add('hidden');
  $('#notif-panel')?.classList.add('hidden');
  $('#avatar-btn')?.setAttribute('aria-expanded', 'false');
  $('#notif-btn')?.setAttribute('aria-expanded', 'false');
}

function bindChrome() {
  $('#theme-toggle')?.addEventListener('click', toggleTheme);
  $('#avatar-btn')?.addEventListener('click', (event) => {
    event.stopPropagation();
    const menu = $('#avatar-menu');
    const willOpen = menu.classList.contains('hidden');
    closeMenus();
    menu.classList.toggle('hidden', !willOpen);
    $('#avatar-btn').setAttribute('aria-expanded', String(willOpen));
  });
  $('#notif-btn')?.addEventListener('click', (event) => {
    event.stopPropagation();
    const panel = $('#notif-panel');
    const willOpen = panel.classList.contains('hidden');
    closeMenus();
    panel.classList.toggle('hidden', !willOpen);
    $('#notif-btn').setAttribute('aria-expanded', String(willOpen));
    if (willOpen) loadNotifications();
  });
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.avatar-wrap') && !event.target.closest('.notif-wrap')) closeMenus();
  });
  $('#sidebar-logout')?.addEventListener('click', logout);
  $('#menu-logout')?.addEventListener('click', logout);
  $('#global-search')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      const q = event.target.value.trim();
      $('#global-search').blur();
      setView('browse', { q });
    }
  });
  $$('.auth-tab').forEach((button) =>
    button.addEventListener('click', () => switchAuthTab(button.dataset.authTab)));
  $$('[data-password-toggle]').forEach((button) =>
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      if (!input) return;
      const showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      button.classList.toggle('is-showing', !showing);
      button.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
      button.setAttribute('aria-pressed', String(!showing));
      input.focus({ preventScroll: true });
    }));
  $$('[data-demo]').forEach((button) =>
    button.addEventListener('click', () => {
      const [email, password] = DEMO_ACCOUNTS[button.dataset.demo];
      $('#login-email').value = email;
      $('#login-password').value = password;
      switchAuthTab('login');
      toast(`${button.dataset.demo} demo account filled in. Press “Sign in” or Enter.`, 'info');
    }));
  $('#login-form')?.addEventListener('submit', handleLogin);
  $('#register-form')?.addEventListener('submit', handleRegister);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeModal();
      closeMenus();
    }
  });
  $('#modal-root')?.addEventListener('click', (event) => {
    if (event.target.id === 'modal-backdrop' || event.target.closest('[data-close]')) closeModal();
  });
}

/* -------------------------- notifications -------------------------- */
async function loadNotifications() {
  if (!state.user) return;
  try {
    const [items, unread] = await Promise.all([
      api('/notifications'),
      api('/notifications/unread-count'),
    ]);
    state.notifications = items;
    $('#notif-dot')?.classList.toggle('hidden', !unread.unread);
    renderNotifPanel();
  } catch { /* silent */ }
}

function renderNotifPanel() {
  const panel = $('#notif-panel');
  if (!panel) return;
  const items = state.notifications;
  const head = `<div class="notif-head"><strong>Notifications</strong>${
    items.some((n) => !n.is_read)
      ? '<button type="button" data-action="mark-all-notifs">Mark all read</button>' : ''
  }</div>`;
  panel.innerHTML = head + (items.length
    ? items.map((n) => `
        <div class="notif-item ${n.is_read ? '' : 'unread'}" ${n.is_read ? '' : `data-action="read-notif" data-id="${n.id}"`}>
          <span class="notif-icon">${n.type === 'fine' ? '!' : n.type === 'reservation' ? '★' : '✓'}</span>
          <div>
            <p>${escapeHTML(n.title)}</p>
            <span>${escapeHTML(n.message || '')} · ${escapeHTML(timeAgo(n.created_at))}</span>
          </div>
        </div>`).join('')
    : '<div class="notif-empty">No notifications yet.<br>Borrow a book and we’ll keep you posted.</div>');
}

/* ------------------------- shared UI pieces ------------------------ */
function statCard(icon, label, value, opts = {}) {
  const { tone = '#4f46e5', suffix = '', trend = '', i = 0, moneyValue = false } = opts;
  const raw = Number(value || 0);
  return `<article class="stat-card" style="--tone:${tone};--i:${i}">
    <div class="stat-top">
      <span class="stat-icon">${icon}</span>
      ${trend ? `<span class="stat-trend">${escapeHTML(trend)}</span>` : ''}
    </div>
    <h3 data-count="${raw}" data-money="${moneyValue ? '1' : '0'}" data-suffix="${escapeHTML(suffix)}">0</h3>
    <p class="stat-label">${escapeHTML(label)}</p>
  </article>`;
}

function animateStats(root) {
  $$('[data-count]', root).forEach((el) => {
    const target = Number(el.dataset.count);
    if (!Number.isFinite(target)) return;
    const isMoney = el.dataset.money === '1';
    const suffix = el.dataset.suffix || '';
    const duration = 950;
    const started = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const value = target * eased;
      el.textContent = isMoney
        ? money(value)
        : Math.round(value).toLocaleString('en-US') + suffix;
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

function animateBars(root) {
  requestAnimationFrame(() => {
    $$('[data-height]', root).forEach((el) => {
      el.style.height = `${el.dataset.height}%`;
    });
  });
}

function chartHTML(monthly) {
  const max = Math.max(...monthly.map((m) => Number(m.loans) || 0), 1);
  const revenue = monthly.reduce((sum, m) => sum + Number(m.revenue || 0), 0);
  return `<div class="chart">${monthly.map((m) => {
    const value = Number(m.loans) || 0;
    const height = value > 0 ? Math.max(3, Math.round((value / max) * 100)) : 0;
    return `
      <div class="chart-col" title="${value} loans in ${escapeHTML(m.month)}">
        <div class="chart-bars">
          <div class="chart-bar" data-height="${height}"></div>
        </div>
        <span class="chart-label">${escapeHTML(m.month)}</span>
      </div>`;
  }).join('')}
    </div>
    <div class="chart-legend">
      <span><i class="legend-dot"></i>Loans per month</span>
      <span class="chart-total">Revenue over 6 months: ${money(revenue)}</span>
    </div>`;
}

const LOAN_BADGE = {
  active: ['blue', 'On loan'],
  returned: ['green', 'Returned'],
  overdue: ['red', 'Overdue'],
  lost: ['grey', 'Lost'],
};
const FINE_BADGE = { unpaid: ['amber', 'Unpaid'], paid: ['green', 'Paid'], waived: ['grey', 'Waived'] };
const PAYMENT_BADGE = {
  pending: ['amber', 'Pending'],
  succeeded: ['green', 'Paid'],
  failed: ['red', 'Failed'],
  refunded: ['grey', 'Refunded'],
};
const RESERVATION_BADGE = {
  pending: ['blue', 'Pending'],
  ready: ['amber', 'Ready for pickup'],
  fulfilled: ['green', 'Fulfilled'],
  cancelled: ['grey', 'Cancelled'],
  expired: ['grey', 'Expired'],
};
const badge = (map, key) => {
  const [tone, label] = map[key] || ['grey', key || '—'];
  return `<span class="badge ${tone}">${escapeHTML(label)}</span>`;
};

function miniCover(book, size = '') {
  return `<span class="mini-cover ${size}">
    ${book?.cover_image_url ? `<img src="${escapeHTML(book.cover_image_url)}" alt="" loading="lazy" onerror="this.remove()">` : ''}
    <span>${escapeHTML(initialsOf(book?.title || '?'))}</span>
  </span>`;
}

/* --------------------------- reading shelves ----------------------- */
const SHELF_META = {
  want_to_read: { label: 'Want to read', short: 'Want to read', icon: ICON.bookmark },
  reading: { label: 'Reading now', short: 'Reading', icon: ICON.book },
  finished: { label: 'Finished', short: 'Finished', icon: ICON.check },
};

function shelfFor(bookId) {
  return state.shelves.byBook.get(Number(bookId)) || null;
}

async function loadShelves(force = false) {
  if (!state.user) return state.shelves;
  if (state.shelves.loaded && !force) return state.shelves;
  const data = await api('/shelves/me');
  state.shelves.items = data.items || [];
  state.shelves.byBook = new Map(
    state.shelves.items.map((entry) => [Number(entry.book.id), entry]),
  );
  state.shelves.counts = {
    want_to_read: 0,
    reading: 0,
    finished: 0,
    ...(data.counts || {}),
  };
  state.shelves.goal = data.goal || state.shelves.goal;
  state.shelves.loaded = true;
  return state.shelves;
}

function goalProgressText(goal) {
  const remaining = Math.max(0, Number(goal.target) - Number(goal.finished));
  if (!remaining) return 'Challenge complete — every page counts.';
  return `${remaining} book${remaining === 1 ? '' : 's'} to go this year.`;
}

function bookCard(book, index = 0) {
  const available = Number(book.available_copies) > 0;
  const shelf = shelfFor(book.id);
  const shelfMeta = shelf ? SHELF_META[shelf.status] : null;
  return `<article class="book-card" style="--i:${index}">
    <button class="cover" type="button" data-action="open-book" data-id="${book.id}" aria-label="View ${escapeHTML(book.title)}">
      <span class="cover-fallback-text">${escapeHTML(initialsOf(book.title))}</span>
      ${book.cover_image_url ? `<img src="${escapeHTML(book.cover_image_url)}" alt="" loading="lazy" onerror="this.remove()">` : ''}
      <span class="cover-badge">${available ? `${book.available_copies} available` : 'Waitlist'}</span>
    </button>
    <button class="shelf-pin ${shelf ? 'saved' : ''}" type="button" data-action="quick-shelf" data-id="${book.id}"
      aria-label="${shelf ? `Manage shelf for ${escapeHTML(book.title)}` : `Save ${escapeHTML(book.title)} to want to read`}"
      title="${shelf ? `On your ${escapeHTML(shelfMeta.label)} shelf` : 'Save to want to read'}">
      ${shelf ? ICON.bookmarkFill : ICON.bookmark}
    </button>
    <div class="book-body">
      <div class="book-eyebrow">
        <span class="book-cat">${escapeHTML(book.category?.name || 'General')}</span>
        ${shelf ? `<span class="book-shelf-tag ${shelf.status}">${escapeHTML(shelfMeta.short)}</span>` : ''}
      </div>
      <h3 class="book-title">${escapeHTML(book.title)}</h3>
      <p class="book-author">${escapeHTML(book.author?.name || 'Unknown author')}</p>
      <div class="book-meta">
        <span class="rating">${ICON.star} ${(Number(book.average_rating) || 0).toFixed(1)} <span>(${number(book.review_count)})</span></span>
        <span class="badge ${available ? 'green' : 'amber'} plain">${available ? 'In library' : 'Reserved'}</span>
      </div>
      <div class="book-foot">
        ${available
          ? `<button class="btn btn-primary btn-sm" type="button" data-action="borrow" data-id="${book.id}">Borrow</button>`
          : `<button class="btn btn-soft btn-sm" type="button" data-action="reserve" data-id="${book.id}">Reserve</button>`}
        <button class="btn btn-ghost btn-sm" type="button" data-action="open-book" data-id="${book.id}">Details</button>
      </div>
    </div>
  </article>`;
}

/* ----------------------------- dashboard --------------------------- */
async function renderDashboard(root) {
  if (isStaff()) return renderStaffDashboard(root);
  return renderMemberDashboard(root);
}

async function renderStaffDashboard(root) {
  const data = await api('/analytics/dashboard');
  const t = data.totals;
  const f = data.finance;
  const recent = data.recent_loans || [];
  root.innerHTML = `
    <div class="page-head">
      <div>
        <p class="eyebrow">${escapeHTML(greeting())} · ${escapeHTML(roleLabel(state.user.role))}</p>
        <h1>Library overview</h1>
        <p class="sub">${escapeHTML(fullDateToday())} — here is how your library is doing.</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" type="button" data-action="new-member">${ICON.users} Add member</button>
        <button class="btn btn-primary" type="button" data-action="new-checkout">${ICON.plus} New checkout</button>
      </div>
    </div>

    <div class="stat-grid">
      ${statCard(ICON.books, 'Titles in catalog', t.books, { tone: '#4f46e5', i: 0, trend: `${number(t.copies)} copies` })}
      ${statCard(ICON.loans, 'Active loans', t.active_loans, { tone: '#0e9f6e', i: 1, trend: t.overdue_loans ? `${t.overdue_loans} overdue` : 'All on time' })}
      ${statCard(ICON.users, 'Members', t.members, { tone: '#0e7fb8', i: 2, trend: `${number(t.pending_reservations)} holds` })}
      ${statCard(ICON.cash, 'Revenue this month', f.revenue_this_month, { tone: '#d99512', i: 3, moneyValue: true, trend: money(f.revenue_total) + ' total' })}
    </div>

    <div class="cols">
      <section class="card">
        <div class="card-head"><h2>Circulation</h2><span class="hint">Loans · last 6 months</span></div>
        <div class="card-body">${chartHTML(data.monthly || [])}</div>
      </section>
      <section class="card">
        <div class="card-head"><h2>Popular titles</h2><span class="hint">All time</span></div>
        <div class="card-body">
          ${data.popular_books?.length ? `<div class="rank-list">
            ${data.popular_books.map((b, i) => `
              <div class="rank-item">
                <span class="rank-num">${i + 1}</span>
                <div class="rank-main"><p>${escapeHTML(b.title)}</p><span>★ ${Number(b.rating).toFixed(1)} rating</span></div>
                <span class="rank-value">${number(b.loans)} loans</span>
              </div>`).join('')}
          </div>` : emptyState('📚', 'No loans yet', 'Popular titles will appear once readers start borrowing.')}
        </div>
      </section>
    </div>

    <div class="cols">
      <section class="card">
        <div class="card-head">
          <h2>Recent activity</h2>
          <button class="link-btn" type="button" data-view="loans">View all →</button>
        </div>
        <div class="card-body">
          ${recent.length ? `<div class="table-wrap"><table class="table">
            <thead><tr><th>Member</th><th>Book</th><th>Due</th><th>Status</th></tr></thead>
            <tbody>${recent.map((l) => `
              <tr>
                <td class="strong">${escapeHTML(l.member || '—')}</td>
                <td>${escapeHTML(l.book || '—')}</td>
                <td class="sub">${fmtShortDate(l.due_date)}</td>
                <td>${badge(LOAN_BADGE, l.status)}</td>
              </tr>`).join('')}</tbody>
          </table></div>` : emptyState('🕒', 'Quiet shelves', 'No circulation activity yet today.')}
        </div>
      </section>
      <section class="card">
        <div class="card-head"><h2>Quick actions</h2><span class="hint">Librarian tools</span></div>
        <div class="card-body">
          <div class="quick-grid">
            <button class="quick-card" type="button" data-view="browse">
              <span class="qc-icon">${ICON.search}</span>
              <strong>Browse catalog</strong>
              <span>Search, borrow and manage every title.</span>
            </button>
            <button class="quick-card" type="button" data-view="members">
              <span class="qc-icon">${ICON.users}</span>
              <strong>Members</strong>
              <span>Cards, tiers and account status.</span>
            </button>
            <button class="quick-card" type="button" data-view="payments">
              <span class="qc-icon">${ICON.cash}</span>
              <strong>Finance</strong>
              <span>Fines, payments and revenue.</span>
            </button>
            <button class="quick-card" type="button" data-view="events">
              <span class="qc-icon">${ICON.calendar}</span>
              <strong>Events</strong>
              <span>Programs, workshops and bookings.</span>
            </button>
            <button class="quick-card" type="button" data-view="spaces">
              <span class="qc-icon">${ICON.spaces}</span>
              <strong>Spaces</strong>
              <span>Study rooms, studios and resources.</span>
            </button>
            <button class="quick-card" type="button" data-view="audit">
              <span class="qc-icon">${ICON.shield}</span>
              <strong>Audit trail</strong>
              <span>Every sensitive action, accounted for.</span>
            </button>
          </div>
        </div>
      </section>
    </div>`;
  animateStats(root);
  animateBars(root);
}

async function renderMemberDashboard(root) {
  if (!state.shelves.loaded) await loadShelves().catch(() => {});
  const [me, recommended] = await Promise.all([
    api('/analytics/me'),
    api('/books?sort=rating&page_size=4&available_only=true'),
  ]);
  const goal = state.shelves.goal;
  const shelfPreview = [
    ...state.shelves.items.filter((entry) => entry.status === 'reading'),
    ...state.shelves.items.filter((entry) => entry.status === 'want_to_read'),
  ].slice(0, 3);
  const nextDue = me.next_due_date ? fmtDate(me.next_due_date) : 'No due dates';
  const overdueLoans = me.current_loans.filter((loan) => loan.days_left < 0);
  const dueCopy = overdueLoans.length
    ? overdueLoans.length === 1
      ? `<strong style="color:#fff">${escapeHTML(overdueLoans[0].book)}</strong> is <strong style="color:#fff">${Math.abs(overdueLoans[0].days_left)} day${Math.abs(overdueLoans[0].days_left) === 1 ? '' : 's'} overdue</strong>. Renew or return it to avoid another fine.`
      : `<strong style="color:#fff">${overdueLoans.length} loans are overdue</strong>. Renew or return them to avoid another fine.`
    : me.next_due_date
      ? `Your next due date is <strong style="color:#fff">${escapeHTML(nextDue)}</strong>. Browse the shelves or pick up where you left off.`
      : 'You have no books checked out. Find your next read on the shelves.';
  root.innerHTML = `
    <section class="hero">
      <div class="hero-content">
        <div>
          <p class="eyebrow">${escapeHTML(greeting())}, ${escapeHTML(firstName())}</p>
          <h1>What will you <em>read</em> next?</h1>
          <p>${dueCopy}</p>
        </div>
        <div class="hero-chips">
          <div class="hero-chip">
            <span class="hc-icon">${ICON.loans}</span>
            <div><strong>${number(me.active_loans)}</strong><span>Active loans</span></div>
          </div>
          <div class="hero-chip">
            <span class="hc-icon">${ICON.books}</span>
            <div><strong>${number(me.finished_this_year ?? goal.finished)}</strong><span>Finished this year</span></div>
          </div>
          <div class="hero-chip">
            <span class="hc-icon">${ICON.cash}</span>
            <div><strong>${money(me.unpaid_fines)}</strong><span>Unpaid fines</span></div>
          </div>
        </div>
      </div>
    </section>

    <div class="dashboard-shelf-row">
      <section class="card goal-card">
        <div class="goal-ring goal-ring-sm" style="--pct:${Math.max(0, Math.min(100, Number(goal.percent) || 0))}" aria-label="${goal.finished} of ${goal.target} books finished">
          <div><strong>${number(goal.finished)}</strong><span>of ${number(goal.target)}</span></div>
        </div>
        <div class="goal-copy">
          <p class="eyebrow">${goal.year} reading challenge</p>
          <h2>${goal.percent >= 100 ? 'A year of great reading.' : 'Your next chapter awaits.'}</h2>
          <p>${escapeHTML(goalProgressText(goal))}</p>
          <div class="goal-track"><span style="width:${Math.max(0, Math.min(100, Number(goal.percent) || 0))}%"></span></div>
        </div>
        <button class="btn btn-ghost btn-sm" type="button" data-action="edit-goal">${ICON.target} Adjust goal</button>
      </section>

      <section class="card shelf-preview">
        <div class="card-head">
          <h2>Up next on your shelves</h2>
          <button class="link-btn" type="button" data-view="shelves">Manage shelves →</button>
        </div>
        <div class="card-body">
          <div class="shelf-count-pills">
            <button type="button" data-action="open-shelf-tab" data-shelf="want_to_read"><strong>${state.shelves.counts.want_to_read}</strong> Want to read</button>
            <button type="button" data-action="open-shelf-tab" data-shelf="reading"><strong>${state.shelves.counts.reading}</strong> Reading</button>
            <button type="button" data-action="open-shelf-tab" data-shelf="finished"><strong>${state.shelves.counts.finished}</strong> Finished</button>
          </div>
          ${shelfPreview.length ? `<div class="shelf-mini-list">
            ${shelfPreview.map((entry) => `
              <button class="shelf-mini" type="button" data-action="open-book" data-id="${entry.book.id}">
                ${miniCover(entry.book, 'sm')}
                <span class="shelf-mini-copy">
                  <strong>${escapeHTML(entry.book.title)}</strong>
                  <small>${escapeHTML(SHELF_META[entry.status].label)}${entry.status === 'reading' ? ` · ${entry.progress}%` : ''}</small>
                </span>
                ${ICON.arrow}
              </button>`).join('')}
          </div>` : emptyState('🔖', 'Your shelves are open', 'Save a title to “Want to read” and it will wait for you here.',
            '<button class="btn btn-primary btn-sm" type="button" data-view="browse">Find your next read</button>')}
        </div>
      </section>
    </div>

    <div class="section-title">
      <div><h2>Continue reading</h2><p>${me.current_loans.length ? 'Keep an eye on your due dates.' : 'Nothing borrowed right now.'}</p></div>
      <button class="link-btn" type="button" data-view="loans">All my loans →</button>
    </div>
    ${me.current_loans.length ? `<div class="loan-cards">
      ${me.current_loans.map((loan) => {
        const overdue = loan.days_left < 0;
        const pct = overdue ? 100 : Math.max(6, Math.min(100, (loan.days_left / 14) * 100));
        return `<article class="loan-card">
          <span class="mini-cover">${escapeHTML(initialsOf(loan.book || '?'))}</span>
          <div class="loan-card-body">
            <h4>${escapeHTML(loan.book || 'Book')}</h4>
            <p class="sub">Due ${fmtDate(loan.due_date)}</p>
            <div class="progress ${overdue ? 'danger' : loan.days_left <= 3 ? 'warn' : ''}"><span style="width:${pct}%"></span></div>
            <div class="due-row">
              <span>${overdue ? `<strong style="color:var(--danger)">${Math.abs(loan.days_left)} day${Math.abs(loan.days_left) === 1 ? '' : 's'} overdue</strong>` : `<strong>${loan.days_left} day${loan.days_left === 1 ? '' : 's'} left</strong>`}</span>
              <button class="btn btn-soft btn-sm" type="button" data-action="renew-loan" data-id="${loan.id}">Renew</button>
            </div>
          </div>
        </article>`;
      }).join('')}
    </div>` : emptyState('📖', 'Your reading list is waiting', 'Find something wonderful in the catalog and borrow it in one tap.',
      '<button class="btn btn-primary" type="button" data-view="browse">Browse catalog</button>')}

    ${me.my_reservations?.length ? `
      <div class="section-title"><div><h2>Your reservations</h2><p>We’ll let you know the moment a copy is ready.</p></div></div>
      <section class="card"><div class="card-body"><div class="table-wrap"><table class="table">
        <thead><tr><th>Book</th><th>Status</th><th></th></tr></thead>
        <tbody>${me.my_reservations.map((r) => `
          <tr><td class="strong">${escapeHTML(r.book || '—')}</td><td>${badge(RESERVATION_BADGE, r.status)}</td>
          <td class="actions"><button class="btn btn-ghost btn-sm" type="button" data-action="cancel-reservation" data-id="${r.id}">Cancel</button></td></tr>`).join('')}
        </tbody></table></div></div></section>` : ''}

    <div class="section-title">
      <div><h2>Highly rated for you</h2><p>Hand-picked from the top of our shelves.</p></div>
      <button class="link-btn" type="button" data-view="browse">See all →</button>
    </div>
    <div class="book-grid">
      ${recommended.items.map((book, i) => bookCard(book, i)).join('')}
    </div>`;
}

/* ------------------------------ browse ----------------------------- */
async function renderBrowse(root) {
  if (!state.categories.length) {
    state.categories = await api('/catalog/categories');
  }
  root.innerHTML = `
    <div class="page-head">
      <div>
        <p class="eyebrow">The collection</p>
        <h1>Browse the catalog</h1>
        <p class="sub">Classics, new voices, science and stories — there is something here for everyone.</p>
      </div>
      ${isStaff() ? `<div class="head-actions">
        <button class="btn btn-primary" type="button" data-action="new-book">${ICON.plus} Add a book</button>
      </div>` : ''}
    </div>
    <div class="toolbar">
      <div class="search">
        ${ICON.search}
        <input id="browse-search" type="search" value="${escapeHTML(state.books.q)}" placeholder="Search by title, author, or ISBN…" aria-label="Search books" />
      </div>
      <select class="select" id="browse-sort" aria-label="Sort books">
        <option value="newest" ${state.books.sort === 'newest' ? 'selected' : ''}>Newest first</option>
        <option value="title" ${state.books.sort === 'title' ? 'selected' : ''}>Title A–Z</option>
        <option value="rating" ${state.books.sort === 'rating' ? 'selected' : ''}>Highest rated</option>
        <option value="popular" ${state.books.sort === 'popular' ? 'selected' : ''}>Most rated</option>
      </select>
    </div>
    <div class="chip-row" id="category-chips" style="margin-bottom:16px">
      <button class="chip ${state.books.category === '' ? 'active' : ''}" type="button" data-category="">All genres</button>
      ${state.categories.map((c) => `
        <button class="chip ${String(state.books.category) === String(c.id) ? 'active' : ''}" type="button" data-category="${c.id}">${escapeHTML(c.name)}</button>`).join('')}
    </div>
    <p class="browse-meta" id="browse-meta">Loading the shelves…</p>
    <div class="book-grid" id="books-grid">${Array.from({ length: 8 }).map(() => '<div class="skeleton skel-card"></div>').join('')}</div>
    <div class="pagination" id="browse-pagination"></div>`;

  const search = $('#browse-search');
  search?.addEventListener('input', debounce(() => {
    state.books.q = search.value.trim();
    state.books.page = 1;
    loadBooksGrid();
  }, 320));
  $('#browse-sort')?.addEventListener('change', (event) => {
    state.books.sort = event.target.value;
    state.books.page = 1;
    loadBooksGrid();
  });
  $('#category-chips')?.addEventListener('click', (event) => {
    const chip = event.target.closest('[data-category]');
    if (!chip) return;
    state.books.category = chip.dataset.category;
    state.books.page = 1;
    $$('#category-chips .chip').forEach((c) => c.classList.toggle('active', c === chip));
    loadBooksGrid();
  });
  await loadBooksGrid();
}

async function loadBooksGrid() {
  const grid = $('#books-grid');
  if (!grid) return;
  const requestId = ++state.browseReq;
  const params = new URLSearchParams({
    page: String(state.books.page),
    page_size: String(state.books.pageSize),
    sort: state.books.sort,
    available_only: 'false',
  });
  if (state.books.q) params.set('q', state.books.q);
  if (state.books.category) params.set('category_id', state.books.category);

  try {
    const data = await api(`/books?${params.toString()}`);
    if (requestId !== state.browseReq) return;
    state.books.pages = data.pages;
    state.books.total = data.total;
    const meta = $('#browse-meta');
    if (meta) {
      meta.textContent = data.total
        ? `Showing ${(data.page - 1) * data.page_size + 1}–${Math.min(data.page * data.page_size, data.total)} of ${number(data.total)} titles`
        : 'No titles match your search yet.';
    }
    grid.innerHTML = data.items.length
      ? data.items.map((book, i) => bookCard(book, i)).join('')
      : `<div style="grid-column:1/-1">${emptyState('🔍', 'No books found', 'Try a different title, author or genre.',
          '<button class="btn btn-ghost" type="button" data-action="clear-filters">Clear filters</button>')}</div>`;
    const pagination = $('#browse-pagination');
    if (pagination) {
      pagination.innerHTML = data.pages > 1 ? `
        <button class="btn btn-ghost btn-sm" type="button" data-action="browse-page" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>← Previous</button>
        <span>Page <strong>${data.page}</strong> of ${data.pages}</span>
        <button class="btn btn-ghost btn-sm" type="button" data-action="browse-page" data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Next →</button>` : '';
    }
  } catch (error) {
    grid.innerHTML = `<div style="grid-column:1/-1">${errorState(error.message)}</div>`;
  }
}

async function openBookModal(id) {
  openModal('<div class="modal-body"><div class="skeleton" style="height:280px;border-radius:18px"></div></div>');
  try {
    const [book, copies, reviews] = await Promise.all([
      api(`/books/${id}`),
      api(`/books/${id}/copies`),
      api(`/books/${id}/reviews`),
    ]);
    const available = Number(book.available_copies) > 0;
    const availableCopies = copies.filter((c) => c.status === 'available');
    const canReview = !!state.user;
    const myReview = reviews.find((r) => r.member_id === state.user?.id);
    const myShelf = shelfFor(book.id);
    setModalHTML(`
      <div class="modal-body">
        <div class="book-detail">
          <div class="cover">
            <span class="cover-fallback-text">${escapeHTML(initialsOf(book.title))}</span>
            ${book.cover_image_url ? `<img src="${escapeHTML(book.cover_image_url)}" alt="${escapeHTML(book.title)} cover" onerror="this.remove()">` : ''}
          </div>
          <div>
            <h2>${escapeHTML(book.title)}</h2>
            <p class="byline">${escapeHTML(book.author?.name || 'Unknown author')}${book.publication_year ? ` · ${book.publication_year}` : ''}${book.publisher?.name ? ` · ${escapeHTML(book.publisher.name)}` : ''}</p>
            <div class="detail-meta">
              <span class="badge violet plain">${escapeHTML(book.category?.name || 'General')}</span>
              <span class="badge ${available ? 'green' : 'amber'} plain">${available ? `${book.available_copies} of ${book.total_copies} available` : 'All copies on loan'}</span>
              <span class="badge grey plain">${escapeHTML(book.book_format)}</span>
              <span class="rating">${ICON.star} ${Number(book.average_rating || 0).toFixed(1)} <span>(${number(book.review_count)} ratings)</span></span>
            </div>
            <div class="shelf-detail">
              <div class="shelf-detail-head">
                <span>${ICON.bookmark} My shelves</span>
                <span class="hint">${myShelf ? `Saved · ${escapeHTML(SHELF_META[myShelf.status].label)}` : 'Private to you'}</span>
              </div>
              <div class="shelf-switch" role="group" aria-label="Choose a reading shelf">
                ${Object.entries(SHELF_META).map(([status, meta]) => `
                  <button class="shelf-switch-btn ${myShelf?.status === status ? 'active' : ''}" type="button"
                    data-action="set-shelf" data-shelf="${status}" data-id="${book.id}">${meta.icon}<span>${meta.short}</span></button>`).join('')}
              </div>
              ${myShelf ? `<button class="link-btn shelf-remove" type="button" data-action="remove-shelf" data-id="${book.id}">Remove from my shelves</button>` : ''}
            </div>
            <p class="book-desc">${escapeHTML(book.description || 'No description has been added for this title yet.')}</p>
            <div class="detail-meta">
              ${book.isbn ? `<span class="badge grey plain">ISBN ${escapeHTML(book.isbn)}</span>` : ''}
              <span class="badge grey plain">${escapeHTML(book.language || 'English')}</span>
              <span class="badge grey plain">${availableCopies.length} on shelf</span>
            </div>
            <div class="detail-actions">
              ${available
                ? `<button class="btn btn-primary" type="button" data-action="borrow" data-id="${book.id}">${ICON.book} Borrow this book</button>`
                : `<button class="btn btn-soft" type="button" data-action="reserve" data-id="${book.id}">${ICON.clock} Reserve a copy</button>`}
              ${book.digital_file_url ? `<a class="btn btn-soft" href="${escapeHTML(book.digital_file_url)}" target="_blank" rel="noopener noreferrer">${ICON.spark} Open digital edition</a>` : ''}
              <button class="btn btn-ghost" type="button" data-close>Keep browsing</button>
            </div>
          </div>
        </div>
        <div class="review-block">
          <h3>Reader reviews ${reviews.length ? `(${reviews.length})` : ''}</h3>
          ${reviews.length ? reviews.map((r) => `
            <div class="review-item">
              <div class="review-head"><span>${escapeHTML(r.member_name || 'Reader')}</span><span class="stars">${'★'.repeat(r.rating)}${'☆'.repeat(5 - r.rating)}</span></div>
              ${r.comment ? `<p>${escapeHTML(r.comment)}</p>` : ''}
            </div>`).join('') : '<p class="book-desc">No written reviews yet — be the first to share your thoughts.</p>'}
          ${canReview ? `
            <form id="review-form" class="review-form" data-book-id="${book.id}">
              <select class="select" name="rating" required aria-label="Rating">
                ${[5, 4, 3, 2, 1].map((n) => `<option value="${n}" ${myReview?.rating === n ? 'selected' : ''}>${n} ★</option>`).join('')}
              </select>
              <input class="review-input" name="comment" placeholder="Share a thought about this book…" value="${escapeHTML(myReview?.comment || '')}" maxlength="500" />
              <button class="btn btn-primary btn-sm" type="submit">${myReview ? 'Update review' : 'Post review'}</button>
            </form>` : ''}
        </div>
      </div>`);
  } catch (error) {
    closeModal();
    toast(error.message, 'error');
  }
}

/* ------------------------------ shelves ---------------------------- */
function shelfEntryCard(entry, index = 0) {
  const book = entry.book;
  const meta = SHELF_META[entry.status];
  const tone = { want_to_read: 'violet', reading: 'blue', finished: 'green' }[entry.status];
  return `<article class="shelf-entry ${entry.status}" style="--i:${index}">
    <button class="shelf-entry-cover" type="button" data-action="open-book" data-id="${book.id}" aria-label="View ${escapeHTML(book.title)}">
      ${miniCover(book)}
    </button>
    <div class="shelf-entry-body">
      <div class="shelf-entry-head">
        <span class="badge ${tone} plain">${meta.icon} ${meta.label}</span>
        <button class="shelf-entry-remove" type="button" data-action="remove-shelf" data-id="${book.id}" aria-label="Remove ${escapeHTML(book.title)} from shelves" title="Remove from shelves">×</button>
      </div>
      <h3>${escapeHTML(book.title)}</h3>
      <p class="shelf-entry-author">${escapeHTML(book.author?.name || 'Unknown author')}</p>
      <p class="shelf-entry-note">${
        entry.status === 'finished'
          ? `Finished ${fmtDate(entry.finished_at || entry.updated_at)}`
          : entry.status === 'reading'
            ? `Started ${entry.started_at ? fmtDate(entry.started_at) : 'recently'}`
            : `Saved ${timeAgo(entry.updated_at)}`
      }</p>
      ${entry.status === 'reading' ? `
        <div class="shelf-progress">
          <div class="shelf-progress-label"><span>Reading progress</span><strong data-progress-label="${book.id}">${entry.progress}%</strong></div>
          <input type="range" min="0" max="100" step="1" value="${entry.progress}" data-shelf-progress="${book.id}" aria-label="Reading progress for ${escapeHTML(book.title)}" />
        </div>` : ''}
      <div class="shelf-entry-actions">
        ${entry.status !== 'reading' ? `<button class="btn btn-soft btn-sm" type="button" data-action="set-shelf" data-shelf="reading" data-id="${book.id}">${entry.status === 'finished' ? 'Read again' : 'Start reading'}</button>` : ''}
        ${entry.status !== 'finished' ? `<button class="btn btn-success btn-sm" type="button" data-action="set-shelf" data-shelf="finished" data-id="${book.id}">${ICON.check} Finished</button>` : ''}
        <button class="btn btn-ghost btn-sm" type="button" data-action="open-book" data-id="${book.id}">Details</button>
      </div>
    </div>
  </article>`;
}

async function renderShelves(root) {
  await loadShelves(true);
  const { items, counts, goal } = state.shelves;
  const tabs = [
    ['all', 'All books', items.length],
    ['want_to_read', 'Want to read', counts.want_to_read],
    ['reading', 'Reading now', counts.reading],
    ['finished', 'Finished', counts.finished],
  ];
  if (!tabs.some(([key]) => key === state.shelfTab)) state.shelfTab = 'all';
  const visible = state.shelfTab === 'all'
    ? items
    : items.filter((entry) => entry.status === state.shelfTab);

  root.innerHTML = `
    <div class="page-head">
      <div>
        <p class="eyebrow">Your reading life</p>
        <h1>My shelves</h1>
        <p class="sub">Keep the books you want close, track what you are reading and celebrate every finish.</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" type="button" data-action="edit-goal">${ICON.target} Edit goal</button>
        <button class="btn btn-primary" type="button" data-view="browse">${ICON.search} Find a book</button>
      </div>
    </div>

    <section class="goal-hero">
      <div class="goal-ring" style="--pct:${Math.max(0, Math.min(100, Number(goal.percent) || 0))}" aria-label="${goal.finished} of ${goal.target} books finished">
        <div><strong>${number(goal.finished)}</strong><span>of ${number(goal.target)}</span></div>
      </div>
      <div class="goal-hero-copy">
        <p class="eyebrow">${goal.year} reading challenge</p>
        <h2>${goal.percent >= 100 ? 'You finished your challenge!' : `${number(goal.finished)} books finished so far`}</h2>
        <p>${escapeHTML(goalProgressText(goal))} Your goal is personal — adjust it whenever your reading life changes.</p>
        <div class="goal-track"><span style="width:${Math.max(0, Math.min(100, Number(goal.percent) || 0))}%"></span></div>
        <div class="goal-facts">
          <span><strong>${counts.want_to_read}</strong> Want to read</span>
          <span><strong>${counts.reading}</strong> Reading now</span>
          <span><strong>${counts.finished}</strong> Finished</span>
        </div>
      </div>
    </section>

    <div class="shelf-tabs" role="tablist" aria-label="Filter shelves">
      ${tabs.map(([key, label, count]) => `
        <button class="shelf-tab ${state.shelfTab === key ? 'active' : ''}" type="button" role="tab" aria-selected="${state.shelfTab === key}" data-action="shelf-tab" data-shelf="${key}">
          ${label}<span>${count}</span>
        </button>`).join('')}
    </div>

    ${visible.length ? `<div class="shelf-grid">
      ${visible.map((entry, index) => shelfEntryCard(entry, index)).join('')}
    </div>` : emptyState('📚', state.shelfTab === 'all' ? 'Your shelves are waiting' : 'Nothing here yet',
      state.shelfTab === 'all'
        ? 'Save a book from the catalog and it will appear on your personal shelves.'
        : 'Browse the catalog and add a title to this shelf.',
      '<button class="btn btn-primary" type="button" data-view="browse">Browse catalog</button>')}

    <div class="shelf-tip">
      ${ICON.spark}
      <div><strong>Your shelves, your pace.</strong><span>Only you can see these lists. Finished books count toward your annual goal automatically.</span></div>
    </div>`;
}

async function saveShelf(bookId, shelf, element = null) {
  const job = async () => {
    const entry = await api(`/shelves/me/${bookId}`, {
      method: 'PUT',
      body: { status: shelf },
    });
    await loadShelves(true);
    toast(entry.status === 'finished'
      ? `Finished “${entry.book.title}” — added to your reading goal.`
      : entry.status === 'reading'
        ? `“${entry.book.title}” is now on your Reading shelf.`
        : `Saved “${entry.book.title}” to Want to read.`);
    if ($('#modal-root .modal')) await openBookModal(bookId);
    else if (state.view === 'browse') await loadBooksGrid();
    else await setView(state.view);
  };
  if (element) await withBusy(element, async () => {
    try { await job(); } catch (error) { toast(error.message, 'error'); }
  });
  else {
    try { await job(); } catch (error) { toast(error.message, 'error'); }
  }
}

async function quickShelf(bookId, element) {
  if (shelfFor(bookId)) {
    await openBookModal(bookId);
    return;
  }
  await saveShelf(bookId, 'want_to_read', element);
}

async function removeShelf(bookId, element) {
  await withBusy(element, async () => {
    try {
      await api(`/shelves/me/${bookId}`, { method: 'DELETE' });
      await loadShelves(true);
      toast('Removed from your shelves.', 'info');
      if ($('#modal-root .modal')) {
        closeModal();
        await refreshCurrentView();
      } else if (state.view === 'shelves' || state.view === 'dashboard') {
        await setView(state.view);
      } else {
        await loadBooksGrid();
      }
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

async function updateShelfProgress(bookId, value) {
  const label = document.querySelector(`[data-progress-label="${bookId}"]`);
  if (label) label.textContent = `${value}%`;
  try {
    await api(`/shelves/me/${bookId}`, {
      method: 'PUT',
      body: { status: 'reading', progress: Number(value) },
    });
    await loadShelves(true);
  } catch (error) {
    toast(error.message, 'error');
    await loadShelves(true).catch(() => {});
    await setView(state.view);
  }
}

function openGoalModal() {
  const goal = state.shelves.goal;
  openModal(`
    <div class="modal-body">
      <p class="eyebrow">Reading challenge</p>
      <h2 style="font-family:var(--font-display);font-size:26px;font-weight:600;margin-bottom:6px">Set your ${goal.year} goal</h2>
      <p class="sub" style="color:var(--muted);font-size:13px;margin-bottom:18px">Choose a number that feels motivating, not overwhelming. You can change it at any time.</p>
      <form id="goal-form">
        <label class="field"><span>Books to read in ${goal.year}</span><input name="target" type="number" min="1" max="365" value="${goal.target}" required /></label>
        <div class="goal-modal-note">${ICON.target} ${goal.finished} finished so far · ${Math.max(0, goal.target - goal.finished)} to go</div>
        <button class="btn btn-primary btn-block" type="submit">${ICON.check} Save goal</button>
      </form>
    </div>`);
}

/* ------------------------------- loans ----------------------------- */
async function renderLoans(root) {
  const staff = isStaff();
  const [loansData, fines, reservations] = await Promise.all([
    api('/loans?limit=300'),
    api('/fines'),
    api('/reservations'),
  ]);
  const loans = loansData.items || [];
  const active = loans.filter((l) => ['active', 'overdue'].includes(l.status));
  const overdue = loans.filter((l) => l.status === 'overdue');
  const holds = reservations.filter((r) => ['pending', 'ready'].includes(r.status));
  const unpaid = fines.filter((f) => f.status === 'unpaid');

  const tabs = staff
    ? [['active', 'Active loans'], ['overdue', 'Overdue'], ['all', 'All loans'], ['reservations', 'Reservations'], ['fines', 'Fines']]
    : [['active', 'My loans'], ['reservations', 'Reservations'], ['fines', 'Fines']];
  if (!tabs.some(([key]) => key === state.loansTab)) state.loansTab = 'active';

  root.innerHTML = `
    <div class="page-head">
      <div>
        <p class="eyebrow">${staff ? 'Circulation desk' : 'Your reading'}</p>
        <h1>${staff ? 'Loans & circulation' : 'My library'}</h1>
        <p class="sub">${staff ? 'Check books in and out, renew loans and manage holds.' : 'Track due dates, renew books and settle fines.'}</p>
      </div>
      <div class="head-actions">
        ${staff
          ? `<button class="btn btn-primary" type="button" data-action="new-checkout">${ICON.plus} New checkout</button>`
          : `<button class="btn btn-ghost" type="button" data-view="browse">${ICON.search} Find a book</button>`}
      </div>
    </div>
    <div class="stat-grid">
      ${statCard(ICON.loans, staff ? 'Active loans' : 'Currently reading', active.length, { tone: '#4f46e5', i: 0 })}
      ${statCard(ICON.clock, 'Overdue', overdue.length, { tone: '#e11d48', i: 1, trend: overdue.length ? 'Needs attention' : 'All good' })}
      ${statCard(ICON.book, 'Active holds', holds.length, { tone: '#0e7fb8', i: 2 })}
      ${statCard(ICON.cash, 'Unpaid fines', unpaid.reduce((s, f) => s + Number(f.amount), 0), { tone: '#d99512', i: 3, moneyValue: true })}
    </div>
    <div class="tab-row" id="loan-tabs">
      ${tabs.map(([key, label]) => `<button class="tab ${state.loansTab === key ? 'active' : ''}" type="button" data-loan-tab="${key}">${label}${key === 'overdue' && overdue.length ? ` · ${overdue.length}` : ''}</button>`).join('')}
    </div>
    <div id="loans-tab-content"></div>`;

  animateStats(root);
  const paint = () => renderLoansTab({ loans, fines, reservations, staff });
  $('#loan-tabs')?.addEventListener('click', (event) => {
    const tab = event.target.closest('[data-loan-tab]');
    if (!tab) return;
    state.loansTab = tab.dataset.loanTab;
    $$('#loan-tabs .tab').forEach((t) => t.classList.toggle('active', t === tab));
    paint();
  });
  paint();
}

function renderLoansTab({ loans, fines, reservations, staff }) {
  const container = $('#loans-tab-content');
  if (!container) return;
  const tab = state.loansTab;

  if (tab === 'reservations') {
    const holds = reservations.filter((r) => ['pending', 'ready'].includes(r.status));
    container.innerHTML = holds.length ? `<section class="card"><div class="card-body"><div class="table-wrap"><table class="table">
      <thead><tr><th>Book</th>${staff ? '<th>Member</th>' : ''}<th>Reserved</th><th>Expires</th><th>Status</th><th></th></tr></thead>
      <tbody>${holds.map((r) => `
        <tr>
          <td class="strong">${escapeHTML(r.book_title || '—')}</td>
          ${staff ? `<td>${escapeHTML(r.member_name || '—')}</td>` : ''}
          <td class="sub">${fmtDate(r.reserved_at)}</td>
          <td class="sub">${r.expires_at ? fmtDate(r.expires_at) : '—'}</td>
          <td>${badge(RESERVATION_BADGE, r.status)}</td>
          <td class="actions"><button class="btn btn-ghost btn-sm" type="button" data-action="cancel-reservation" data-id="${r.id}">Cancel</button></td>
        </tr>`).join('')}</tbody></table></div></div></section>`
      : emptyState('🔖', 'No active reservations', 'When every copy of a book is out, reserve it here and we’ll hold it for you.');
    return;
  }

  if (tab === 'fines') {
    const visible = staff ? fines : fines;
    container.innerHTML = visible.length ? `<section class="card"><div class="card-body"><div class="table-wrap"><table class="table">
      <thead><tr>${staff ? '<th>Member</th>' : ''}<th>Reason</th><th>Amount</th><th>Status</th><th>Created</th><th></th></tr></thead>
      <tbody>${visible.map((f) => `
        <tr>
          ${staff ? `<td class="strong">${escapeHTML(f.member_name || '—')}</td>` : ''}
          <td>${escapeHTML(f.reason)}${f.book_title ? `<div class="sub">${escapeHTML(f.book_title)}</div>` : ''}</td>
          <td class="strong">${money(f.amount)}</td>
          <td>${badge(FINE_BADGE, f.status)}</td>
          <td class="sub">${fmtDate(f.created_at)}</td>
          <td class="actions">
            ${f.status === 'unpaid' ? `<button class="btn btn-primary btn-sm" type="button" data-action="pay-fine" data-id="${f.id}">Pay now</button>` : ''}
            ${staff && f.status === 'unpaid' ? `<button class="btn btn-ghost btn-sm" type="button" data-action="waive-fine" data-id="${f.id}">Waive</button>` : ''}
          </td>
        </tr>`).join('')}</tbody></table></div></div></section>`
      : emptyState('✓', 'No fines', 'Everything is settled — thank you for returning your books on time.');
    return;
  }

  const filtered = tab === 'active'
    ? loans.filter((l) => ['active', 'overdue'].includes(l.status))
    : tab === 'overdue'
      ? loans.filter((l) => l.status === 'overdue')
      : loans;

  container.innerHTML = filtered.length ? `<section class="card"><div class="card-body"><div class="table-wrap"><table class="table">
    <thead><tr><th>Book</th>${staff ? '<th>Member</th>' : ''}<th>Borrowed</th><th>Due</th><th>Status</th><th></th></tr></thead>
    <tbody>${filtered.map((l) => {
      const canRenew = l.status === 'active' && l.renewed_count < 2 && l.days_overdue === 0;
      return `<tr>
        <td><div class="cell-book">${miniCover({ title: l.book_title })}<div><div class="strong">${escapeHTML(l.book_title || '—')}</div><div class="sub">${l.copy_barcode ? escapeHTML(l.copy_barcode) : 'Digital copy'}</div></div></div></td>
        ${staff ? `<td>${escapeHTML(l.member_name || '—')}</td>` : ''}
        <td class="sub">${fmtDate(l.borrowed_at)}</td>
        <td class="sub">${fmtDate(l.due_date)}${l.status === 'overdue' && l.days_overdue ? `<div class="sub" style="color:var(--danger)">${l.days_overdue} d overdue</div>` : ''}</td>
        <td>${badge(LOAN_BADGE, l.status)}</td>
        <td class="actions">
          ${canRenew ? `<button class="btn btn-soft btn-sm" type="button" data-action="renew-loan" data-id="${l.id}">Renew</button>` : ''}
          ${['active', 'overdue'].includes(l.status) ? `<button class="btn btn-ghost btn-sm" type="button" data-action="return-loan" data-id="${l.id}">Return</button>` : ''}
        </td>
      </tr>`;
    }).join('')}</tbody></table></div></div></section>`
    : emptyState('📚', tab === 'overdue' ? 'Nothing overdue' : 'No loans here yet',
      tab === 'overdue' ? 'Every book is safely within its due date.' : 'Borrow a book from the catalog and it will show up here.');
}

async function openCheckoutModal() {
  openModal('<div class="modal-body"><div class="skeleton" style="height:240px;border-radius:16px"></div></div>');
  try {
    const [members, books] = await Promise.all([
      api('/members?role=member&limit=200'),
      api('/books?page_size=100&available_only=true&sort=title'),
    ]);
    setModalHTML(`
      <div class="modal-body">
        <p class="eyebrow">Circulation</p>
        <h2 style="font-family:var(--font-display);font-size:26px;font-weight:600;margin-bottom:6px">New checkout</h2>
        <p class="sub" style="color:var(--muted);font-size:13px;margin-bottom:18px">Issue a book to a member and set the loan length.</p>
        <form id="checkout-form">
          <label class="field"><span>Member</span>
            <select id="checkout-member" required>
              ${members.length ? members.map((m) => `<option value="${m.id}">${escapeHTML(m.full_name)} · ${escapeHTML(m.library_card_number || m.email)}</option>`).join('') : '<option value="">No members yet</option>'}
            </select>
          </label>
          <label class="field"><span>Book</span>
            <select id="checkout-book" required>
              ${books.items.length ? books.items.map((b) => `<option value="${b.id}">${escapeHTML(b.title)} — ${escapeHTML(b.author?.name || 'Unknown')} (${b.available_copies} left)</option>`).join('') : '<option value="">No books available</option>'}
            </select>
          </label>
          <label class="field"><span>Loan length (days)</span>
            <input id="checkout-days" type="number" min="1" max="90" value="14" required />
          </label>
          <button class="btn btn-primary btn-block" type="submit" ${!members.length || !books.items.length ? 'disabled' : ''}>${ICON.check} Check out book</button>
        </form>
      </div>`);
  } catch (error) {
    closeModal();
    toast(error.message, 'error');
  }
}

/* ------------------------------ members ---------------------------- */
async function renderMembers(root) {
  root.innerHTML = `
    <div class="page-head">
      <div>
        <p class="eyebrow">People</p>
        <h1>Members</h1>
        <p class="sub">Manage library cards, membership tiers and account access.</p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" type="button" data-action="new-member">${ICON.plus} Add member</button>
      </div>
    </div>
    <div class="toolbar">
      <div class="search">
        ${ICON.search}
        <input id="member-search" type="search" placeholder="Search by name, email or library card…" aria-label="Search members" />
      </div>
    </div>
    <div id="members-table"><div class="skeleton" style="height:300px;border-radius:20px"></div></div>`;
  const input = $('#member-search');
  input?.addEventListener('input', debounce(() => loadMembersTable(input.value.trim()), 320));
  await loadMembersTable('');
}

async function loadMembersTable(query = '') {
  const container = $('#members-table');
  if (!container) return;
  try {
    const members = await api(`/members?role=member&limit=200${query ? `&q=${encodeURIComponent(query)}` : ''}`);
    container.innerHTML = members.length ? `<section class="card"><div class="card-body" style="padding-top:8px"><div class="table-wrap"><table class="table">
      <thead><tr><th>Member</th><th>Library card</th><th>Membership</th><th>Joined</th><th>Status</th><th></th></tr></thead>
      <tbody>${members.map((m, index) => `
        <tr>
          <td><div class="cell-book">
            <span class="avatar-sm tone-${(index % 4) + 1}">${escapeHTML(initialsOf(m.full_name))}</span>
            <div><div class="strong">${escapeHTML(m.full_name)}</div><div class="sub">${escapeHTML(m.email)}</div></div>
          </div></td>
          <td class="sub" style="font-family:ui-monospace,monospace">${escapeHTML(m.library_card_number || '—')}</td>
          <td>
            <select class="select" style="padding:6px 28px 6px 10px;font-size:12px" data-tier-member="${m.id}" aria-label="Membership tier">
              ${['basic', 'student', 'premium', 'family'].map((tier) => `<option value="${tier}" ${m.membership_tier === tier ? 'selected' : ''}>${tierLabel(tier)}</option>`).join('')}
            </select>
          </td>
          <td class="sub">${fmtDate(m.created_at)}</td>
          <td>${m.is_active ? '<span class="badge green">Active</span>' : '<span class="badge grey">Disabled</span>'}</td>
          <td class="actions">
            <button class="btn ${m.is_active ? 'btn-ghost' : 'btn-success'} btn-sm" type="button" data-action="toggle-member" data-id="${m.id}">${m.is_active ? 'Deactivate' : 'Reactivate'}</button>
          </td>
        </tr>`).join('')}</tbody></table></div></div></section>`
      : emptyState('👥', 'No members found', query ? 'No member matches that search.' : 'Add your first member to get started.');
  } catch (error) {
    container.innerHTML = errorState(error.message);
  }
}

async function openMemberModal() {
  openModal(`
    <div class="modal-body">
      <p class="eyebrow">New account</p>
      <h2 style="font-family:var(--font-display);font-size:26px;font-weight:600;margin-bottom:6px">Add a member</h2>
      <p class="sub" style="color:var(--muted);font-size:13px;margin-bottom:18px">Create a library account and issue a digital card instantly.</p>
      <form id="member-form">
        <div class="form-grid">
          <label class="field full"><span>Full name</span><input name="full_name" required minlength="2" placeholder="Ada Lovelace" /></label>
          <label class="field"><span>Email</span><input name="email" type="email" required placeholder="ada@example.com" /></label>
          <label class="field"><span>Temporary password</span><input name="password" type="password" required minlength="8" placeholder="At least 8 characters" /></label>
          <label class="field"><span>Phone</span><input name="phone" placeholder="+91 90000 00000" /></label>
          <label class="field"><span>Role</span>
            <select name="role"><option value="member">Member</option><option value="librarian">Librarian</option></select>
          </label>
        </div>
        <button class="btn btn-primary btn-block" type="submit" style="margin-top:6px">${ICON.plus} Create account</button>
      </form>
    </div>`);
}

/* ------------------------------- events ---------------------------- */
async function renderEvents(root) {
  const [eventsData, branches] = await Promise.all([
    api('/events?upcoming_only=true'),
    api('/catalog/branches').catch(() => []),
  ]);
  const branchName = (id) => branches.find((b) => b.id === id)?.name || 'Central Library';
  const events = eventsData.items || [];
  root.innerHTML = `
    <div class="page-head">
      <div>
        <p class="eyebrow">What’s on</p>
        <h1>Events & programs</h1>
        <p class="sub">Workshops, author talks and story hours — come and join the community.</p>
      </div>
      ${isStaff() ? `<div class="head-actions"><button class="btn btn-primary" type="button" data-action="new-event">${ICON.plus} Create event</button></div>` : ''}
    </div>
    ${events.length ? `<div class="event-grid">
      ${events.map((event, index) => {
        const date = fmtMonthDay(event.start_time);
        const full = Number(event.registered_count) >= Number(event.capacity);
        const free = Number(event.ticket_price) === 0;
        return `<article class="event-card" style="--i:${index}">
          <div class="event-top">
            <div class="event-date"><strong>${date.day}</strong><span>${date.month}</span></div>
            <div>
              <h3>${escapeHTML(event.title)}</h3>
              <p class="event-where">${escapeHTML(branchName(event.branch_id))} · ${escapeHTML(fmtDateTime(event.start_time))}</p>
            </div>
          </div>
          <div class="event-body">
            <p class="event-desc">${escapeHTML(event.description || 'Join us for this library program.')}</p>
            <div class="event-foot">
              <div class="event-price">${free ? 'Free entry' : money(event.ticket_price)}<span>${free ? 'Everyone welcome' : 'per person'}</span></div>
              <span class="event-capacity">${event.registered_count}/${event.capacity} registered</span>
              <button class="btn ${full ? 'btn-ghost' : 'btn-primary'} btn-sm" type="button" data-action="register-event" data-id="${event.id}" ${full ? 'disabled' : ''}>${full ? 'Fully booked' : 'Register'}</button>
            </div>
          </div>
        </article>`;
      }).join('')}
    </div>` : emptyState('🗓️', 'No upcoming events', 'Check back soon — new programs are added every week.')}`;
}

async function openEventModal() {
  openModal('<div class="modal-body"><div class="skeleton" style="height:260px;border-radius:16px"></div></div>');
  try {
    const branches = await api('/catalog/branches').catch(() => []);
    const tomorrow = new Date(Date.now() + 86400000);
    tomorrow.setHours(18, 0, 0, 0);
    const toInput = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    setModalHTML(`
      <div class="modal-body">
        <p class="eyebrow">Programming</p>
        <h2 style="font-family:var(--font-display);font-size:26px;font-weight:600;margin-bottom:6px">Create an event</h2>
        <p class="sub" style="color:var(--muted);font-size:13px;margin-bottom:18px">Publish a new program to the community calendar.</p>
        <form id="event-form">
          <label class="field"><span>Title</span><input name="title" required minlength="2" placeholder="Author talk: ..." /></label>
          <label class="field"><span>Description</span><textarea name="description" rows="3" placeholder="What should attendees expect?"></textarea></label>
          <div class="form-grid">
            <label class="field"><span>Starts</span><input name="start_time" type="datetime-local" value="${toInput(tomorrow)}" required /></label>
            <label class="field"><span>Ends</span><input name="end_time" type="datetime-local" value="${toInput(new Date(tomorrow.getTime() + 2 * 3600000))}" required /></label>
            <label class="field"><span>Branch</span>
              <select name="branch_id"><option value="">Central Library</option>${branches.map((b) => `<option value="${b.id}">${escapeHTML(b.name)}</option>`).join('')}</select>
            </label>
            <label class="field"><span>Capacity</span><input name="capacity" type="number" min="1" value="40" required /></label>
            <label class="field"><span>Ticket price (USD)</span><input name="ticket_price" type="number" min="0" step="0.01" value="0" /></label>
          </div>
          <button class="btn btn-primary btn-block" type="submit" style="margin-top:6px">${ICON.calendar} Publish event</button>
        </form>
      </div>`);
  } catch (error) {
    closeModal();
    toast(error.message, 'error');
  }
}

/* ------------------------------ payments --------------------------- */
const PLANS = [
  { tier: 'basic', name: 'Basic', price: 0, blurb: 'Everything you need to start reading.', features: ['Borrow up to 5 books', '14-day loans', 'Reserve titles', 'Community events'] },
  { tier: 'student', name: 'Student', price: 4.99, blurb: 'For curious minds on a budget.', features: ['Borrow up to 10 books', '21-day loans', '2 renewals per book', 'Study room discounts'] },
  { tier: 'premium', name: 'Premium', price: 9.99, blurb: 'The complete library experience.', features: ['Borrow up to 15 books', '21-day loans', 'Priority reservations', 'Free workshop tickets'] },
  { tier: 'family', name: 'Family', price: 14.99, blurb: 'One card, the whole household.', features: ['Up to 4 linked cards', '25 books at a time', 'Family event access', 'Extended weekend hours'] },
];

function revenueChartHTML(monthly) {
  const max = Math.max(...monthly.map((m) => Number(m.revenue) || 0), 1);
  return `<div class="chart">${monthly.map((m) => {
    const value = Number(m.revenue) || 0;
    const height = value > 0 ? Math.max(3, Math.round((value / max) * 100)) : 0;
    return `
      <div class="chart-col" title="${money(value)} revenue in ${escapeHTML(m.month)}">
        <div class="chart-bars">
          <div class="chart-bar alt" data-height="${height}"></div>
        </div>
        <span class="chart-label">${escapeHTML(m.month)}</span>
      </div>`;
  }).join('')}
    </div>
    <div class="chart-legend"><span><i class="legend-dot green"></i>Revenue by month</span></div>`;
}

async function renderPayments(root) {
  if (isStaff()) return renderStaffFinance(root);

  const [fines, payments, subscriptions] = await Promise.all([
    api('/fines'),
    api('/payments'),
    api('/payments/subscriptions/me').catch(() => []),
  ]);
  const unpaid = fines.filter((f) => f.status === 'unpaid');
  const unpaidTotal = unpaid.reduce((sum, f) => sum + Number(f.amount), 0);
  const currentTier = state.user?.membership_tier || 'basic';
  const activeSub = subscriptions.find((s) => s.status === 'active');

  root.innerHTML = `
    <div class="page-head">
      <div>
        <p class="eyebrow">Membership & billing</p>
        <h1>Payments</h1>
        <p class="sub">Settle fines, manage your membership and review your payment history.</p>
      </div>
    </div>

    ${unpaidTotal > 0 ? `<div class="fine-banner">
      <div>
        <h3>You have an outstanding balance</h3>
        <p>${unpaid.length} unpaid fine${unpaid.length > 1 ? 's' : ''} · settle now to keep borrowing without interruption.</p>
      </div>
      <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
        <span class="fine-amount">${money(unpaidTotal)}</span>
        <button class="btn btn-primary" type="button" data-action="pay-all-fines" data-ids="${unpaid.map((f) => f.id).join(',')}">Pay all fines</button>
      </div>
    </div>` : ''}

    <div class="cols">
      <section class="card">
        <div class="card-head"><h2>Fines</h2><span class="hint">${unpaid.length ? `${unpaid.length} open` : 'All settled'}</span></div>
        <div class="card-body">
          ${fines.length ? `<div class="table-wrap"><table class="table">
            <thead><tr><th>Reason</th><th>Amount</th><th>Status</th><th></th></tr></thead>
            <tbody>${fines.slice(0, 8).map((f) => `
              <tr>
                <td>${escapeHTML(f.reason)}<div class="sub">${fmtDate(f.created_at)}</div></td>
                <td class="strong">${money(f.amount)}</td>
                <td>${badge(FINE_BADGE, f.status)}</td>
                <td class="actions">${f.status === 'unpaid' ? `<button class="btn btn-primary btn-sm" type="button" data-action="pay-fine" data-id="${f.id}">Pay</button>` : ''}</td>
              </tr>`).join('')}</tbody>
          </table></div>` : emptyState('✓', 'No fines on file', 'Keep returning books on time and this stays happily empty.')}
        </div>
      </section>

      <section class="card">
        <div class="card-head"><h2>Your membership</h2><span class="hint">${activeSub ? 'Auto-renewing monthly' : 'No active subscription'}</span></div>
        <div class="card-body">
          <div class="kv-list">
            <div class="kv"><span>Current tier</span><strong>${escapeHTML(tierLabel(currentTier))}</strong></div>
            <div class="kv"><span>Library card</span><strong style="font-family:ui-monospace,monospace">${escapeHTML(state.user?.library_card_number || '—')}</strong></div>
            <div class="kv"><span>Renewal</span><strong>${activeSub?.current_period_end ? fmtDate(activeSub.current_period_end) : '—'}</strong></div>
            <div class="kv"><span>Payments made</span><strong>${payments.length}</strong></div>
          </div>
          <p style="font-size:12px;color:var(--muted);margin-top:14px">Membership fees support new books, programs and free community events.</p>
        </div>
      </section>
    </div>

    <div class="section-title"><div><h2>Choose your membership</h2><p>Upgrade or downgrade anytime — changes take effect immediately.</p></div></div>
    <div class="plan-grid">
      ${PLANS.map((plan) => `
        <article class="plan ${currentTier === plan.tier ? 'current' : ''}">
          ${currentTier === plan.tier ? '<span class="plan-badge">Current</span>' : ''}
          <h3>${plan.name}</h3>
          <div class="price">${plan.price ? money(plan.price) : 'Free'}<span>${plan.price ? ' / month' : ' forever'}</span></div>
          <ul>${plan.features.map((f) => `<li>${escapeHTML(f)}</li>`).join('')}</ul>
          <button class="btn ${currentTier === plan.tier ? 'btn-ghost' : 'btn-primary'} btn-block btn-sm" type="button"
            data-action="subscribe" data-tier="${plan.tier}" ${currentTier === plan.tier ? 'disabled' : ''}>
            ${currentTier === plan.tier ? 'Active plan' : plan.price ? 'Subscribe' : 'Switch to Basic'}
          </button>
        </article>`).join('')}
    </div>

    <div class="section-title"><div><h2>Payment history</h2><p>A record of every fine and membership payment.</p></div></div>
    <section class="card"><div class="card-body">
      ${payments.length ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>Date</th><th>Description</th><th>Amount</th><th>Status</th></tr></thead>
        <tbody>${payments.map((p) => `
          <tr>
            <td class="sub">${fmtDate(p.created_at)}</td>
            <td>${escapeHTML(p.description || p.payment_type)}</td>
            <td class="strong">${money(p.amount)}</td>
            <td>${badge(PAYMENT_BADGE, p.status)}</td>
          </tr>`).join('')}</tbody>
      </table></div>` : emptyState('🧾', 'No payments yet', 'Your receipts will appear here after your first payment.')}
    </div></section>`;
}

async function renderStaffFinance(root) {
  const [dashboard, payments, fines] = await Promise.all([
    api('/analytics/dashboard'),
    api('/payments'),
    api('/fines'),
  ]);
  const unpaid = fines.filter((f) => f.status === 'unpaid');
  const totalPaid = payments.filter((p) => p.status === 'succeeded').reduce((s, p) => s + Number(p.amount), 0);

  root.innerHTML = `
    <div class="page-head">
      <div>
        <p class="eyebrow">Finance</p>
        <h1>Revenue & fines</h1>
        <p class="sub">Track membership income, fines and every transaction in one place.</p>
      </div>
    </div>
    <div class="stat-grid">
      ${statCard(ICON.cash, 'Lifetime revenue', totalPaid, { tone: '#0e9f6e', moneyValue: true, i: 0 })}
      ${statCard(ICON.card, 'Revenue this month', dashboard.finance.revenue_this_month, { tone: '#4f46e5', moneyValue: true, i: 1 })}
      ${statCard(ICON.warning, 'Unpaid fines', dashboard.finance.unpaid_fines, { tone: '#d99512', moneyValue: true, i: 2, trend: `${unpaid.length} account${unpaid.length === 1 ? '' : 's'}` })}
      ${statCard(ICON.book, 'Transactions', payments.length, { tone: '#0e7fb8', i: 3 })}
    </div>
    <div class="cols">
      <section class="card">
        <div class="card-head"><h2>Revenue trend</h2><span class="hint">Last 6 months</span></div>
        <div class="card-body">${revenueChartHTML(dashboard.monthly || [])}</div>
      </section>
      <section class="card">
        <div class="card-head"><h2>Unpaid fines</h2><span class="hint">${unpaid.length} open</span></div>
        <div class="card-body">
          ${unpaid.length ? `<div class="rank-list">
            ${unpaid.slice(0, 6).map((f) => `
              <div class="rank-item">
                <span class="rank-num" style="background:var(--gold-soft);color:var(--gold)">${escapeHTML(initialsOf(f.member_name || '?'))}</span>
                <div class="rank-main"><p>${escapeHTML(f.member_name || 'Member')}</p><span>${escapeHTML(f.reason)}</span></div>
                <div style="text-align:right">
                  <div class="rank-value">${money(f.amount)}</div>
                  <button class="link-btn" style="font-size:11px" type="button" data-action="waive-fine" data-id="${f.id}">Waive</button>
                </div>
              </div>`).join('')}
          </div>` : emptyState('✓', 'No unpaid fines', 'Every account is in good standing.')}
        </div>
      </section>
    </div>
    <div class="section-title"><div><h2>All transactions</h2><p>Fine payments, memberships and event tickets.</p></div></div>
    <section class="card"><div class="card-body">
      ${payments.length ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>Member</th><th>Description</th><th>Type</th><th>Amount</th><th>Status</th><th>Date</th></tr></thead>
        <tbody>${payments.map((p) => `
          <tr>
            <td class="strong">${escapeHTML(p.member_name || '—')}</td>
            <td>${escapeHTML(p.description || '—')}</td>
            <td class="sub" style="text-transform:capitalize">${escapeHTML(p.payment_type)}</td>
            <td class="strong">${money(p.amount)}</td>
            <td>${badge(PAYMENT_BADGE, p.status)}</td>
            <td class="sub">${fmtDate(p.created_at)}</td>
          </tr>`).join('')}</tbody>
      </table></div>` : emptyState('🧾', 'No payments recorded', 'Completed payments will show up here.')}
    </div></section>`;
  animateStats(root);
  animateBars(root);
}

/* ------------------------------- spaces ---------------------------- */
const ROOM_GLYPHS = {
  study: ICON.book,
  studio: ICON.spark,
  focus: ICON.clock,
  meeting: ICON.users,
};

const roomTypeLabel = (type) =>
  ({ study: 'Study room', studio: 'Creative studio', focus: 'Focus pod', meeting: 'Meeting room' }[type] || 'Library space');

async function renderSpaces(root) {
  const [rooms, bookings] = await Promise.all([api('/rooms'), api('/rooms/bookings')]);
  const activeBookings = bookings.filter((booking) => booking.status === 'confirmed');

  root.innerHTML = `
    <div class="page-head">
      <div>
        <p class="eyebrow">Our spaces</p>
        <h1>Rooms & resources</h1>
        <p class="sub">Book a quiet room, a studio or a community table. Spaces are free for members.</p>
      </div>
      <div class="head-actions">
        <span class="badge green plain">${ICON.spaces} ${rooms.length} bookable spaces</span>
      </div>
    </div>

    ${rooms.length ? `<div class="space-grid">
      ${rooms.map((room, index) => `
        <article class="space-card" style="--i:${index}">
          <div class="space-visual">
            <span class="space-icon">${ROOM_GLYPHS[room.room_type] || ICON.spaces}</span>
            <div class="space-visual-meta">
              <span>${escapeHTML(room.branch_name || 'Library')}</span>
              <span>${room.capacity} people</span>
            </div>
          </div>
          <div class="space-body">
            <div class="space-title-row">
              <h3>${escapeHTML(room.name)}</h3>
              <span class="badge ${room.upcoming_bookings ? 'blue' : 'green'} plain">${room.upcoming_bookings ? `${room.upcoming_bookings} upcoming` : 'Open'}</span>
            </div>
            <p class="sub space-desc">${escapeHTML(room.description || 'A welcoming space for reading and community.')}</p>
            <div class="amenity-row">
              ${(room.amenities || []).map((amenity) => `<span class="amenity">${escapeHTML(amenity)}</span>`).join('')}
            </div>
            <div class="space-foot">
              <span class="space-rate">${Number(room.hourly_rate) > 0 ? `${money(room.hourly_rate)}<small>/hour</small>` : 'Free with membership'}</span>
              <button class="btn btn-primary btn-sm" type="button" data-action="book-room" data-id="${room.id}">Book a slot</button>
            </div>
          </div>
        </article>`).join('')}
    </div>` : emptyState('🏛️', 'No spaces available', 'A librarian can add bookable rooms from the API.')}

    <section class="card" style="margin-top:20px">
      <div class="card-head">
        <h2>Upcoming bookings</h2>
        <span class="hint">${isStaff() ? 'All members' : 'Your reservations'}</span>
      </div>
      <div class="card-body">
        ${activeBookings.length ? `<div class="booking-list">
          ${activeBookings.map((booking) => `
            <div class="booking-row">
              <div class="booking-date">
                <strong>${fmtShortDate(booking.start_time)}</strong>
                <span>${fmtTime(booking.start_time)} – ${fmtTime(booking.end_time)}</span>
              </div>
              <div class="booking-main">
                <strong>${escapeHTML(booking.room_name || 'Library space')}</strong>
                <span>${isStaff() ? `${escapeHTML(booking.member_name || 'Member')} · ` : ''}${escapeHTML(roomTypeLabel(rooms.find((r) => r.id === booking.room_id)?.room_type))}${booking.notes ? ` · ${escapeHTML(booking.notes)}` : ''}</span>
              </div>
              <span class="badge green">Confirmed</span>
              <button class="btn btn-ghost btn-sm" type="button" data-action="cancel-room-booking" data-id="${booking.id}">Cancel</button>
            </div>`).join('')}
        </div>` : emptyState('🕰️', 'No upcoming bookings', 'Choose a space above and reserve a quiet hour for yourself.')}
      </div>
    </section>`;
}

async function openRoomBookingModal(roomId) {
  try {
    const rooms = await api('/rooms');
    const room = rooms.find((item) => item.id === roomId);
    if (!room) throw new Error('That space is no longer available.');
    const start = new Date();
    start.setDate(start.getDate() + 1);
    start.setHours(10, 0, 0, 0);
    const end = new Date(start);
    end.setHours(end.getHours() + 2);
    openModal(`
      <div class="modal-body">
        <p class="eyebrow">Reserve a space</p>
        <h2 style="font-family:var(--font-display);font-size:26px;font-weight:600;margin-bottom:6px">${escapeHTML(room.name)}</h2>
        <p class="sub" style="color:var(--muted);font-size:13px;margin-bottom:18px">${escapeHTML(room.branch_name || 'Library')} · ${room.capacity} people · ${roomTypeLabel(room.room_type)}</p>
        <form id="room-form" data-room-id="${room.id}">
          <div class="form-grid">
            <label class="field"><span>Starts</span><input name="start_time" type="datetime-local" value="${localInputValue(start)}" required /></label>
            <label class="field"><span>Ends</span><input name="end_time" type="datetime-local" value="${localInputValue(end)}" required /></label>
            <label class="field full"><span>What will you use it for? <em>(optional)</em></span><input name="notes" placeholder="Study group, recording session, tutoring…" maxlength="500" /></label>
          </div>
          <div class="booking-note">${ICON.clock} Up to 4 hours · ${Number(room.hourly_rate) > 0 ? `${money(room.hourly_rate)} per hour` : 'free with membership'} · cancel any time before the slot starts.</div>
          <button class="btn btn-primary btn-block" type="submit" style="margin-top:6px">${ICON.check} Confirm booking</button>
        </form>
      </div>`);
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function cancelRoomBooking(id, element) {
  await withBusy(element, async () => {
    try {
      await api(`/rooms/bookings/${id}/cancel`, { method: 'POST' });
      toast('Booking cancelled — the space is free for someone else.');
      await setView('spaces');
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

/* ------------------------------ audit log -------------------------- */
function auditLabel(action = '') {
  return String(action).replace(/[._]/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

function auditTone(action = '') {
  const prefix = String(action).split('.')[0];
  return {
    auth: 'grey',
    member: 'blue',
    book: 'violet',
    copy: 'violet',
    loan: 'green',
    reservation: 'green',
    fine: 'amber',
    payment: 'amber',
    membership: 'amber',
    event: 'blue',
  }[prefix] || 'grey';
}

function auditDetails(details) {
  if (!details || typeof details !== 'object') return '—';
  const entries = Object.entries(details).filter(([, value]) =>
    value !== null && value !== undefined && value !== '');
  if (!entries.length) return '—';
  const rendered = entries.slice(0, 4).map(([key, value]) => {
    const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
    return `${key.replace(/_/g, ' ')}: ${text}`;
  });
  if (entries.length > 4) rendered.push(`+${entries.length - 4} more`);
  return rendered.join(' · ');
}

async function renderAudit(root) {
  const entries = await api('/audit?limit=150');
  root.innerHTML = `
    <div class="page-head">
      <div>
        <p class="eyebrow">Governance</p>
        <h1>Audit trail</h1>
        <p class="sub">A transparent record of sensitive actions across the library — who did what, and when.</p>
      </div>
      <div class="head-actions">
        <span class="badge green plain">${ICON.shield} ${entries.length} recent events</span>
      </div>
    </div>
    <section class="card">
      <div class="card-head"><h2>Activity ledger</h2><span class="hint">Newest first · last 150 events</span></div>
      <div class="card-body">
        ${entries.length ? `<div class="table-wrap"><table class="table audit-table">
          <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
          <tbody>${entries.map((entry) => `
            <tr>
              <td class="sub" title="${escapeHTML(entry.created_at || '')}">
                <strong style="color:var(--ink);font-weight:600">${escapeHTML(timeAgo(entry.created_at))}</strong><br>
                ${escapeHTML(fmtDateTime(entry.created_at))}
              </td>
              <td>
                <div class="audit-actor">
                  <strong>${escapeHTML(entry.user_name || 'System')}</strong>
                  <span>${escapeHTML(entry.user_email || entry.user_role || 'automated')}</span>
                </div>
              </td>
              <td><span class="badge ${auditTone(entry.action)} plain audit-pill">${escapeHTML(auditLabel(entry.action))}</span></td>
              <td class="sub">${entry.entity_type ? `<span class="audit-target">${escapeHTML(entry.entity_type)}${entry.entity_id ? ` #${escapeHTML(entry.entity_id)}` : ''}</span>` : '—'}</td>
              <td class="audit-details">${escapeHTML(auditDetails(entry.details))}</td>
            </tr>`).join('')}</tbody>
        </table></div>` : emptyState('🛡️', 'No audit events yet', 'Sensitive actions will be recorded here automatically.')}
      </div>
    </section>
    <p class="audit-foot">${ICON.shield} Each entry is committed in the same transaction as the action it describes.</p>`;
}

/* ------------------------------ profile ---------------------------- */
function barcodeHTML(seed) {
  let hash = 2166136261;
  for (const ch of String(seed || 'LIBRA')) {
    hash ^= ch.charCodeAt(0);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  const bars = [];
  let n = hash || 123456789;
  for (let i = 0; i < 44; i += 1) {
    n = (Math.imul(n, 1103515245) + 12345) >>> 0;
    bars.push(`<i style="height:${58 + (n % 42)}%;width:${1 + (n % 3)}px"></i>`);
  }
  return bars.join('');
}

async function renderProfile(root) {
  const u = state.user;
  const role = roleLabel(u.role);
  root.innerHTML = `
    <div class="page-head">
      <div>
        <p class="eyebrow">Account</p>
        <h1>Your profile</h1>
        <p class="sub">Manage your details, library card and account security.</p>
      </div>
    </div>
    <div class="profile-grid">
      <div style="display:flex;flex-direction:column;gap:16px">
        <div class="library-card">
          <div class="lc-top">
            <span class="lc-brand"><span class="brand-mark">L</span> Libra</span>
            <span class="lc-tier">${escapeHTML(tierLabel(u.membership_tier))} member</span>
          </div>
          <div>
            <div class="lc-name">${escapeHTML(u.full_name)}</div>
            <div class="lc-number">${escapeHTML(u.library_card_number || 'PENDING-CARD')}</div>
          </div>
          <div class="lc-bottom">
            <div class="barcode" aria-hidden="true">${barcodeHTML(u.library_card_number || u.email)}</div>
            <div class="lc-since">Member since<br>${fmtDate(u.created_at)}</div>
          </div>
        </div>
        <section class="card">
          <div class="card-head"><h2>Account details</h2><span class="hint">${escapeHTML(role)}</span></div>
          <div class="card-body">
            <div class="kv-list">
              <div class="kv"><span>Email</span><strong>${escapeHTML(u.email)}</strong></div>
              <div class="kv"><span>Phone</span><strong>${escapeHTML(u.phone || 'Not added')}</strong></div>
              <div class="kv"><span>Address</span><strong>${escapeHTML(u.address || 'Not added')}</strong></div>
              <div class="kv"><span>Status</span><strong>${u.is_active ? 'Active' : 'Disabled'}</strong></div>
              <div class="kv"><span>Last sign-in</span><strong>${u.last_login ? fmtDateTime(u.last_login) : '—'}</strong></div>
              <div class="kv"><span>Reading goal</span><strong>${number(u.reading_goal || 12)} books · ${state.shelves.goal.year}</strong></div>
            </div>
          </div>
        </section>
        <section class="card">
          <div class="card-head"><h2>Reading life</h2><span class="hint">${state.shelves.goal.year}</span></div>
          <div class="card-body profile-reading">
            <div class="goal-ring goal-ring-xs" style="--pct:${Math.max(0, Math.min(100, Number(state.shelves.goal.percent) || 0))}">
              <div><strong>${number(state.shelves.goal.finished)}</strong><span>of ${number(state.shelves.goal.target)}</span></div>
            </div>
            <div><strong>${state.shelves.goal.percent >= 100 ? 'Challenge complete' : 'Keep turning pages'}</strong><p>${escapeHTML(goalProgressText(state.shelves.goal))}</p></div>
            <button class="btn btn-soft btn-sm" type="button" data-view="shelves">${ICON.bookmark} My shelves</button>
          </div>
        </section>
        ${!isStaff() ? `<button class="btn btn-ghost btn-block" type="button" data-view="payments">${ICON.card} Manage membership & billing</button>` : ''}
        <button class="btn btn-danger btn-block" type="button" data-action="logout">${ICON.logout} Sign out of Libra</button>
      </div>

      <div style="display:flex;flex-direction:column;gap:16px">
        <section class="card">
          <div class="card-head"><h2>Edit profile</h2><span class="hint">Visible to library staff</span></div>
          <div class="card-body">
            <form id="profile-form">
              <div class="form-grid">
                <label class="field full"><span>Full name</span><input name="full_name" value="${escapeHTML(u.full_name)}" required minlength="2" /></label>
                <label class="field"><span>Phone</span><input name="phone" value="${escapeHTML(u.phone || '')}" placeholder="+91 90000 00000" /></label>
                <label class="field"><span>Date of birth</span><input name="date_of_birth" type="date" value="${escapeHTML(u.date_of_birth || '')}" /></label>
                <label class="field full"><span>Address</span><textarea name="address" rows="2" placeholder="Your address">${escapeHTML(u.address || '')}</textarea></label>
                <label class="field full"><span>Annual reading goal</span><input name="reading_goal" type="number" min="1" max="365" value="${number(u.reading_goal || 12)}" required /><em class="field-hint">Finished books count automatically each calendar year.</em></label>
              </div>
              <button class="btn btn-primary" type="submit">${ICON.check} Save changes</button>
            </form>
          </div>
        </section>

        <section class="card">
          <div class="card-head"><h2>Change password</h2><span class="hint">Keep your account safe</span></div>
          <div class="card-body">
            <form id="password-form">
              <div class="form-grid">
                <label class="field full"><span>Current password</span><input name="current_password" type="password" required autocomplete="current-password" /></label>
                <label class="field full"><span>New password</span><input name="new_password" type="password" required minlength="8" autocomplete="new-password" placeholder="At least 8 characters" /></label>
              </div>
              <button class="btn btn-primary" type="submit">Update password</button>
            </form>
          </div>
        </section>

        <section class="card">
          <div class="card-head"><h2>Membership</h2><span class="hint">${escapeHTML(tierLabel(u.membership_tier))}</span></div>
          <div class="card-body">
            <p style="font-size:13px;color:var(--muted);line-height:1.6">
              You are on the <strong style="color:var(--ink)">${escapeHTML(tierLabel(u.membership_tier))}</strong> plan.
              ${isStaff() ? 'Staff accounts include full administrative access.' : 'Upgrade anytime for longer loans, more renewals and priority reservations.'}
            </p>
            ${!isStaff() ? `<button class="btn btn-soft" type="button" data-view="payments" style="margin-top:14px">Compare plans ${ICON.arrow}</button>` : ''}
          </div>
        </section>
      </div>
    </div>`;
}

/* --------------------------- add book modal ------------------------ */
async function suggestBookMetadata(element) {
  const form = $('#book-form');
  if (!form) return;
  const title = form.querySelector('[name="title"]')?.value.trim() || '';
  if (!title) {
    toast('Add a title first, then ask for a suggestion.', 'info');
    return;
  }
  const authorSelect = form.querySelector('[name="author_id"]');
  const authorName = authorSelect?.value ? authorSelect.selectedOptions[0]?.textContent.trim() : null;
  await withBusy(element, async () => {
    try {
      const suggestion = await api('/books/suggest', {
        method: 'POST',
        body: {
          title,
          author_name: authorName === 'Unknown' ? null : authorName,
          description: form.querySelector('[name="description"]')?.value.trim() || null,
        },
      });
      if (suggestion.category_id) {
        const categorySelect = form.querySelector('[name="category_id"]');
        if (categorySelect) categorySelect.value = String(suggestion.category_id);
      }
      const tagsInput = form.querySelector('[name="tags"]');
      if (tagsInput) tagsInput.value = suggestion.tags.join(', ');
      const desc = form.querySelector('[name="description"]');
      if (desc && !desc.value.trim()) desc.value = suggestion.description;
      const format = form.querySelector('[name="book_format"]');
      if (format) format.value = suggestion.book_format;
      toast(`Smart suggestion: ${suggestion.category || 'General'} · ${suggestion.confidence}% keyword match`);
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

async function openBookCreateModal() {
  openModal('<div class="modal-body"><div class="skeleton" style="height:300px;border-radius:16px"></div></div>');
  try {
    const [categories, authors] = await Promise.all([
      api('/catalog/categories'),
      api('/catalog/authors'),
    ]);
    setModalHTML(`
      <div class="modal-body">
        <p class="eyebrow">Catalog</p>
        <h2 style="font-family:var(--font-display);font-size:26px;font-weight:600;margin-bottom:6px">Add a book</h2>
        <p class="sub" style="color:var(--muted);font-size:13px;margin-bottom:18px">Add a new title to the shelves. Copies can be issued afterwards.</p>
        <form id="book-form">
          <div class="suggest-banner">
            <div>
              <strong>Smart catalog assist</strong>
              <span>Suggest a category, tags and starter description from the title.</span>
            </div>
            <button class="btn btn-soft btn-sm" type="button" data-action="suggest-book">${ICON.spark} Suggest details</button>
          </div>
          <div class="form-grid">
            <label class="field full"><span>Title</span><input name="title" required minlength="1" placeholder="The Left Hand of Darkness" /></label>
            <label class="field"><span>Author</span>
              <select name="author_id"><option value="">Unknown</option>${authors.map((a) => `<option value="${a.id}">${escapeHTML(a.name)}</option>`).join('')}</select>
            </label>
            <label class="field"><span>Category</span>
              <select name="category_id"><option value="">General</option>${categories.map((c) => `<option value="${c.id}">${escapeHTML(c.name)}</option>`).join('')}</select>
            </label>
            <label class="field"><span>ISBN</span><input name="isbn" placeholder="978…" /></label>
            <label class="field"><span>Publication year</span><input name="publication_year" type="number" min="1000" max="2100" placeholder="2026" /></label>
            <label class="field"><span>Copies</span><input name="total_copies" type="number" min="1" value="1" required /></label>
            <label class="field"><span>Format</span>
              <select name="book_format"><option value="hardcover">Hardcover</option><option value="paperback">Paperback</option><option value="ebook">E-book</option><option value="audiobook">Audiobook</option></select>
            </label>
            <label class="field full"><span>Cover image URL</span><input name="cover_image_url" placeholder="https://… (auto-filled from ISBN if left empty)" /></label>
            <label class="field full"><span>Tags</span><input name="tags" placeholder="ai, computing, future (comma separated)" /></label>
            <label class="field full"><span>Description</span><textarea name="description" rows="3" placeholder="What is this book about?"></textarea></label>
          </div>
          <button class="btn btn-primary btn-block" type="submit" style="margin-top:6px">${ICON.plus} Add to catalog</button>
        </form>
      </div>`);
  } catch (error) {
    closeModal();
    toast(error.message, 'error');
  }
}

/* --------------------------- UI actions ---------------------------- */
async function withBusy(element, fn) {
  if (!element || element.dataset.busy === '1') return;
  const original = element.innerHTML;
  element.dataset.busy = '1';
  element.disabled = true;
  try {
    return await fn();
  } finally {
    element.dataset.busy = '0';
    if (element.isConnected) {
      element.disabled = false;
      element.innerHTML = original;
    }
  }
}

async function refreshCurrentView() {
  if (state.view === 'browse') await loadBooksGrid();
  else await setView(state.view);
}

async function borrowBook(id, element) {
  await withBusy(element, async () => {
    try {
      const loan = await api('/loans', { method: 'POST', body: { book_id: id } });
      toast(`Borrowed! “${loan.book_title}” is due back ${fmtDate(loan.due_date)}.`);
      closeModal();
      await refreshCurrentView();
      loadNotifications();
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

async function reserveBook(id, element) {
  await withBusy(element, async () => {
    try {
      const reservation = await api('/reservations', { method: 'POST', body: { book_id: id } });
      toast(`Reserved “${reservation.book_title}”. We’ll notify you when a copy is ready.`);
      closeModal();
      await refreshCurrentView();
      loadNotifications();
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

async function renewLoan(id, element) {
  await withBusy(element, async () => {
    try {
      const loan = await api(`/loans/${id}/renew`, { method: 'POST' });
      toast(`Renewed — your new due date is ${fmtDate(loan.due_date)}.`);
      await setView(state.view);
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

async function returnLoan(id, element) {
  await withBusy(element, async () => {
    try {
      const result = await api(`/loans/${id}/return`, { method: 'POST' });
      toast(result.message || 'Book returned. Thank you!', result.fine_amount > 0 ? 'info' : 'success');
      await setView(state.view);
      loadNotifications();
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

async function cancelReservation(id, element) {
  await withBusy(element, async () => {
    try {
      await api(`/reservations/${id}`, { method: 'DELETE' });
      toast('Reservation cancelled.', 'info');
      await setView(state.view);
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

async function payFines(ids, element) {
  if (!ids.length) return;
  await withBusy(element, async () => {
    try {
      const result = await api('/payments/fines/checkout', {
        method: 'POST',
        body: {
          fine_ids: ids,
          description: ids.length > 1 ? `${ids.length} library fines` : 'Library fine payment',
        },
      });
      if (result.url) {
        window.location.href = result.url;
        return;
      }
      toast(result.message || 'Payment received — thank you!');
      await setView(state.view);
      loadNotifications();
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

async function subscribeTier(tier, element) {
  await withBusy(element, async () => {
    try {
      const result = await api('/payments/subscribe', { method: 'POST', body: { tier } });
      if (result.url) {
        window.location.href = result.url;
        return;
      }
      state.user = await api('/auth/me');
      renderUserChrome();
      toast(result.message || `${tierLabel(tier)} membership is now active.`);
      await setView('payments');
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

async function registerForEvent(id, element) {
  await withBusy(element, async () => {
    try {
      const result = await api(`/events/${id}/register`, { method: 'POST' });
      if (result.checkout_url && /^https?:/i.test(result.checkout_url)) {
        window.location.href = result.checkout_url;
        return;
      }
      toast(result.message || 'You are registered for this event.');
      await setView('events');
      loadNotifications();
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

async function toggleMember(id, element) {
  await withBusy(element, async () => {
    try {
      const member = await api(`/members/${id}/deactivate`, { method: 'PATCH' });
      toast(`${member.full_name} is now ${member.is_active ? 'active' : 'deactivated'}.`, member.is_active ? 'success' : 'info');
      if (state.view === 'members') {
        await loadMembersTable($('#member-search')?.value.trim() || '');
      }
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

async function changeMemberTier(select) {
  const id = Number(select.dataset.tierMember);
  const tier = select.value;
  select.disabled = true;
  try {
    await api(`/members/${id}/membership`, { method: 'PATCH', body: { tier } });
    toast(`Membership updated to ${tierLabel(tier)}.`);
  } catch (error) {
    toast(error.message, 'error');
    await loadMembersTable($('#member-search')?.value.trim() || '');
  } finally {
    select.disabled = false;
  }
}

async function markNotificationRead(id) {
  try {
    await api(`/notifications/${id}/read`, { method: 'POST' });
    await loadNotifications();
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function markAllNotifications() {
  try {
    await api('/notifications/read-all', { method: 'POST' });
    await loadNotifications();
  } catch (error) {
    toast(error.message, 'error');
  }
}

function openWaiveModal(id) {
  openModal(`
    <div class="modal-body">
      <p class="eyebrow">Finance</p>
      <h2 style="font-family:var(--font-display);font-size:26px;font-weight:600;margin-bottom:6px">Waive this fine</h2>
      <p class="sub" style="color:var(--muted);font-size:13px;margin-bottom:18px">The fine will be removed from the member’s balance. This is recorded in the audit trail.</p>
      <form id="waive-form">
        <input type="hidden" name="fine_id" value="${id}" />
        <label class="field"><span>Reason</span><textarea name="reason" rows="3" placeholder="Goodwill, library error, special circumstances…"></textarea></label>
        <button class="btn btn-primary btn-block" type="submit">Waive fine</button>
      </form>
    </div>`);
}

async function handleAction(action, element) {
  switch (action) {
    case 'retry-view':
      await setView(state.view);
      break;
    case 'clear-filters':
      state.books.q = '';
      state.books.category = '';
      state.books.page = 1;
      await setView('browse');
      break;
    case 'browse-page': {
      const page = Number(element.dataset.page);
      if (page >= 1) {
        state.books.page = page;
        await loadBooksGrid();
        $('#view')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
      break;
    }
    case 'open-book':
      await openBookModal(Number(element.dataset.id));
      break;
    case 'quick-shelf':
      await quickShelf(Number(element.dataset.id), element);
      break;
    case 'set-shelf':
      await saveShelf(Number(element.dataset.id), element.dataset.shelf, element);
      break;
    case 'remove-shelf':
      await removeShelf(Number(element.dataset.id), element);
      break;
    case 'edit-goal':
      openGoalModal();
      break;
    case 'open-shelf-tab':
      state.shelfTab = element.dataset.shelf || 'all';
      await setView('shelves');
      break;
    case 'shelf-tab':
      state.shelfTab = element.dataset.shelf || 'all';
      await setView('shelves');
      break;
    case 'borrow':
      await borrowBook(Number(element.dataset.id), element);
      break;
    case 'reserve':
      await reserveBook(Number(element.dataset.id), element);
      break;
    case 'renew-loan':
      await renewLoan(Number(element.dataset.id), element);
      break;
    case 'return-loan':
      await returnLoan(Number(element.dataset.id), element);
      break;
    case 'cancel-reservation':
      await cancelReservation(Number(element.dataset.id), element);
      break;
    case 'pay-fine':
      await payFines([Number(element.dataset.id)], element);
      break;
    case 'pay-all-fines': {
      const ids = String(element.dataset.ids || '')
        .split(',')
        .map((value) => Number(value))
        .filter(Boolean);
      await payFines(ids, element);
      break;
    }
    case 'waive-fine':
      openWaiveModal(Number(element.dataset.id));
      break;
    case 'new-checkout':
      await openCheckoutModal();
      break;
    case 'new-member':
      await openMemberModal();
      break;
    case 'new-book':
      await openBookCreateModal();
      break;
    case 'new-event':
      await openEventModal();
      break;
    case 'suggest-book':
      await suggestBookMetadata(element);
      break;
    case 'book-room':
      await openRoomBookingModal(Number(element.dataset.id));
      break;
    case 'cancel-room-booking':
      await cancelRoomBooking(Number(element.dataset.id), element);
      break;
    case 'register-event':
      await registerForEvent(Number(element.dataset.id), element);
      break;
    case 'subscribe':
      await subscribeTier(element.dataset.tier, element);
      break;
    case 'toggle-member':
      await toggleMember(Number(element.dataset.id), element);
      break;
    case 'read-notif':
      await markNotificationRead(Number(element.dataset.id));
      break;
    case 'mark-all-notifs':
      await markAllNotifications();
      break;
    case 'logout':
      await logout();
      break;
    default:
      break;
  }
}

/* --------------------------- form handling ------------------------- */
async function handleFormSubmit(event) {
  const form = event.target;
  const id = form.id;
  if (!id || ['login-form', 'register-form'].includes(id)) return;
  const known = ['checkout-form', 'member-form', 'event-form', 'book-form', 'room-form', 'review-form', 'profile-form', 'password-form', 'waive-form', 'goal-form'];
  if (!known.includes(id)) return;
  event.preventDefault();
  const submit = form.querySelector('button[type="submit"]');
  if (submit) submit.disabled = true;

  try {
    if (id === 'checkout-form') {
      const memberId = Number(form.querySelector('#checkout-member')?.value || 0);
      const bookId = Number(form.querySelector('#checkout-book')?.value || 0);
      const days = Number(form.querySelector('#checkout-days')?.value || 14);
      if (!memberId || !bookId) throw new Error('Please choose both a member and a book.');
      const loan = await api('/loans', {
        method: 'POST',
        body: { book_id: bookId, member_id: memberId, days },
      });
      toast(`Checked out “${loan.book_title}” to ${loan.member_name}. Due ${fmtDate(loan.due_date)}.`);
      closeModal();
      await setView('loans');
      loadNotifications();
    }

    if (id === 'member-form') {
      const data = new FormData(form);
      const created = await api('/members', {
        method: 'POST',
        body: {
          full_name: String(data.get('full_name') || '').trim(),
          email: String(data.get('email') || '').trim(),
          password: String(data.get('password') || ''),
          phone: String(data.get('phone') || '').trim() || null,
          role: String(data.get('role') || 'member'),
        },
      });
      toast(`Account created for ${created.full_name} — card ${created.library_card_number}.`);
      closeModal();
      if (state.view === 'members') await loadMembersTable($('#member-search')?.value.trim() || '');
    }

    if (id === 'event-form') {
      const data = new FormData(form);
      const start = new Date(String(data.get('start_time') || ''));
      const end = new Date(String(data.get('end_time') || ''));
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
        throw new Error('Please choose valid start and end times.');
      }
      const branch = String(data.get('branch_id') || '');
      await api('/events', {
        method: 'POST',
        body: {
          title: String(data.get('title') || '').trim(),
          description: String(data.get('description') || '').trim() || null,
          branch_id: branch ? Number(branch) : null,
          start_time: start.toISOString(),
          end_time: end.toISOString(),
          capacity: Number(data.get('capacity') || 40),
          ticket_price: Number(data.get('ticket_price') || 0),
          is_published: true,
        },
      });
      toast('Event published to the community calendar.');
      closeModal();
      await setView('events');
    }

    if (id === 'room-form') {
      const data = new FormData(form);
      const start = new Date(String(data.get('start_time') || ''));
      const end = new Date(String(data.get('end_time') || ''));
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
        throw new Error('Please choose valid start and end times.');
      }
      if (end <= start) throw new Error('The end time must be after the start time.');
      await api(`/rooms/${form.dataset.roomId}/bookings`, {
        method: 'POST',
        body: {
          start_time: start.toISOString(),
          end_time: end.toISOString(),
          notes: String(data.get('notes') || '').trim() || null,
        },
      });
      toast('Your space is booked — see you there!');
      closeModal();
      await setView('spaces');
    }

    if (id === 'book-form') {
      const data = new FormData(form);
      const isbn = String(data.get('isbn') || '').trim();
      const authorId = String(data.get('author_id') || '');
      const categoryId = String(data.get('category_id') || '');
      const year = String(data.get('publication_year') || '');
      const cover = String(data.get('cover_image_url') || '').trim();
      const tags = String(data.get('tags') || '').split(',').map((tag) => tag.trim()).filter(Boolean);
      const book = await api('/books', {
        method: 'POST',
        body: {
          title: String(data.get('title') || '').trim(),
          isbn: isbn || null,
          author_id: authorId ? Number(authorId) : null,
          category_id: categoryId ? Number(categoryId) : null,
          publication_year: year ? Number(year) : null,
          total_copies: Number(data.get('total_copies') || 1),
          book_format: String(data.get('book_format') || 'hardcover'),
          cover_image_url: cover || (isbn ? `https://covers.openlibrary.org/b/isbn/${isbn}-L.jpg` : null),
          description: String(data.get('description') || '').trim() || null,
          tags,
        },
      });
      toast(`“${book.title}” added to the catalog.`);
      closeModal();
      if (state.view === 'browse') {
        state.books.page = 1;
        await loadBooksGrid();
      } else {
        await setView('browse');
      }
    }

    if (id === 'review-form') {
      const data = new FormData(form);
      const bookId = Number(form.dataset.bookId);
      const comment = String(data.get('comment') || '').trim();
      await api(`/books/${bookId}/reviews`, {
        method: 'POST',
        body: { rating: Number(data.get('rating') || 5), comment: comment || null },
      });
      toast('Thank you for sharing your review!');
      await openBookModal(bookId);
    }

    if (id === 'profile-form') {
      const data = new FormData(form);
      const dob = String(data.get('date_of_birth') || '');
      state.user = await api('/auth/me', {
        method: 'PUT',
        body: {
          full_name: String(data.get('full_name') || '').trim(),
          phone: String(data.get('phone') || '').trim() || null,
          address: String(data.get('address') || '').trim() || null,
          date_of_birth: dob || null,
          reading_goal: Number(data.get('reading_goal') || 12),
        },
      });
      await loadShelves(true).catch(() => {});
      renderUserChrome();
      toast('Your profile has been updated.');
      await setView('profile');
    }

    if (id === 'password-form') {
      const data = new FormData(form);
      await api('/auth/change-password', {
        method: 'POST',
        body: {
          current_password: String(data.get('current_password') || ''),
          new_password: String(data.get('new_password') || ''),
        },
      });
      form.reset();
      toast('Password updated successfully.');
    }

    if (id === 'waive-form') {
      const data = new FormData(form);
      const fineId = Number(data.get('fine_id'));
      await api(`/fines/${fineId}/waive`, {
        method: 'POST',
        body: { reason: String(data.get('reason') || '').trim() || null },
      });
      toast('Fine waived.');
      closeModal();
      await setView(state.view);
    }

    if (id === 'goal-form') {
      const data = new FormData(form);
      const goal = await api('/shelves/me/goal', {
        method: 'PUT',
        body: { target: Number(data.get('target') || 12) },
      });
      state.shelves.goal = goal;
      if (state.user) state.user.reading_goal = goal.target;
      toast(`Your ${goal.year} reading goal is now ${goal.target} books.`);
      closeModal();
      await setView(state.view);
    }
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    if (submit && submit.isConnected) submit.disabled = false;
  }
}

/* --------------------------- event wiring -------------------------- */
function bindDelegates() {
  document.addEventListener('click', async (event) => {
    const viewTarget = event.target.closest('[data-view]');
    if (viewTarget) {
      event.preventDefault();
      await setView(viewTarget.dataset.view);
      return;
    }
    const actionTarget = event.target.closest('[data-action]');
    if (actionTarget) {
      event.preventDefault();
      await handleAction(actionTarget.dataset.action, actionTarget);
    }
  });

  document.addEventListener('change', async (event) => {
    const tierSelect = event.target.closest('[data-tier-member]');
    if (tierSelect) await changeMemberTier(tierSelect);
    const progress = event.target.closest('[data-shelf-progress]');
    if (progress) await updateShelfProgress(Number(progress.dataset.shelfProgress), progress.value);
  });

  document.addEventListener('submit', handleFormSubmit);
}

const RENDERERS = {
  dashboard: renderDashboard,
  browse: renderBrowse,
  shelves: renderShelves,
  loans: renderLoans,
  members: renderMembers,
  events: renderEvents,
  spaces: renderSpaces,
  payments: renderPayments,
  audit: renderAudit,
  profile: renderProfile,
};

/* ------------------------------- boot ------------------------------ */
async function boot() {
  const preferred = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  applyTheme(localStorage.getItem(THEME_KEY) || preferred, false);
  bindChrome();
  bindDelegates();

  try {
    if (getAccess()) {
      state.user = await api('/auth/me');
      await enterApp();
    } else {
      setTimeout(showAuth, 400);
    }
  } catch {
    clearSession();
    setTimeout(showAuth, 400);
  } finally {
    const splash = $('#splash');
    if (splash) {
      setTimeout(() => splash.classList.add('done'), 380);
      setTimeout(() => splash.remove(), 1200);
    }
    if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
      navigator.serviceWorker.register('/service-worker.js').catch(() => { /* offline shell is optional */ });
    }
  }
}

document.addEventListener('DOMContentLoaded', boot);

