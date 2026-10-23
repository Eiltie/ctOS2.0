const API = {
  base: "",
  chat: "/chat",
  sessions: "/sessions",
  model: "deepseek-v4-flash"
};

const TYPE_FRAME_MS = 16;
const TYPE_MIN_CPS  = 45;
const TYPE_MAX_CPS  = 220;

const state = {
  view: "chat",
  sessions: [],
  activeId: null,
  loaded: new Set()
};


const $ = (id) => document.getElementById(id);

const now = () => {
  const d = new Date();
  return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
};

function esc(s){
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function scrollDown(el){
  if (!el) return;
  el.scrollTop = el.scrollHeight;
}

async function getJson(url, options){
  try{
    const res = await fetch(API.base + url, options);
    if (!res.ok) return null;
    return await res.json();
  }catch(e){
    return null;
  }
}

function bindEnter(inputId, handler){
  const input = $(inputId);
  if (!input) return;
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing){
      e.preventDefault();
      handler();
    }
  });
}


let currentAbort = null;

function newAbortController(){
  if (currentAbort) currentAbort.abort();
  currentAbort = new AbortController();
  return currentAbort;
}

function finishAbort(ctl){
  if (currentAbort === ctl) currentAbort = null;
}

function currentSignal(){
  return currentAbort ? currentAbort.signal : undefined;
}

function abortCurrent(){
  if (currentAbort) currentAbort.abort();
  currentAbort = null;
}


const stickyHeads = new WeakMap();

function syncStickyHeads(){
  document.querySelectorAll("[data-sticky-head]").forEach((head) => {
    const host = head.parentElement;
    if (!host) return;
    const h = head.offsetHeight;
    if (stickyHeads.get(host) === h) return;
    stickyHeads.set(host, h);
    host.style.setProperty("--sticky-h", h + "px");
  });
}

window.addEventListener("resize", syncStickyHeads);
window.addEventListener("load", syncStickyHeads);

if (typeof ResizeObserver === "function"){
  const ro = new ResizeObserver(() => syncStickyHeads());
  document.querySelectorAll("[data-sticky-head]").forEach((h) => ro.observe(h));
}


function createSseParser(onEvent){
  let buf = "";

  const emit = (raw) => {
    let name = "";
    const dataLines = [];

    raw.split(/\r?\n/).forEach((line) => {
      if (!line || line.startsWith(":")) return;
      const colon = line.indexOf(":");
      const field = colon < 0 ? line : line.slice(0, colon);
      let value = colon < 0 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);

      if (field === "data") dataLines.push(value);
      else if (field === "event") name = value.trim();
    });

    if (!dataLines.length && !name) return;
    const data = dataLines.join("\n");

    let payload = null;
    try{
      payload = JSON.parse(data);
    }catch(e){
      payload = null;
    }

    if (payload && typeof payload === "object"){
      if (!payload.kind && name) payload.kind = name;
      onEvent(payload);
      return;
    }

    const kind = name || "TOKEN";
    if (data) onEvent({ kind, text: data });
    else if (name) onEvent({ kind });
  };

  return {
    push(chunk){
      if (!chunk) return;
      buf += chunk;
      let idx;
      while ((idx = buf.search(/\r?\n\r?\n/)) >= 0){
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx).replace(/^\r?\n\r?\n/, "");
        emit(raw);
      }
    },
    end(){
      if (buf.trim()) emit(buf);
      buf = "";
    }
  };
}


