/* ==========================================================================
   Pearl Continental Lahore — Chat concierge widget
   State lives in ONE place (state.messages + state.pending). The DOM is
   always re-rendered from that state, so collapsing/expanding or navigating
   between pages can never leave the loader out of sync with the history.
   Requires: app.js (global App) and backend GET /chat/history (see BACKEND_CHANGES.md)
   ========================================================================== */
(function () {
  'use strict';
  const { api, esc, Auth, $ } = App;
  const PENDING_KEY = 'pcl_chat_pending';
  const PENDING_MAX_MS = 90000;

  const state = { open: false, large: false, loaded: false, pending: false, messages: [], threadId: null, poll: null };

  const SUGGESTIONS = ['Check room availability', 'What is the cancellation policy?', 'Show my bookings', 'What time is check-in?'];

  /* ---------- Build the DOM once ---------- */
  const root = document.createElement('div');
  root.innerHTML = `
    <button class="chat-fab" id="chat-fab" aria-label="Open chat concierge"><span class="dot"></span> Concierge</button>
    <section class="chat-panel" id="chat-panel" role="dialog" aria-label="PC Lahore concierge chat">
      <div class="chat-head">
        <div class="ttl"><span class="avatar">PC</span><div><strong>PC Concierge</strong><small>Ask about rooms, bookings &amp; policies</small></div></div>
        <div class="chat-tools">
          <button id="chat-new" title="Start a new chat" aria-label="Start a new chat">＋</button>
          <button id="chat-expand" class="expand" title="Enlarge" aria-label="Enlarge chat">⤢</button>
          <button id="chat-close" title="Minimise" aria-label="Minimise chat">—</button>
        </div>
      </div>
      <div class="chat-body" id="chat-body" aria-live="polite"></div>
      <div class="chat-suggest" id="chat-suggest"></div>
      <form class="chat-form" id="chat-form">
        <textarea id="chat-input" rows="1" placeholder="Type your message…" aria-label="Message"></textarea>
        <button type="submit" id="chat-send">Send</button>
      </form>
    </section>`;
  document.body.appendChild(root);

  const fab = $('#chat-fab'), panel = $('#chat-panel'), body = $('#chat-body'), input = $('#chat-input'), send = $('#chat-send'), sugg = $('#chat-suggest');

  /* ---------- Text formatting (safe: escape first, then add light markdown) ---------- */
  function format(text) {
    let t = esc(text);
    t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    const lines = t.split('\n');
    let out = '', inList = false;
    for (const line of lines) {
      const m = line.match(/^\s*[-*•]\s+(.*)/);
      if (m) { if (!inList) { out += '<ul>'; inList = true; } out += `<li>${m[1]}</li>`; }
      else { if (inList) { out += '</ul>'; inList = false; } out += line.trim() === '' ? '<br>' : `<div>${line}</div>`; }
    }
    if (inList) out += '</ul>';
    return out;
  }
  const timeLabel = (iso) => { try { return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }); } catch { return ''; } };

  /* ---------- Render from state ---------- */
  function render() {
    if (!Auth.loggedIn) {
      body.innerHTML = `<div class="chat-guest"><div style="font-size:2rem">🛎️</div><strong>Sign in to chat with our concierge</strong>
        <p class="muted small">Your conversations are private and saved to your account.</p>
        <a class="btn btn-primary btn-sm" href="login.html?next=${encodeURIComponent((location.pathname.split('/').pop() || 'index.html') + location.search)}">Sign in</a></div>`;
      $('#chat-form').classList.add('hidden'); sugg.classList.add('hidden');
      return;
    }
    $('#chat-form').classList.remove('hidden');

    let html = '';
    if (!state.messages.length && !state.pending) {
      html += `<div class="msg bot">Welcome to Pearl Continental Lahore. I can check room availability, help with bookings, and answer questions about our policies. How may I help you today?</div>`;
    }
    for (const m of state.messages) {
      const cls = m.sender === 'user' ? 'user' : 'bot';
      html += `<div class="msg ${cls}">${format(m.message)}${m.created_at ? `<time>${timeLabel(m.created_at)}</time>` : ''}</div>`;
    }
    if (state.pending) html += `<div class="typing" aria-label="Concierge is typing"><span></span><span></span><span></span></div>`;
    body.innerHTML = html;
    body.scrollTop = body.scrollHeight;

    sugg.classList.toggle('hidden', state.messages.length > 0 || state.pending);
    sugg.innerHTML = SUGGESTIONS.map((s) => `<button type="button">${esc(s)}</button>`).join('');
    sugg.querySelectorAll('button').forEach((b) => (b.onclick = () => submit(b.textContent)));
    send.disabled = state.pending;
  }

  /* ---------- Pending flag (survives collapse AND page navigation) ---------- */
  function setPending(on) {
    state.pending = on;
    if (on) sessionStorage.setItem(PENDING_KEY, String(Date.now()));
    else sessionStorage.removeItem(PENDING_KEY);
    render();
  }
  function pendingFlagFresh() {
    const t = Number(sessionStorage.getItem(PENDING_KEY));
    return t && Date.now() - t < PENDING_MAX_MS;
  }

  /* ---------- History ---------- */
  let loadingHistory = false;
  async function loadHistory() {
    if (!Auth.loggedIn || loadingHistory) { if (!Auth.loggedIn) render(); return; }
    loadingHistory = true;
    try {
      const data = await api('/chat/history', { redirectOn401: false });
      state.threadId = data.thread_id;
      state.messages = data.messages || [];
      state.loaded = true;
    } catch { state.loaded = true; }
    loadingHistory = false;

    // If a reply was in flight when the page changed, resume the loader and poll for it
    const last = state.messages[state.messages.length - 1];
    if (pendingFlagFresh() && last && last.sender === 'user') { state.pending = true; startPolling(); }
    else if (state.pending === false) sessionStorage.removeItem(PENDING_KEY);
    render();
  }

  function startPolling() {
    if (state.poll) return;
    state.poll = setInterval(async () => {
      if (!pendingFlagFresh()) { stopPolling(); setPending(false); return; }
      try {
        const data = await api('/chat/history', { redirectOn401: false });
        const last = (data.messages || [])[data.messages.length - 1];
        if (last && last.sender === 'assistant') { state.messages = data.messages; stopPolling(); setPending(false); }
      } catch { /* try again on next tick */ }
    }, 2500);
  }
  function stopPolling() { clearInterval(state.poll); state.poll = null; }

  /* ---------- Sending ---------- */
  async function submit(text) {
    text = (text || '').trim();
    if (!text || state.pending || !Auth.loggedIn) return;
    state.messages.push({ sender: 'user', message: text, created_at: new Date().toISOString() });
    input.value = ''; autoGrow();
    setPending(true);
    try {
      const data = await api('/chat', { method: 'POST', body: { message: text, thread_id: state.threadId } });
      state.threadId = data.thread_id;
      state.messages.push({ sender: 'assistant', message: data.response, created_at: new Date().toISOString() });
    } catch (e) {
      state.messages.push({ sender: 'assistant', message: 'Sorry, I could not complete that request just now. Please try again in a moment.', created_at: new Date().toISOString() });
    }
    stopPolling();
    setPending(false);
  }

  async function newChat() {
    if (!Auth.loggedIn || state.pending) return;
    try { await api('/chat/new', { method: 'POST' }); } catch { /* ignore, still clear UI */ }
    state.messages = []; state.threadId = null;
    render();
  }

  /* ---------- Open / close / enlarge ---------- */
  function setOpen(v) {
    state.open = v;
    panel.classList.toggle('open', v);
    fab.classList.toggle('hidden', v);
    sessionStorage.setItem('pcl_chat_open', v ? '1' : '0');
    if (v) { render(); setTimeout(() => input.focus(), 50); if (!state.loaded) loadHistory(); }
  }
  function setLarge(v) {
    state.large = v;
    panel.classList.toggle('large', v);
    $('#chat-expand').textContent = v ? '⤡' : '⤢';
    $('#chat-expand').title = v ? 'Reduce' : 'Enlarge';
    localStorage.setItem('pcl_chat_large', v ? '1' : '0');
    body.scrollTop = body.scrollHeight;
  }

  function autoGrow() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 110) + 'px'; }

  fab.onclick = () => setOpen(true);
  $('#chat-close').onclick = () => setOpen(false);
  $('#chat-expand').onclick = () => setLarge(!state.large);
  $('#chat-new').onclick = newChat;
  $('#chat-form').onsubmit = (e) => { e.preventDefault(); submit(input.value); };
  input.addEventListener('input', autoGrow);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(input.value); } });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && state.open && !document.querySelector('.modal-backdrop')) setOpen(false); });

  /* ---------- Boot ---------- */
  setLarge(localStorage.getItem('pcl_chat_large') === '1');
  App.ready.then(() => {
    if (Auth.loggedIn) loadHistory();
    if (sessionStorage.getItem('pcl_chat_open') === '1') setOpen(true);
  });
  render();
})();
