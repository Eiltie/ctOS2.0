// 闲聊模块：左侧会话列表 + 聊天区。
//
// 依赖（按 HTML 里的加载顺序）：
//   common/config.js    API、VIEW_STATUS
//   common/utils.js     $、esc、now、scrollDown、getJson、bindEnter
//   common/abort.js     newAbortController、finishAbort、abortCurrent
//   common/sse.js       createSseParser（纯文本流不用，但出行/客服要用）
//   common/typer.js     createTyper
//   common/selection.js 多选删除
//   common/sticky.js    syncStickyHeads
//
// 本文件里的事：
//   1. state          全局状态（当前视图、会话列表、已加载过消息的会话）
//   2. 消息渲染       appendRow / appendNotice / renderChat
//   3. 会话增删        loadSessions / openSession / removeSession / removeSessionsPicked
//   4. 发送            sendChat
//   5. 视图切换       switchView / triggerHologram
//   6. 启动           DOMContentLoaded 里按顺序初始化

// ===== 全局状态 =====

const state = {
  view: "chat",         // 当前视图：chat / trip / customer
  sessions: [],         // 闲聊会话列表（来自 GET /sessions）
  activeId: null,       // 当前打开的会话 id
  loaded: new Set()     // 哪些会话的消息已经拉过了，避免重复请求
};


// ===== 消息渲染 =====

let chatBusy = false;

// 一条消息的 HTML 骨架（头像 + 时间 + 气泡），内容后面再填
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

// 追加一行，返回这一行元素；text 为 null 时留空气泡（给流式用）
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

// 一行「系统提示」样式的消息，用于错误说明
function appendNotice(feed, text){
  const row = appendRow(feed, "ai", null);
  row.querySelector(".avatar").textContent = "!";
  row.querySelector(".message-meta span").textContent = `系统 ${now()}`;
  row.querySelector(".bubble").innerHTML = esc(text).replace(/\n/g, "<br>");
  return row;
}

// 把聊天区重画成「当前会话」的样子
function renderChat(){
  const feed = $("chat-feed");
  if (!feed) return;
  feed.innerHTML = "";

  const s = state.sessions.find((x) => x.id === state.activeId);

  // 没有会话，或者消息还没拉下来：显示欢迎语
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


// ===== 左侧会话列表 =====

function renderHistory(){
  // 出行和客服的列表由各自模块负责，这里只管闲聊
  if (state.view === "trip"){ renderTripHistory(); return; }
  if (state.view === "customer"){ renderCustomerHistory(); return; }

  const box = $("history-chat");
  if (!box) return;

  renderHistoryTitle();

  // 清掉已经不存在的勾选（比如别处删了会话）
  const alive = new Set(state.sessions.map((s) => Number(s.id)));
  historyPicked = new Set([...historyPicked].filter((id) => alive.has(id)));

  const rows = state.sessions.map((s) => `
    <div class="history-item${s.id === state.activeId && !historySelectMode ? " active" : ""}" data-sid="${s.id}">
      ${pickDotHTML(s.id)}
      <span class="hi-title">${esc(s.title || "新对话")}</span>
      <span class="del" title="删除会话" data-del="${s.id}">🗑</span>
    </div>`).join("");

  box.innerHTML = rows + selectBarHTML();

  box.querySelectorAll(".history-item").forEach((item) => {
    item.onclick = () => {
      if (historySelectMode) return;      // 多选模式下不打开会话
      openSession(Number(item.dataset.sid));
    };
  });

  box.querySelectorAll(".del").forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      removeSession(Number(el.dataset.del));
    };
  });

  bindPickDots(box, renderHistory);
  bindSelectBar(
    box,
    state.sessions.length,
    () => { historyPicked = new Set(state.sessions.map((s) => Number(s.id))); },
    removeSessionsPicked,
    renderHistory,
  );
}

async function removeSessionsPicked(ids){
  if (!ids.length) return;

  if (!confirm(`确定删除选中的 ${ids.length} 个对话吗？\n\n这些对话的全部消息会一起删除，无法恢复。`)) return;

  let failed = 0;
  for (const id of ids){
    const result = await getJson(`${API.sessions}/${id}`, { method: "DELETE" });
    if (!result){ failed += 1; continue; }

    state.sessions = state.sessions.filter((x) => x.id !== id);
    state.loaded.delete(id);
  }

  if (failed){
    alert(`有 ${failed} 个对话删除失败，请确认后端已启动。`);
  }

  // 当前打开的对话被删了就换一个
  if (ids.includes(state.activeId)){
    state.activeId = state.sessions.length ? state.sessions[0].id : null;
    if (state.activeId) await openSession(state.activeId);
    else renderChat();
  }

  historyPicked.clear();
  historySelectMode = false;
  renderHistory();
}

async function loadSessions(){
  const list = await getJson(API.sessions);

  if (!Array.isArray(list)){
    if (state.view === "chat") renderHistory();
    return;
  }

  state.sessions = list;

  // 当前打开的会话没了（被删了）就切到第一个
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

  // 消息按需拉，拉过一次就缓存
  if (!state.loaded.has(id)){
    const rows = await getJson(`${API.sessions}/${id}/messages`);
    s.messages = (Array.isArray(rows) ? rows : []).map((m) => ({ role: m.role, text: m.content }));
    state.loaded.add(id);
  }

  if (state.view === "chat") renderChat();
}

async function removeSession(id){
  if (!confirm("确定删除这个对话吗？\n\n全部消息会一起删除，无法恢复。")) return;

  const result = await getJson(`${API.sessions}/${id}`, { method: "DELETE" });
  if (!result){
    alert("删除失败，请确认后端已启动。");
    return;
  }

  state.sessions = state.sessions.filter((x) => x.id !== id);
  state.loaded.delete(id);

  if (state.activeId === id){
    state.activeId = state.sessions.length ? state.sessions[0].id : null;
    if (state.activeId) await openSession(state.activeId);
    else renderChat();
  }

  renderHistory();
}