function createTyper(container, bubbleEl){
  const queue = [];
  let shown = "";
  let body = null;
  let cursor = null;
  let active = false;
  let finished = false;
  let cutOff = false;
  let raf = 0;

  const alive = () => container.isConnected && bubbleEl.isConnected;

  function ensureBody(){
    if (body) return;
    active = true;
    bubbleEl.classList.remove("loading-bubble");
    bubbleEl.textContent = "";
    body = document.createTextNode("");
    cursor = document.createElement("span");
    cursor.className = "type-cursor";
    bubbleEl.appendChild(body);
    bubbleEl.appendChild(cursor);
  }

  function dropCursor(){
    if (cursor && cursor.parentNode) cursor.parentNode.removeChild(cursor);
    cursor = null;
  }

  function untouched(){
    return !active;
  }

  function paintFinal(){
    if (!shown){
      bubbleEl.textContent = "";
      return;
    }
    bubbleEl.innerHTML = esc(shown).replace(/\n/g, "<br>");
  }

  function takeQuota(){
    const backlog = queue.reduce((n, s) => n + s.length, 0);
    const pressure = Math.min(1, backlog / 160);
    const cps = TYPE_MIN_CPS + (TYPE_MAX_CPS - TYPE_MIN_CPS) * pressure;
    let quota = Math.max(1, Math.round(cps * TYPE_FRAME_MS / 1000));

    while (quota > 0 && queue.length){
      const piece = queue[0];
      const take = piece.slice(0, quota);
      shown += take;
      quota -= take.length;
      if (take.length < piece.length) queue[0] = piece.slice(take.length);
      else queue.shift();
    }
  }

  function tick(){
    raf = 0;
    if (cutOff || !alive()) return;

    if (queue.length){
      ensureBody();
      takeQuota();
      body.data = shown;
      scrollDown(container);
    }
    if (finished && queue.length === 0){
      dropCursor();
      body = null;
      paintFinal();
      return;
    }
    raf = requestAnimationFrame(tick);
  }

  function schedule(){
    if (raf || cutOff) return;
    raf = requestAnimationFrame(tick);
  }

  return {
    push(piece){
      if (cutOff || !piece) return;
      queue.push(String(piece));
      schedule();
    },
    done(){
      finished = true;
      if (queue.length === 0 && !active){
        bubbleEl.classList.remove("loading-bubble");
        bubbleEl.textContent = "";
      }
      schedule();
    },
    cut(){
      if (cutOff) return shown;
      cutOff = true;
      if (raf){ cancelAnimationFrame(raf); raf = 0; }
      while (queue.length) shown += queue.shift();
      if (alive() && shown){
        ensureBody();
        body.data = shown;
        dropCursor();
        body = null;
        paintFinal();
      }
      return shown;
    },
    renderFinal(text){
      cutOff = true;
      finished = true;
      if (raf){ cancelAnimationFrame(raf); raf = 0; }
      queue.length = 0;
      shown = String(text == null ? "" : text);

      body = null;
      cursor = null;
      bubbleEl.textContent = "";
      bubbleEl.classList.remove("loading-bubble");
      if (!shown) return shown;

      paintFinal();
      scrollDown(container);
      return shown;
    },
    get text(){ return shown; },
    untouched
  };
}


function rowHTML(kind){
  const isUser = kind === "user";
  return `<div class="message-row ${isUser ? "user" : "ai"}">
      <div class="avatar ${isUser ? "user" : "ai"}">${isUser ? "你" : "AI"}</div>
      <div class="message-content">
        <div class="message-meta"><span>${isUser ? "你" : "ctOS"} ${now()}</span></div>
        <div class="bubble"></div>
      </div>
    </div>`;
}

function appendRow(feed, kind, text){
  const box = document.createElement("div");
  box.innerHTML = rowHTML(kind).trim();
  const el = box.firstElementChild;
  if (text != null){
    el.querySelector(".bubble").textContent = text;
    el.dataset.hasText = "1";
  }
  feed.appendChild(el);
  scrollDown(feed);
  return el;
}

function removeRow(row){
  if (row && row.parentNode) row.parentNode.removeChild(row);
}

function appendNotice(feed, text){
  const row = appendRow(feed, "ai", null);
  row.querySelector(".avatar").textContent = "!";
  row.querySelector(".message-meta span").textContent = `系统 ${now()}`;
  row.querySelector(".bubble").innerHTML = esc(text).replace(/\n/g, "<br>");
  return row;
}


const WELCOME = "你好。ctOS 在线，有什么需要我处理？";

function renderChat(){
  const feed = $("chat-feed");
  if (!feed) return;
  feed.innerHTML = "";

  const s = state.sessions.find((x) => x.id === state.activeId);

  if (!s || !state.loaded.has(s.id)){
    appendRow(feed, "ai", WELCOME);
    scrollDown(feed);
    return;
  }

  for (const m of (s.messages || [])){
    appendRow(feed, m.role === "user" ? "user" : "ai", m.text);
  }
  scrollDown(feed);
}


function renderHistory(){
  if (state.view === "trip"){ renderTripHistory(); return; }
  if (state.view === "customer"){ renderCustomerHistory(); return; }

  const box = $("history-chat");
  if (!box) return;

  /*
  if (!state.sessions.length){
    box.innerHTML = `<div class="empty-history">还没有会话记录。<br>在右边发一句话，会话就会存进来。</div>`;
    return;
  }
  */

  box.innerHTML = state.sessions.map((s) => `
    <div class="history-item${s.id === state.activeId ? " active" : ""}" data-sid="${s.id}">
      <span>${esc(s.title || "新对话")}</span>
      <span class="del" title="删除会话" data-del="${s.id}">🗑</span>
    </div>`).join("");

  box.querySelectorAll(".history-item").forEach((item) => {
    item.onclick = () => openSession(Number(item.dataset.sid));
  });

  box.querySelectorAll(".del").forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      removeSession(Number(el.dataset.del));
    };
  });
}

