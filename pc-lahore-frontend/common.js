// common.js — shared utilities, apiFetch wrapper, header, and expandable chatbot widget
const API = "";
const TOKEN_KEY = "pc_token", USER_KEY = "pc_user";
const THREAD_KEY = "pc_chat_thread_id";

const getToken = () => localStorage.getItem(TOKEN_KEY);
const getUser = () => { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } };
function setSession(t, u) { localStorage.setItem(TOKEN_KEY, t); localStorage.setItem(USER_KEY, JSON.stringify(u)); }
function clearSession() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); localStorage.removeItem(THREAD_KEY); }

const $ = id => document.getElementById(id), $$ = s => Array.from(document.querySelectorAll(s));
function safeNext(n) { return n && /^[a-z0-9_-]+\.html(\?[^#]*)?$/i.test(n) ? n : "home.html"; }
function goLogin() { location.href = "login.html?next=" + encodeURIComponent(location.pathname.split("/").pop() + location.search); }

async function apiFetch(url, opts = {}) {
    opts.headers = Object.assign({}, opts.headers);
    const t = getToken();
    if (t) {
        opts.headers["X-Session-Token"] = t;
    }
    if (opts.body && !(opts.body instanceof FormData) && !opts.headers["Content-Type"]) {
        opts.headers["Content-Type"] = "application/json";
    }
    const res = await fetch(API + url, opts);
    if (res.status === 401 && t && !url.startsWith("/auth/login")) {
        clearSession();
        toast("Session expired. Please sign in again.", "error");
        setTimeout(goLogin, 900);
    }
    return res;
}

const json = async r => { try { return await r.json(); } catch { return {}; } };

function errText(d, fb = "Something went wrong.") {
    const x = d && (d.detail || d.message);
    if (typeof x === "string") return x;
    if (Array.isArray(x)) {
        return x.map(e => {
            let msg = e.msg || "";
            if (msg.includes("String should match pattern")) {
                return "Please enter an 11-digit phone number.";
            }
            return msg.replace(/^Value error, /, "");
        }).join(". ") || fb;
    }
    return fb;
}

const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtPKR = (n, d = 0) => "PKR " + (Number(n) || 0).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const localISO = d => new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
const addDays = (iso, n) => { const d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const nightsBetween = (a, b) => a && b && b > a ? Math.round((Date.parse(b) - Date.parse(a)) / 864e5) : 0;
const fmtDate = iso => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

function toast(msg, type = "info", ms = 4500) {
    let h = $("toasts");
    if (!h) { h = document.createElement("div"); h.id = "toasts"; h.setAttribute("aria-live", "polite"); document.body.appendChild(h); }
    const el = document.createElement("div"); el.className = "toast " + type; el.textContent = msg;
    h.appendChild(el); setTimeout(() => el.remove(), ms);
}

function confirmDialog(msg, ok = "Confirm", danger = false) {
    return new Promise(resolve => {
        const w = document.createElement("div"); w.className = "modal";
        w.innerHTML = `<div class="modal-card"><p>${esc(msg)}</p><div class="row" style="justify-content:flex-end;margin-top:1.25rem"><button class="btn" data-no>Cancel</button><button class="btn ${danger ? "danger" : "primary"}" data-yes>${esc(ok)}</button></div></div>`;
        document.body.appendChild(w);
        w.querySelector("[data-no]").onclick = () => { w.remove(); resolve(false); };
        w.querySelector("[data-yes]").onclick = () => { w.remove(); resolve(true); };
        w.onclick = e => { if (e.target === w) { w.remove(); resolve(false); } };
    });
}

function renderHeader(active = "") {
    const u = getUser();
    const initial = u && (u.full_name || u.email) ? (u.full_name || u.email).charAt(0).toUpperCase() : "U";

    document.body.insertAdjacentHTML("afterbegin", `
    <a class="skip" href="#main">Skip to main content</a>
    <header class="nav">
      <div class="wrap">
        <a class="logo" href="home.html"><b>PC</b> Pearl Continental</a>
        <button class="nav-toggle" aria-expanded="false" aria-controls="nav-panel" aria-label="Toggle navigation">☰</button>
        <nav class="nav-panel" id="nav-panel" aria-label="Main">
          <ul>
            <li><a href="home.html" class="${active === "home" ? "active" : ""}">Home</a></li>
            <li><a href="book.html" class="${active === "book" ? "active" : ""}">Book a Stay</a></li>
            <li><a href="bookings.html" class="${active === "bookings" ? "active" : ""}">My Bookings & Payments</a></li>
          </ul>
          <div class="row" style="align-items:center; gap:1rem;">
            ${u ? `
              <div class="profile-menu-container">
                <button class="profile-avatar-btn" id="avatar-btn" aria-label="Google Account Profile">${esc(initial)}</button>
                <div class="profile-dropdown" id="profile-dropdown">
                  <div class="profile-dropdown-header">
                    <strong>${esc(u.full_name || "Valued Guest")}</strong>
                    <small>${esc(u.email || "")}</small>
                  </div>
                 <a href="profile-edit.html">⚙️ Update Account Details</a>
                 <a href="change-password.html">🔒 Change Password</a>
                  <div style="height:1px; background:var(--line); margin:.25rem 0;"></div>
                  <a href="login.html?logout=true" class="danger-option">🚪 Log out</a>
                </div>
              </div>` : `
              <a class="btn sm" href="login.html">Log in</a>
              <a class="btn sm primary" href="register.html">Register</a>`}
          </div>
        </nav>
      </div>
    </header>`);

    const t = document.querySelector(".nav-toggle"), p = document.getElementById("nav-panel");
    if (t && p) {
        t.onclick = () => { const o = p.classList.toggle("open"); t.setAttribute("aria-expanded", o); };
    }

    const avatarBtn = $("avatar-btn"), dropdown = $("profile-dropdown");
    if (avatarBtn && dropdown) {
        avatarBtn.onclick = e => {
            e.stopPropagation();
            dropdown.classList.toggle("open");
        };
        document.addEventListener("click", e => {
            if (!dropdown.contains(e.target) && e.target !== avatarBtn) {
                dropdown.classList.remove("open");
            }
        });
    }
}

// // Get stored stay parameters or fallback to defaults (Today & Tomorrow)
// function getStayPrefs() {
//     const q = new URLSearchParams(location.search);
//     const today = localISO(new Date());

//     // Priority: 1. URL Query Params -> 2. LocalStorage -> 3. Defaults
//     const ci = q.get("check_in") || localStorage.getItem("pc_check_in") || today;
//     const co = q.get("check_out") || localStorage.getItem("pc_check_out") || addDays(ci, 1);
//     const guests = q.get("guests") || localStorage.getItem("pc_guests") || "2";

//     // Save back to localStorage for persistence
//     localStorage.setItem("pc_check_in", ci);
//     localStorage.setItem("pc_check_out", co);
//     localStorage.setItem("pc_guests", guests);

//     return { ci, co, guests };
// }

// // Update stored preferences when user changes them
// function saveStayPrefs(ci, co, guests) {
//     if (ci) localStorage.setItem("pc_check_in", ci);
//     if (co) localStorage.setItem("pc_check_out", co);
//     if (guests) localStorage.setItem("pc_guests", guests);
// }

// Universal Stay State Management (Supporting Adults & Children)
function getStayPrefs() {
    const q = new URLSearchParams(location.search);
    const today = localISO(new Date());

    // Priority: 1. URL Query Params -> 2. LocalStorage -> 3. Defaults
    const ci = q.get("check_in") || localStorage.getItem("pc_check_in") || today;
    const co = q.get("check_out") || localStorage.getItem("pc_check_out") || addDays(ci, 1);
    const guests = q.get("guests") || localStorage.getItem("pc_guests") || "2";
    const children = q.get("children") || localStorage.getItem("pc_children") || "0";

    // Save back to localStorage for cross-page persistence
    localStorage.setItem("pc_check_in", ci);
    localStorage.setItem("pc_check_out", co);
    localStorage.setItem("pc_guests", guests);
    localStorage.setItem("pc_children", children);

    return { ci, co, guests, children };
}

// Universal bidirectional sync when user updates preferences anywhere
function saveStayPrefs(ci, co, guests, children) {
    if (ci) localStorage.setItem("pc_check_in", ci);
    if (co) localStorage.setItem("pc_check_out", co);
    if (guests !== undefined) localStorage.setItem("pc_guests", guests);
    if (children !== undefined) localStorage.setItem("pc_children", children);

    // Immediately push updates to URL query parameters without reloading the page
    const newParams = new URLSearchParams(location.search);
    if (ci) newParams.set("check_in", ci);
    if (co) newParams.set("check_out", co);
    if (guests !== undefined) newParams.set("guests", guests);
    if (children !== undefined) newParams.set("children", children);

    history.replaceState(null, "", `${location.pathname}?${newParams.toString()}`);
}

/* ─── Markdown-like formatting for bot messages ─── */
// function formatBotMessage(raw) {
//     if (!raw || typeof raw !== "string") return "I can help with rooms, rates, and bookings.";

//     let text = raw;
//     text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
//     text = text.replace(/__(.+?)__/g, '<strong>$1</strong>');
//     text = text.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
//     text = text.replace(/^### (.+)$/gm, '<strong style="font-size:1.05em;display:block;margin-top:.5em">$1</strong>');
//     text = text.replace(/^## (.+)$/gm, '<strong style="font-size:1.1em;display:block;margin-top:.5em">$1</strong>');
//     text = text.replace(/^# (.+)$/gm, '<strong style="font-size:1.15em;display:block;margin-top:.5em">$1</strong>');
//     text = text.replace(/^---+$/gm, '<hr style="border:none;border-top:1px solid rgba(255,255,255,.15);margin:.6em 0">');
//     text = text.replace(/^[\-\*•]\s+(.+)$/gm, '<li>$1</li>');
//     text = text.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
//     text = text.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul class="bot-list">$1</ul>');
//     text = text.replace(/\n/g, '<br>');
//     text = text.replace(/(<\/ul>)<br>/g, '$1');
//     text = text.replace(/(<hr[^>]*>)<br>/g, '$1');
//     text = text.replace(/(<\/strong>)<br><br>/g, '$1<br>');

//     return text;
// }

/* ─── Markdown-like formatting for bot messages ─── */
function formatBotMessage(raw) {
    if (!raw || typeof raw !== "string") return "I can help with rooms, rates, and bookings.";

    let text = raw;

    // url

    text = text.replace(
        /\[([^\]]+)\]\(([^)]+)\)/g,
        '<a href="$2" target="_blank" style="color: var(--gold, #d4af37); text-decoration: underline; font-weight: 500;">$1</a>'
    );
    // 1. Bold text
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/__(.+?)__/g, '<strong>$1</strong>');

    // 2. Italics
    text = text.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');

    // 3. Headings
    text = text.replace(/^### (.+)$/gm, '<strong style="font-size:1.05em;display:block;margin-top:.5em">$1</strong>');
    text = text.replace(/^## (.+)$/gm, '<strong style="font-size:1.1em;display:block;margin-top:.5em">$1</strong>');
    text = text.replace(/^# (.+)$/gm, '<strong style="font-size:1.15em;display:block;margin-top:.5em">$1</strong>');

    // 4. Horizontal Rule
    text = text.replace(/^---+$/gm, '<hr style="border:none;border-top:1px solid rgba(255,255,255,.15);margin:.6em 0">');

    // 5. Bullet Lists
    text = text.replace(/^[\-\*•]\s+(.+)$/gm, '<li>$1</li>');
    text = text.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
    text = text.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul class="bot-list">$1</ul>');

    // 6. Basic Markdown Table Support
    if (text.includes('|')) {
        const lines = text.split('\n');
        let inTable = false;
        let tableHtml = '<div style="overflow-x:auto; margin:.5em 0;"><table class="table" style="font-size:0.88rem; width:100%; border-collapse:collapse;">';

        const processedLines = lines.map(line => {
            if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
                // Skip table header divider line like |---|---|
                if (line.includes('---')) return '';

                const cols = line.split('|').slice(1, -1).map(c => c.trim());
                const tag = !inTable ? 'th' : 'td';
                if (!inTable) inTable = true;

                return `<tr>${cols.map(c => `<${tag} style="padding:.5rem; border-bottom:1px solid rgba(255,255,255,.1);">${c}</${tag}>`).join('')}</tr>`;
            } else {
                if (inTable) {
                    inTable = false;
                    return '</table></div>' + line;
                }
                return line;
            }
        });
        if (inTable) processedLines.push('</table></div>');
        text = processedLines.filter(l => l !== '').join('\n');
    }

    // 7. Line breaks
    text = text.replace(/\n/g, '<br>');
    text = text.replace(/(<\/ul>)<br>/g, '$1');
    text = text.replace(/(<\/div>)<br>/g, '$1');
    text = text.replace(/(<hr[^>]*>)<br>/g, '$1');
    text = text.replace(/(<\/strong>)<br><br>/g, '$1<br>');

    return text;
}

function renderFooter() {
    const u = getUser();
    const token = getToken();

    // If no valid session token exists, clear stale localStorage thread state
    if (!u || !token) {
        clearSession();
    }

    document.body.insertAdjacentHTML("beforeend", `
    <footer class="footer"><div class="wrap row between"><p>© ${new Date().getFullYear()} Pearl Continental. All rights reserved.</p><p>Lahore, Pakistan · +92 42 111 505 505</p></div></footer>
    
    <button class="chat-fab" id="chat-fab" aria-label="Open concierge chat">💬</button>
    
    <section class="chat-panel" id="chat-panel" aria-label="Hotel concierge chat" role="dialog">
      <!-- SIDEBAR FOR THREADS (Rendered strictly if logged in) -->
      ${u && token ? `
      <div class="chat-sidebar" id="chat-sidebar">
        <div class="chat-sidebar-header">
          <strong>Conversations</strong>
          <button class="btn sm primary" id="sidebar-new-chat">+ New Chat</button>
        </div>
        <div class="thread-list" id="thread-list"></div>
      </div>` : ''}

      <!-- MAIN CHAT AREA -->
      <div class="chat-main-container">
        <div class="chat-head" id="chat-head">
          <div class="row" style="gap:.5rem; align-items:center;">
            ${u && token ? '<button class="btn sm" id="chat-toggle-sidebar" title="Toggle Threads" style="padding:.2rem .4rem;">☰</button>' : ''}
            <strong id="chat-title">${u && token ? "Pearl Continental Assistant" : "Front Desk Support"}</strong>
          </div>
          <div class="row" style="gap:.25rem">
            <button class="btn sm" id="chat-expand" title="Enlarge chatbot" style="padding:.2rem .5rem">🗖</button>
            <button class="btn sm" id="chat-close" aria-label="Close chat" style="padding:.2rem .5rem">✕</button>
          </div>
        </div>
        <div class="chat-log" id="chat-log">
          <div class="msg bot">${u && token ? "Hello! Ask me about rooms, availability, add-ons, or your bookings." : 'Welcome to Pearl Continental Lahore! Please <a href="login.html">log in</a> to unlock our full AI concierge.'}</div>
        </div>
        <form class="chat-form" id="chat-form">
          <label class="skip" for="chat-input">Message</label>
          <input id="chat-input" placeholder="${u && token ? "Ask about rooms or bookings…" : "Ask about check-in, timings, or policies…"}" autocomplete="off">
          <button class="btn primary" type="submit" id="chat-send-btn">Send</button>
        </form>
      </div>
    </section>`);

    const fab = $("chat-fab"), panel = $("chat-panel");
    if (!fab || !panel) return;

    fab.onclick = () => {
        panel.classList.add("open");
        fab.style.display = "none";
        $("chat-input").focus();
        if (u && token) loadThreads();
    };

    $("chat-close").onclick = () => {
        panel.classList.remove("open");
        panel.style.width = "";
        panel.style.height = "";
        panel.style.transform = "";
        fab.style.display = "";
    };

    const sidebar = $("chat-sidebar");
    const toggleSidebarBtn = $("chat-toggle-sidebar");
    if (toggleSidebarBtn && sidebar) {
        toggleSidebarBtn.onclick = () => {
            sidebar.classList.toggle("open");
        };
    }

    const expandBtn = $("chat-expand");
    let isExpanded = false;
    expandBtn.onclick = () => {
        isExpanded = !isExpanded;
        if (isExpanded) {
            panel.style.width = "min(900px, calc(100vw - 2rem))";
            panel.style.height = "min(750px, calc(100vh - 2rem))";
            expandBtn.textContent = "🗗";
        } else {
            panel.style.width = "";
            panel.style.height = "";
            expandBtn.textContent = "🗖";
        }
    };

    // --- INSTANT DRAGGABLE CHATBOX LOGIC ---
    const chatHead = $("chat-head");
    let isDragging = false, startX = 0, startY = 0, currentX = 0, currentY = 0;

    chatHead.onmousedown = (e) => {
        if (e.target.tagName === 'BUTTON' || e.target.closest('button')) return;
        isDragging = true;
        startX = e.clientX - currentX;
        startY = e.clientY - currentY;

        function onMouseMove(e) {
            if (!isDragging) return;
            currentX = e.clientX - startX;
            currentY = e.clientY - startY;
            panel.style.transform = `translate(${currentX}px, ${currentY}px)`;
        }

        function onMouseUp() {
            isDragging = false;
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        }

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
    };


    // async function loadChatHistory() {
    //     if (!u || !token) return;
    //     try {
    //         const url = chatThreadId ? `/chat/history?thread_id=${chatThreadId}` : "/chat/history";
    //         const r = await apiFetch(url);
    //         const d = await json(r);
    //         if (d.thread_id) {
    //             chatThreadId = d.thread_id;
    //             localStorage.setItem(THREAD_KEY, chatThreadId);
    //         }
    //         const log = $("chat-log");
    //         log.innerHTML = "";
    //         if (d.messages && d.messages.length > 0) {
    //             d.messages.forEach(m => {
    //                 const cls = m.sender === "user" ? "user" : "bot";
    //                 if (cls === "bot") {
    //                     log.insertAdjacentHTML("beforeend", `<div class="msg bot">${formatBotMessage(m.message)}</div>`);
    //                 } else {
    //                     log.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(m.message)}</div>`);
    //                 }
    //             });
    //         } else {
    //             log.innerHTML = '<div class="msg bot">Hello! How can I help you with your stay at Pearl Continental Lahore?</div>';
    //         }
    //         log.scrollTop = log.scrollHeight;
    //     } catch {
    //         // Fallback welcome
    //     }
    // }


    // ================= THREAD STATE =================
    const WELCOME = "Hello! How can I help you with your stay at Pearl Continental Hotel Lahore ?";
    const log = $("chat-log");                 // ONE shared definition (this was the missing piece)

    const PENDING_CHAT_KEY = "pc_pending_chat_turn";
    const DEFAULT_PLACEHOLDER = u && token ? "Ask about rooms or bookings…" : "Ask about check-in, timings, or policies…";


    const stored = localStorage.getItem(THREAD_KEY);
    let chatThreadId = stored && stored !== "undefined" && stored !== "null" ? stored : null;
    if (!chatThreadId) localStorage.removeItem(THREAD_KEY);
    let isChatBusy = false;
    let pendingPollTimer = null;
    function getPendingChat() {
        try {
            return JSON.parse(localStorage.getItem(PENDING_CHAT_KEY) || "null");
        } catch {
            return null;
        }
    }

    function setPendingChat(threadId, userText) {
        localStorage.setItem(PENDING_CHAT_KEY, JSON.stringify({
            threadId: threadId ? String(threadId) : (chatThreadId || null),
            userText,
            ts: Date.now(),
        }));
    }

    function clearPendingChat() {
        localStorage.removeItem(PENDING_CHAT_KEY);
        if (pendingPollTimer) {
            clearInterval(pendingPollTimer);
            pendingPollTimer = null;
        }
    }

    function setChatLocked(locked, msg = "Pearl Continental Assistant is thinking…") {
        isChatBusy = locked;
        const input = $("chat-input");
        const sendBtn = $("chat-send-btn");
        if (input) {
            input.disabled = locked;
            input.placeholder = locked ? msg : DEFAULT_PLACEHOLDER;
        }
        if (sendBtn) {
            sendBtn.disabled = locked;
        }
    }

    function setThread(id) {                   // never store garbage
        if (id === undefined || id === null || id === "undefined") return;
        chatThreadId = String(id);
        localStorage.setItem(THREAD_KEY, chatThreadId);
    }
    function forgetThread() { chatThreadId = null; localStorage.removeItem(THREAD_KEY); }
    function addMsg(role, text) {
        const html = role === "bot" ? formatBotMessage(text) : esc(text);
        log.insertAdjacentHTML("beforeend", `<div class="msg ${role}">${html}</div>`);
        log.scrollTop = log.scrollHeight;
    }
    function showWelcome() { log.innerHTML = ""; addMsg("bot", WELCOME); }

    // ================= THREAD LIST =================
    async function loadThreads() {
        const listEl = $("thread-list");
        if (!listEl) return;
        try {
            const r = await apiFetch("/chat/threads");
            const d = await json(r);
            const threads = Array.isArray(d) ? d : (d.threads || []);
            listEl.innerHTML = threads.length ? threads.map(t => {
                const raw = t.updated_at || t.created_at;
                const dateStr = raw ? fmtDate(String(raw).split("T")[0]) : "Today";
                return `<div class="thread-item ${String(t.id) === String(chatThreadId) ? "active" : ""}" data-id="${t.id}">
                          <span class="thread-title">${esc(t.title || "Conversation " + t.id)}</span>
                          <small class="muted">${esc(dateStr)}</small>
                        </div>`;
            }).join("") : '<div class="muted" style="padding:1rem;text-align:center;">No past threads</div>';

            listEl.querySelectorAll(".thread-item").forEach(item => {
                item.onclick = async () => {
                    const tid = item.getAttribute("data-id");
                    if (!tid) return;
                    setThread(tid);
                    listEl.querySelectorAll(".thread-item").forEach(i => i.classList.remove("active"));
                    item.classList.add("active");
                    await loadChatHistory(tid);
                    if (window.innerWidth <= 768 && sidebar) sidebar.classList.remove("open");
                };
            });
        } catch {
            listEl.innerHTML = '<div class="muted" style="padding:1rem;text-align:center;">Could not load threads</div>';
        }
    }

    // ================= HISTORY =================
    async function loadChatHistory(threadId = null) {
        if (!u || !token) return;
        try {


            const pending = getPendingChat();
            const tid = threadId || (pending && pending.threadId) || chatThreadId;

            // const tid = threadId || chatThreadId;
            const r = await apiFetch(tid ? `/chat/history?thread_id=${tid}` : "/chat/history");
            const d = await json(r);
            if (!r.ok) {

                forgetThread();
                clearPendingChat();
                setChatLocked(false);
                showWelcome(); return;
            }   // stale/foreign thread id -> start clean


            //     setThread(d.thread_id);
            //     log.innerHTML = "";
            //     if (d.messages && d.messages.length) {
            //         d.messages.forEach(m => addMsg(m.sender === "user" ? "user" : "bot", m.message));
            //     } else {
            //         showWelcome();
            //     }
            // } catch {
            //     if (!log.innerHTML.trim()) showWelcome();
            // }
            // }

            setThread(d.thread_id);
            log.innerHTML = "";
            const msgs = Array.isArray(d.messages) ? d.messages : [];
            if (msgs.length) {
                msgs.forEach(m => addMsg(m.sender === "user" ? "user" : "bot", m.message));
            } else {
                showWelcome();
            }

            const lastMsg = msgs[msgs.length - 1];
            const hasBotReply = Boolean(lastMsg && lastMsg.sender !== "user");

            if (pending && !hasBotReply) {
                setChatLocked(true, "Waiting for response before you can type…");
                if (!pendingPollTimer) {
                    pendingPollTimer = setInterval(() => {
                        loadChatHistory(d.thread_id || tid);
                    }, 2000);
                }
            } else {
                clearPendingChat();
                setChatLocked(false);
            }
        } catch {
            if (!log.innerHTML.trim()) showWelcome();
        }
    }

    // ================= NEW CHAT =================
    const newChatBtn = $("sidebar-new-chat");
    if (newChatBtn && u && token) {
        newChatBtn.onclick = async () => {
            try {
                const r = await apiFetch("/chat/new", { method: "POST" });
                if (!r.ok) throw new Error();
                forgetThread();              // the backend creates the thread on the first message
                showWelcome();
                await loadThreads();
                if (window.innerWidth <= 768 && sidebar) sidebar.classList.remove("open");
            } catch {
                toast("Could not start a new chat.", "error");
            }
        };
    }

    // ================= SEND =================
    let guestMessageCount = Number(sessionStorage.getItem("pc_guest_msgs") || 0);

    $("chat-form").onsubmit = async e => {
        e.preventDefault();
        // if (isChatBusy) return;
        if (isChatBusy || getPendingChat()) return;


        const input = $("chat-input"), sendBtn = $("chat-send-btn");
        const text = input.value.trim();
        if (!text) return;

        addMsg("user", text);                // show the guest's own bubble immediately
        input.value = "";

        if (!u || !token) {                  // visitors get one message, then a login prompt
            guestMessageCount++;
            sessionStorage.setItem("pc_guest_msgs", guestMessageCount);
            //     isChatBusy = true;
            //     input.disabled = true; sendBtn.disabled = true;
            //     input.placeholder = "Please log in to continue chatting…";
            //     setTimeout(() => addMsg("bot",
            //         'You have reached the message limit. Please [log in](login.html) or [register](register.html) to continue.'), 500);
            //     return;
            // }
            setChatLocked(true, "Please log in to continue chatting…");
            setTimeout(() => addMsg("bot",
                'You have reached the message limit. Please [log in](login.html) or [register](register.html) to continue.'), 500);
            return;
        }

        setPendingChat(chatThreadId, text);
        setChatLocked(true, "Pearl Continental Assistant is thinking…");

        isChatBusy = true;
        input.disabled = true; sendBtn.disabled = true;
        input.placeholder = "Pearl Continental Assistant is thinking…";

        const typingEl = document.createElement("div");
        typingEl.className = "msg bot typing-indicator";
        typingEl.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
        log.appendChild(typingEl);
        log.scrollTop = log.scrollHeight;

        // try {
        //     const body = { message: text };
        //     if (chatThreadId) body.thread_id = Number(chatThreadId);

        //     const r = await apiFetch("/chat", { method: "POST", body: JSON.stringify(body) });
        //     const d = await json(r);
        //     typingEl.remove();

        //     if (!r.ok) {
        //         if (r.status === 404) forgetThread();            // thread no longer exists
        //         addMsg("bot", errText(d, "Please contact our front desk at +92-42-111-505-505."));
        //     } else {
        //         setThread(d.thread_id);
        //         loadThreads();
        //         addMsg("bot", d.response || d.reply || d.message || "I can help with rooms, rates, and bookings.");
        //         window.dispatchEvent(new CustomEvent("pc-chatbot-action"));
        //     }
        // } catch {
        //     typingEl.remove();
        //     addMsg("bot", "Please contact our front desk at +92-42-111-505-505.");
        // }
        try {
            const body = { message: text };
            if (chatThreadId) body.thread_id = Number(chatThreadId);

            const r = await apiFetch("/chat", { method: "POST", body: JSON.stringify(body) });
            const d = await json(r);
            typingEl.remove();

            if (!r.ok) {
                if (r.status === 404) forgetThread();
                addMsg("bot", errText(d, "Please contact our front desk at +92-42-111-505-505."));
                clearPendingChat();
                setChatLocked(false);
                input.focus();
            } else {
                if (d.thread_id) {
                    setThread(d.thread_id);
                    setPendingChat(d.thread_id, text);
                }
                loadThreads();
                addMsg("bot", d.response || d.reply || d.message || "I can help with rooms, rates, and bookings.");
                clearPendingChat();
                setChatLocked(false);
                input.focus();
                window.dispatchEvent(new CustomEvent("pc-chatbot-action"));
            }
        } catch {
            typingEl.remove();
            addMsg("bot", "Please contact our front desk at +92-42-111-505-505.");
            clearPendingChat();
            setChatLocked(false);
            input.focus();
        } finally {                          // ALWAYS unlock the input, even if something throws
            isChatBusy = false;
            input.disabled = false; sendBtn.disabled = false;
            input.placeholder = "Ask about rooms or bookings…";
            input.focus();
        }
    };

    if (u && token) loadChatHistory().then(loadThreads);   // once, in this order
}
document.addEventListener("DOMContentLoaded", renderFooter);