// ===== 发送消息 =====

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

  // 先放一个「接入中」的占位气泡，第一块字到了再换成打字机
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
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
      signal: ctl.signal
    });

    // 401 = 登录过期，弹回登录页
    if (res.status === 401){
      handleAuthExpired();
      throw new Error("登录已过期，请重新登录");
    }

    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    if (!res.body) throw new Error("当前浏览器不支持流式读取");

    // 新会话的 id 由后端通过响应头回传
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
        "\n请确认后端已启动：python -m api.main");
    }
  }finally{
    finishAbort(ctl);
    chatBusy = false;

    await loadSessions();

    // 用服务端的完整记录覆盖本地缓存，保证和数据库一致
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


// ===== 视图切换 =====

function switchView(viewName){
  if (!VIEW_ORDER.includes(viewName)) return;

  state.view = viewName;

  // 主区域：只显示当前视图
  VIEW_ORDER.forEach((name) => {
    const view = $(`view-${name}`);
    if (view) view.classList.toggle("active", name === viewName);
  });

  // 左侧列表：三个模块各有一个，同样只显示当前那个。
  // 这里漏掉的话，出行和客服的会话列表会一直是 hidden，
  // 因为 CSS 里 .view-section 默认 display:none，只有 .active 才显示。
  VIEW_ORDER.forEach((name) => {
    const list = $(`history-${name}`);
    if (list) list.classList.toggle("active", name === viewName);
  });

  // 顶栏的 tab
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    const text = tab.textContent.trim();
    const match = { "闲聊": "chat", "智能出行": "trip", "智能客服": "customer" }[text];
    tab.classList.toggle("active", match === viewName);
  });

  // 右侧状态标签
  document.querySelectorAll(".tag-status").forEach((el) => {
    el.classList.toggle("active", el.id === `status-${viewName}`);
  });

  // 底部的端点和输入框提示
  const meta = VIEW_STATUS[viewName];
  const endpoint = $("foot-endpoint");
  if (endpoint && meta) endpoint.textContent = meta.endpoint;

  const activeInput = $({ chat: "chat-input", trip: "trip-input", customer: "customer-input" }[viewName]);
  if (activeInput && meta && meta.ph) activeInput.placeholder = meta.ph;

  // 换模块时退出多选，避免勾选状态带到另一个列表上
  if (historySelectMode){
    historySelectMode = false;
    historyPicked.clear();
  }
  renderHistoryTitle();     // 客服页没有会话列表，这里会把图标藏起来

  // 该显示哪个列表
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

// 「新会话」按钮：先放全息光幕动画，再交给当前模块处理
function triggerHologram(){
  const overlay = $("hologram-overlay");

  if (overlay){
    overlay.classList.remove("activating");
    void overlay.offsetWidth;     // 强制重排，让动画能重复触发
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


// ===== 输入框相关 =====

// 滚动条拖动时加一个类，用于样式上的「呼吸」效果
document.querySelectorAll(".custom-scroll").forEach((el) => {
  let scrollTimeout;
  el.addEventListener("scroll", () => {
    el.classList.add("is-scrolling");
    clearTimeout(scrollTimeout);
    scrollTimeout = setTimeout(() => el.classList.remove("is-scrolling"), 3000);
  });
});

// 闲聊输入框：字数统计 + 回车发送
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

// 快捷指令胶囊：点一下填进输入框并发送
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


// ===== 启动 =====

// 登录成功后要重置界面：清掉上一个用户的残留数据
window.onLoginSuccess = async function(){
  state.sessions = [];
  state.activeId = null;
  state.loaded = new Set();
  state.view = "chat";

  renderUserBadge();

  // 出行模块的本地状态也要清，否则会带着上一个用户的会话
  if (typeof tripNewSession === "function") tripNewSession();
  if (typeof customerIntro === "function") customerIntro();

  switchView("chat");
  await loadSessions();
  renderChat();
  await syncTripRecords();
};

// 登录过期时弹回登录页
window.onAuthExpired = function(){
  showLogin();
};

// 出行记录刷新（登录后要用当前用户的数据重新拉）
async function syncTripRecords(){
  if (typeof loadTripRecords === "function"){
    await loadTripRecords();
    if (typeof renderTripHistory === "function") renderTripHistory();
  }
}

window.addEventListener("DOMContentLoaded", async () => {
  const model = $("foot-model");
  if (model) model.textContent = API.model;

  // 三个模块的输入框都绑上回车
  bindEnter("trip-input", () => sendTrip());
  bindEnter("trip-input-hero", () => sendTrip());
  bindEnter("customer-input", () => sendCustomer());

  // 登录页的邮箱/密码框也支持回车提交
  bindEnter("login-email", () => submitAuth());
  bindEnter("login-password", () => submitAuth());

  // 没 token：显示登录页，不加载任何数据
  if (!getToken()){
    switchLoginMode("login");
    showLogin();
    return;
  }

  // 有 token：先验证它还有效
  const me = await authJson("/auth/me");
  if (!me){
    // token 失效（过期或被吊销）
    clearAuth();
    switchLoginMode("login");
    showLogin();
    return;
  }

  // token 有效：进入主界面
  saveAuth(getToken(), me);
  showApp();
  renderUserBadge();

  // 出行和客服各自初始化
  if (typeof tripInit === "function") tripInit();
  if (typeof customerInit === "function") customerInit();
  syncStickyHeads();

  await loadSessions();

  if (state.activeId !== null) await openSession(state.activeId);
  else renderChat();
});