async function loadSessions(){
  const list = await getJson(API.sessions);

  if (!Array.isArray(list)){
    if (state.view === "chat") renderHistory();
    return;
  }

  state.sessions = list;

  if (!state.sessions.some((s) => s.id === state.activeId)){
    state.activeId = state.sessions.length ? state.sessions[0].id : null;
  }

  if (state.view === "chat") renderHistory();
}

async function openSession(id){
  state.activeId = id;
  if (state.view === "chat") renderHistory();

  const s = state.sessions.find((x) => x.id === id);
  if (!s) return;

  if (!state.loaded.has(id)){
    const rows = await getJson(`${API.sessions}/${id}/messages`);
    s.messages = (Array.isArray(rows) ? rows : []).map((m) => ({ role: m.role, text: m.content }));
    state.loaded.add(id);
  }

  if (state.activeId === id) renderChat();
}

async function removeSession(id){
  const s = state.sessions.find((x) => x.id === id);
  if (!s) return;

  if (!confirm(`确定删除会话「${s.title || "新对话"}」吗？\n\n该会话的全部聊天记录会一起删除，无法恢复。`)) return;

  const result = await getJson(`${API.sessions}/${id}`, { method: "DELETE" });

  if (!result){
    alert("删除失败：请确认后端已启动（python src/ctOS_chat_api.py）。");
    return;
  }

  state.sessions = state.sessions.filter((x) => x.id !== id);
  state.loaded.delete(id);

  if (state.activeId === id){
    state.activeId = state.sessions.length ? state.sessions[0].id : null;
    if (state.activeId) return openSession(state.activeId);
    renderChat();
  }

  renderHistory();
}


let chatBusy = false;

async function sendChat(){
  const input = $("chat-input");
  const feed = $("chat-feed");
  if (!input || !feed || chatBusy) return;

  const text = input.value.trim();
  if (!text) return;

  chatBusy = true;
  input.value = "";

  const count = $("char-count");
  if (count) count.textContent = "0 字符";

  const sessionId = state.activeId;
  const ctl = newAbortController();

  appendRow(feed, "user", text);

  const aiRow = appendRow(feed, "ai", null);
  const bubble = aiRow.querySelector(".bubble");
  bubble.classList.add("loading-bubble");
  bubble.textContent = "接入大模型中...";

  const typer = createTyper(feed, bubble);
  let failed = null;

  try{
    const payload = { messages: text };
    if (sessionId !== null) payload.session_id = sessionId;

    const res = await fetch(API.base + API.chat, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: ctl.signal
    });

    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    if (!res.body) throw new Error("当前浏览器不支持流式读取");

    const createdId = Number(res.headers.get("X-Session-Id"));
    if (sessionId === null && createdId) state.activeId = createdId;

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");

    while (true){
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      typer.push(decoder.decode(value, { stream: true }));
    }

    typer.push(decoder.decode());
    typer.done();
  }catch(err){
    if (err && err.name === "AbortError"){
      typer.cut();
    }else{
      failed = err;
      const partial = typer.cut();
      if (!partial) removeRow(aiRow);
      appendNotice(feed,
        "请求失败：" + (err && err.message ? err.message : err) +
        "\n请确认后端已启动：python src/ctOS_chat_api.py");
    }
  }finally{
    finishAbort(ctl);
    chatBusy = false;

    await loadSessions();

    const cur = state.activeId;

    if (cur !== null){
      const s = state.sessions.find((x) => x.id === cur);
      const rows = await getJson(`${API.sessions}/${cur}/messages`);
      if (s && Array.isArray(rows)){
        s.messages = rows.map((m) => ({ role: m.role, text: m.content }));
        state.loaded.add(cur);
      }
    }

    if (state.view === "chat") renderHistory();
    input.focus();
  }
}


