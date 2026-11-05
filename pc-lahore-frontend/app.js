/* ==========================================================================
   Pearl Continental Lahore — shared frontend logic
   Loaded on every page BEFORE the page's own script.
   Exposes one global: App
   ========================================================================== */
(function () {
  'use strict';

  const KEYS = { token: 'pcl_token', user: 'pcl_user' };

  /* ---------- Auth store (localStorage) ---------- */
  const Auth = {
    get token() { return localStorage.getItem(KEYS.token); },
    get user() { try { return JSON.parse(localStorage.getItem(KEYS.user)); } catch { return null; } },
    get loggedIn() { return !!this.token; },
    set(token, user) { localStorage.setItem(KEYS.token, token); localStorage.setItem(KEYS.user, JSON.stringify(user)); },
    setUser(user) { localStorage.setItem(KEYS.user, JSON.stringify(user)); },
    clear() {
      localStorage.removeItem(KEYS.token);
      localStorage.removeItem(KEYS.user);
      sessionStorage.removeItem('pcl_chat_pending');
      sessionStorage.removeItem('pcl_draft');
    }
  };

  /* ---------- Helpers ---------- */
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const money = (n) => 'PKR ' + Number(n || 0).toLocaleString('en-PK', { maximumFractionDigits: 0 });
  const parseDate = (iso) => new Date(iso + 'T00:00:00');
  const toISO = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const todayISO = () => toISO(new Date());
  const addDays = (iso, n) => { const d = parseDate(iso); d.setDate(d.getDate() + n); return toISO(d); };
  const diffDays = (a, b) => Math.round((parseDate(b) - parseDate(a)) / 86400000);
  const fmtDate = (iso) => iso ? parseDate(String(iso).slice(0, 10)).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) : '—';
  const initials = (name) => (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('');
  const qs = (k) => new URLSearchParams(location.search).get(k);
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const uid = (p) => p + '-' + (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '') : Date.now().toString(36) + Math.random().toString(36).slice(2));

  /* ---------- API client ---------- */
  class ApiError extends Error { constructor(msg, status) { super(msg); this.status = status; } }

  function parseDetail(data) {
    if (!data || !data.detail) return null;
    if (typeof data.detail === 'string') return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => {
        const field = (d.loc || []).filter((x) => x !== 'body' && x !== 'query').join(' › ');
        const msg = String(d.msg || '').replace(/^Value error, /, '');
        return field ? `${field}: ${msg}` : msg;
      }).join(' · ');
    }
    return null;
  }

  function goLogin() {
    const page = location.pathname.split('/').pop() || 'index.html';
    location.href = 'login.html?next=' + encodeURIComponent(page + location.search);
  }

  async function api(path, opts = {}) {
    const { method = 'GET', body, headers = {}, auth = true, redirectOn401 = true } = opts;
    const h = { ...headers };
    if (body !== undefined) h['Content-Type'] = 'application/json';
    if (auth && Auth.token) h['X-Session-Token'] = Auth.token;
    let res;
    try {
      res = await fetch(path, { method, headers: h, body: body !== undefined ? JSON.stringify(body) : undefined });
    } catch {
      throw new ApiError('We could not reach the server. Please check your connection and try again.', 0);
    }
    let data = null;
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) {
      if (res.status === 401 && auth && redirectOn401) { Auth.clear(); goLogin(); }
      throw new ApiError(parseDetail(data) || 'Something went wrong. Please try again.', res.status);
    }
    return data;
  }

  /* ---------- Toasts / modal ---------- */
  function toast(message, type = 'info') {
    let box = $('.toasts');
    if (!box) { box = document.createElement('div'); box.className = 'toasts'; box.setAttribute('role', 'status'); box.setAttribute('aria-live', 'polite'); document.body.appendChild(box); }
    const t = document.createElement('div');
    t.className = 'toast ' + type;
    t.textContent = message;
    box.appendChild(t);
    setTimeout(() => t.remove(), 4500);
  }

  function dialog({ title, message, confirmText = 'Confirm', cancelText = 'Cancel', danger = false, input = null }) {
    return new Promise((resolve) => {
      const wrap = document.createElement('div');
      wrap.className = 'modal-backdrop';
      wrap.innerHTML = `
        <div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}">
          <h3>${esc(title)}</h3>
          <div class="muted">${message}</div>
          ${input ? `<div class="field" style="margin-top:1rem"><label>${esc(input.label)}</label><input class="input" id="dlg-input" placeholder="${esc(input.placeholder || '')}" autocomplete="off"><span class="hint">${esc(input.hint || '')}</span></div>` : ''}
          <div class="actions">
            <button class="btn btn-outline" data-act="cancel">${esc(cancelText)}</button>
            <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-act="ok">${esc(confirmText)}</button>
          </div>
        </div>`;
      document.body.appendChild(wrap);
      const done = (val) => { wrap.remove(); document.removeEventListener('keydown', onKey); resolve(val); };
      const onKey = (e) => { if (e.key === 'Escape') done(null); };
      document.addEventListener('keydown', onKey);
      wrap.addEventListener('click', (e) => { if (e.target === wrap) done(null); });
      $('[data-act=cancel]', wrap).onclick = () => done(null);
      $('[data-act=ok]', wrap).onclick = () => done(input ? ($('#dlg-input', wrap).value.trim() || null) : true);
      (input ? $('#dlg-input', wrap) : $('[data-act=ok]', wrap)).focus();
    });
  }

  /* Button loading state helper */
  async function withLoading(btn, fn) {
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>';
    try { return await fn(); }
    finally { btn.disabled = false; btn.innerHTML = original; }
  }

  /* ---------- Pricing estimate (mirrors util/pricing_util.py) ---------- */
  function estimate(draft, roomTypes, services) {
    const nights = draft.check_in && draft.check_out ? Math.max(0, diffDays(draft.check_in, draft.check_out)) : 0;
    const rooms = [];
    let roomsCost = 0;
    for (const [id, qty] of Object.entries(draft.rooms || {})) {
      if (!qty) continue;
      const rt = roomTypes.find((r) => String(r.room_type_id) === String(id));
      if (!rt) continue;
      const sub = rt.base_price * nights * qty;
      roomsCost += sub;
      rooms.push({ name: rt.name, qty, sub, perNight: rt.base_price });
    }
    const extras = [];
    let svcCost = 0;
    for (const [id, qty] of Object.entries(draft.services || {})) {
      if (!qty) continue;
      const s = services.find((x) => String(x.id) === String(id));
      if (!s) continue;
      let sub = s.price * qty;
      if (s.pricing_unit === 'per_night') sub = s.price * nights * qty;
      else if (s.pricing_unit === 'per_guest') sub = s.price * draft.guests * qty;
      svcCost += sub;
      extras.push({ name: s.name, qty, sub });
    }
    return { nights, rooms, extras, roomsCost, svcCost, total: roomsCost + svcCost };
  }

  const unitLabel = (u) => ({ per_booking: 'per booking', per_night: 'per night', per_guest: 'per guest' }[u] || (u || '').replace('_', ' '));

  /* ---------- Payment helper shared by wizard + detail page ---------- */
  function pay(ref, idempotencyKey) {
    return api(`/bookings/${encodeURIComponent(ref)}/pay`, { method: 'POST', headers: { 'X-Idempotency-Key': idempotencyKey || uid('tx') } });
  }

  /* ---------- Layout (header + footer injected on every page) ---------- */
  const NAV = [
    { key: 'home', label: 'Home', href: 'index.html' },
    { key: 'rooms', label: 'Rooms & Suites', href: 'rooms.html' },
    { key: 'book', label: 'Book a Stay', href: 'book.html' },
    { key: 'bookings', label: 'My Bookings', href: 'bookings.html' }
  ];

  function headerHTML() {
    const page = document.body.dataset.page;
    const u = Auth.user;
    const links = NAV.map((n) => `<li><a href="${n.href}" class="${page === n.key ? 'active' : ''}" ${page === n.key ? 'aria-current="page"' : ''}>${n.label}</a></li>`).join('');
    const actions = Auth.loggedIn
      ? `<div class="user-menu">
           <button class="user-btn" id="user-btn" aria-haspopup="true" aria-expanded="false">
             <span class="avatar">${esc(initials(u && u.full_name))}</span><span>${esc((u && u.full_name || 'Account').split(' ')[0])}</span> ▾
           </button>
           <div class="dropdown" id="user-dd">
             <div class="who"><strong>${esc(u && u.full_name || '')}</strong><small>${esc(u && u.email || '')}</small></div>
             <a href="account.html">My Account</a>
             <a href="bookings.html">My Bookings</a>
             <button id="logout-btn">Sign out</button>
           </div>
         </div>`
      : `<a class="btn btn-outline btn-sm" href="login.html">Sign in</a><a class="btn btn-primary btn-sm" href="register.html">Create account</a>`;
    return `<header class="site-header"><div class="container nav">
        <a class="brand" href="index.html" aria-label="Pearl Continental Lahore home">
          <span class="brand-mark">PC</span>
          <span class="brand-text"><strong>Pearl Continental</strong><span>Lahore</span></span>
        </a>
        <ul class="nav-links" id="nav-links">${links}</ul>
        <div class="nav-actions">${actions}<button class="menu-toggle" id="menu-toggle" aria-label="Open menu">☰</button></div>
      </div></header>`;
  }

  function footerHTML() {
    return `<footer class="site-footer"><div class="container">
      <div class="footer-grid">
        <div><div class="brand" style="margin-bottom:.8rem"><span class="brand-mark">PC</span><span class="brand-text"><strong style="color:#fff">Pearl Continental</strong><span>Lahore</span></span></div>
          <p>Shahrah-e-Quaid-e-Azam, Lahore, Pakistan.<br>A landmark of Pakistani hospitality since 1960s.</p></div>
        <div><h4>Explore</h4><a href="index.html">Home</a><a href="rooms.html">Rooms &amp; Suites</a><a href="book.html">Book a Stay</a></div>
        <div><h4>Guest</h4><a href="account.html">My Account</a><a href="bookings.html">My Bookings</a><a href="login.html">Sign in</a></div>
        <div><h4>Stay information</h4><p>Check-in from 14:00<br>Check-out until 12:00<br>Free cancellation 7+ days before arrival</p></div>
      </div>
      <div class="footer-bottom"><span>© ${new Date().getFullYear()} Pearl Continental Hotel Lahore. All rights reserved.</span><span>Prices in Pakistani Rupees (PKR)</span></div>
    </div></footer>`;
  }

  function mountLayout() {
    document.body.insertAdjacentHTML('afterbegin', headerHTML());
    document.body.insertAdjacentHTML('beforeend', footerHTML());
    wireHeader();
  }

  function wireHeader() {
    const toggle = $('#menu-toggle');
    if (toggle) toggle.onclick = () => $('#nav-links').classList.toggle('open');
    const btn = $('#user-btn');
    if (btn) {
      btn.onclick = (e) => { e.stopPropagation(); const open = $('#user-dd').classList.toggle('open'); btn.setAttribute('aria-expanded', open); };
      document.addEventListener('click', () => $('#user-dd') && $('#user-dd').classList.remove('open'));
    }
    const lo = $('#logout-btn');
    if (lo) lo.onclick = logout;
  }

  async function logout() {
    try { await api('/auth/logout', { method: 'POST', redirectOn401: false }); } catch { /* token may already be invalid */ }
    Auth.clear();
    location.href = 'index.html';
  }

  function refreshHeader() {
    const old = $('.site-header');
    if (old) old.remove();
    document.body.insertAdjacentHTML('afterbegin', headerHTML());
    wireHeader();
  }

  /* ---------- Page title: "Page | Pearl Continental Lahore" ---------- */
  function setTitle(t) { document.title = t ? `${t} | Pearl Continental Lahore` : 'Pearl Continental Lahore'; }

  /* ---------- Session restore ---------- */
  async function restoreSession() {
    if (!Auth.token) return;
    try {
      const data = await api('/sessions/verify', { redirectOn401: false });
      const before = JSON.stringify(Auth.user);
      Auth.setUser(data.user);
      if (before !== JSON.stringify(data.user)) refreshHeader();
    } catch (e) {
      if (e.status === 401) { Auth.clear(); refreshHeader(); }
    }
  }

  /* Redirect guests to login; call at top of protected pages */
  async function requireAuth() {
    if (!Auth.token) { goLogin(); return false; }
    await App.ready;
    if (!Auth.token) return false;
    return true;
  }

  const App = { Auth, api, ApiError, esc, money, fmtDate, parseDate, toISO, todayISO, addDays, diffDays, initials, qs, $, $$, uid,
    toast, dialog, withLoading, estimate, unitLabel, pay, setTitle, requireAuth, goLogin, logout, refreshHeader };

  window.App = App;
  mountLayout();
  App.ready = restoreSession();
})();