function triggerHologram(){
  const overlay = $("hologram-overlay");

  if (overlay){
    overlay.classList.remove("activating");
    void overlay.offsetWidth;
    overlay.classList.add("activating");
  }

  if (state.view === "trip"){ tripNewSession(); return; }
  if (state.view === "customer"){ customerNewSession(); return; }

  setTimeout(() => {
    if (state.view !== "chat") return;
    abortCurrent();
    chatBusy = false;
    state.activeId = null;
    renderHistory();
    renderChat();
    const input = $("chat-input");
    if (input) input.focus();
  }, 300);
}


const VIEW_ORDER = ["chat", "trip", "customer"];

const VIEW_STATUS = {
  chat:     { tag: "LANGGRAPH · READY",  endpoint: "POST /chat",          ph: "向 ctOS 发送指令... (Enter 发送)" },
  trip:     { tag: "TRIP AGENT · READY", endpoint: "POST /trip/chat",     ph: "告诉我想去哪儿玩..." },
  customer: { tag: "RAG · READY",        endpoint: "POST /customer/chat", ph: "问一个关于本项目的问题..." }
};

function switchView(viewName){
  if (VIEW_ORDER.indexOf(viewName) < 0) return;
  state.view = viewName;

  const tabIndex = VIEW_ORDER.indexOf(viewName);
  document.querySelectorAll(".nav-tab").forEach((tab, i) => {
    tab.classList.toggle("active", i === tabIndex);
  });

  document.querySelectorAll(".main-content > .view-section").forEach((sec) => sec.classList.remove("active"));
  const view = $("view-" + viewName);
  if (view) view.classList.add("active");

  document.querySelectorAll(".nav-status .tag-status").forEach((tag) => tag.classList.remove("active"));
  const status = $("status-" + viewName);
  if (status) status.classList.add("active");

  document.querySelectorAll(".history-section .view-section").forEach((hist) => hist.classList.remove("active"));
  const hist = $("history-" + viewName);
  if (hist) hist.classList.add("active");

  const meta = VIEW_STATUS[viewName];
  const ep = $("foot-endpoint");
  if (ep) ep.textContent = meta.endpoint;

  const input = $("view-" + viewName + " input");
  if (input) input.placeholder = meta.ph;

  if (viewName === "trip"){
    renderTripHistory();
    loadTripRecords().then(renderTripHistory);
  }else if (viewName === "customer"){
    renderCustomerHistory();
  }else{
    renderHistory();
  }

  syncStickyHeads();
}


const aura = $("cursor-aura");
let mouseX = 0, mouseY = 0;
let auraX = 0, auraY = 0;

document.addEventListener("mousemove", (e) => {
  mouseX = e.clientX;
  mouseY = e.clientY;
  if (aura && aura.style.opacity === "0") aura.style.opacity = "1";
});

document.addEventListener("mouseleave", () => { if (aura) aura.style.opacity = "0"; });

function animateAura(){
  if (aura){
    auraX += (mouseX - auraX) * 0.15;
    auraY += (mouseY - auraY) * 0.15;
    aura.style.transform = `translate(${auraX}px, ${auraY}px) translate(-50%, -50%)`;
  }
  requestAnimationFrame(animateAura);
}

animateAura();


document.querySelectorAll(".custom-scroll").forEach((el) => {
  let scrollTimeout;
  el.addEventListener("scroll", () => {
    el.classList.add("is-scrolling");
    clearTimeout(scrollTimeout);
    scrollTimeout = setTimeout(() => el.classList.remove("is-scrolling"), 3000);
  });
});


(function initChatInput(){
  const chatInput = $("chat-input");
  const charCount = $("char-count");
  if (!chatInput) return;

  chatInput.addEventListener("input", (e) => {
    if (charCount) charCount.textContent = `${e.target.value.length} 字符`;
  });

  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing){
      e.preventDefault();
      sendChat();
    }
  });
})();


document.querySelectorAll(".quick-prompts .prompt-btn").forEach((btn) => {
  btn.onclick = () => {
    const input = $("chat-input");
    if (!input || chatBusy) return;

    input.value = btn.textContent.trim();
    const count = $("char-count");
    if (count) count.textContent = `${input.value.length} 字符`;

    switchView("chat");
    sendChat();
  };
});


window.addEventListener("DOMContentLoaded", async () => {
  const model = $("foot-model");
  if (model) model.textContent = API.model;

  bindEnter("trip-input", () => sendTrip());
  bindEnter("customer-input", () => sendCustomer());

  if (typeof tripInit === "function") tripInit();
  if (typeof customerInit === "function") customerInit();
  syncStickyHeads();

  await loadSessions();

  if (state.activeId !== null) await openSession(state.activeId);
  else renderChat();
});
