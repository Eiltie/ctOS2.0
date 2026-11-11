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

// 闲聊现在有两种玩法：普通聊天 / 角色扮演
let chatMode = "normal";          // normal / role-select / role-chat
let activeRole = null;            // 当前角色（角色聊天时才有）
let roleMemory = "";              // 当前角色记住的事
let roleSessionId = null;         // 当前角色会话
let normalSessionId = null;       // 切到角色玩法前，普通聊天停在哪个会话
let roleSessionCache = new Set(); // 哪些会话是角色会话，切回普通聊天时避开
let roleList = null;              // 预设角色列表，拉一次就缓存
let roleListLoading = false;
let roleFormSource = "custom";    // 当前表单保存成 custom 还是 ai_search
let roleMenuOpen = false;         // 侧栏「角色扮演」菜单是否展开

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

  // 角色聊天时，AI 头像和名字换成当前角色
  if (kind === "ai" && chatMode === "role-chat" && activeRole){
    el.querySelector(".avatar").textContent = activeRole.emoji || "AI";
    el.querySelector(".message-meta span").textContent = `${activeRole.name} ${now()}`;
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
  if (!s || !state.loaded.has(s.id) || !Array.isArray(s.messages)){
    appendRow(feed, "ai", WELCOME);
    scrollDown(feed);
    return;
  }

  for (const m of (s.messages || [])){
    appendRow(feed, m.role === "user" ? "user" : "ai", m.text);
  }
  scrollDown(feed);
}


// ===== 角色扮演 =====

// 根据模式切换三个区域：角色选择页 / 角色聊天 / 普通聊天
function showChatPanels(mode){
  const view = $("view-chat");
  if (!view) return;

  view.classList.toggle("role-select-mode", mode === "role-select");
  view.classList.toggle("role-chat-mode", mode === "role-chat");

  const select = $("role-select");
  const bar = $("role-bar");
  const feed = $("chat-feed");
  const bottom = $("chat-bottom");

  if (select) select.style.display = mode === "role-select" ? "flex" : "none";
  if (bar) bar.style.display = mode === "role-chat" ? "flex" : "none";
  if (feed) feed.style.display = mode === "role-select" ? "none" : "flex";
  if (bottom) bottom.style.display = mode === "role-select" ? "none" : "flex";

  document.querySelectorAll(".chat-plugin").forEach((btn) => {
    const plugin = btn.dataset.plugin;
    const on = (plugin === "normal" && mode === "normal") ||
               (plugin === "roleplay" && mode !== "normal");
    btn.classList.toggle("active", on);
  });

  const input = $("chat-input");
  if (input){
    input.placeholder = (mode === "role-chat" && activeRole)
      ? `和${activeRole.name}说点什么...`
      : VIEW_STATUS.chat.ph;
  }
}

// 角色聊天顶部的角色条 + 记忆条
function renderRoleBar(){
  const bar = $("role-bar");
  if (!bar) return;

  if (!activeRole){
    bar.innerHTML = "";
    return;
  }

  const memoryHtml = roleMemory ? `
    <div class="role-memory" id="role-memory">
      <span class="role-memory-text">↺ 它还记着：${esc(roleMemory)}</span>
      <button class="role-memory-clear" type="button" onclick="clearRoleMemory()">清空记忆</button>
    </div>` : "";

  bar.innerHTML = `
    <div class="role-banner">
      <span>${esc(activeRole.emoji || "")}</span>
      <span>正在和 <b>${esc(activeRole.name)}</b> 聊天</span>
      <button class="role-change" type="button" onclick="chatSetMode('role-select')">换角色</button>
    </div>
    ${memoryHtml}`;
}

// 选角色页
async function renderRoleSelect(){
  const box = $("role-select");
  if (!box) return;

  if (roleList === null){
    if (roleListLoading) return;
    roleListLoading = true;
    box.innerHTML = `<div class="role-select-loading">正在加载角色...</div>`;

    const data = await getJson("/roleplay/roles");
    roleListLoading = false;

    if (!data || !Array.isArray(data.roles)){
      box.innerHTML = `<div class="role-select-loading">角色加载失败，刷新页面再试</div>`;
      return;
    }
    roleList = data.roles;
  }

  if (!roleList.length){
    box.innerHTML = `<div class="role-select-loading">还没有预设角色</div>`;
    return;
  }

  const groups = [];
  roleList.forEach((role) => {
    if (!groups.includes(role.group)) groups.push(role.group);
  });

  const groupHtml = groups.map((group) => {
    const cards = roleList.filter((role) => role.group === group).map((role) => `
      <div class="role-card" data-role-id="${esc(role.id)}">
        <div class="role-card-top">
          <div class="role-emoji">${esc(role.emoji || "")}</div>
          <div>
            <div class="role-card-name">${esc(role.name)}</div>
            <div class="role-card-tag">${esc(role.tagline || "")}</div>
          </div>
        </div>
        <div class="role-card-opening">${esc(role.opening || "")}</div>
      </div>`).join("");

    return `<div class="role-group-label">${esc(group || "其他")}</div>
            <div class="role-grid">${cards}</div>`;
  }).join("");

  box.innerHTML = `
    <div class="role-select-inner">
      <div class="role-select-head">
        <h2>想和谁聊？</h2>
        <p>选一个角色直接开始</p>
      </div>
      ${groupHtml}

      <div class="role-advanced">
        <div class="role-advanced-title">想玩点不一样的？</div>
        <div class="role-adv-row">
          <button class="role-add-card" type="button" id="role-ai-btn">
            <span class="role-add-icon">🔍</span>
            <span class="role-add-text">
              <span class="role-add-name">AI 帮我查</span>
              <span class="role-add-desc">说个名字，我上网查资料写成角色</span>
            </span>
          </button>
          <button class="role-add-card" type="button" id="role-add-btn">
            <span class="role-add-icon">✍️</span>
            <span class="role-add-text">
              <span class="role-add-name">自己写一个角色</span>
              <span class="role-add-desc">名字、性格、说话方式都由你定</span>
            </span>
          </button>
        </div>
      </div>
    </div>`;

  box.querySelectorAll(".role-card").forEach((card) => {
    card.onclick = () => startRole(card.dataset.roleId);
  });

  const aiBtn = $("role-ai-btn");
  if (aiBtn) aiBtn.onclick = () => renderRoleSearch();

  const addBtn = $("role-add-btn");
  if (addBtn) addBtn.onclick = () => renderRoleCreate();
}

// 自己写角色的表单（AI 生成的草稿也用同一套表单）
function roleFormHTML(values){
  const v = values || {};

  return `
      <div class="role-form">
        <input type="hidden" id="rc-emoji" value="${esc(v.emoji || "🎭")}">
        <input type="hidden" id="rc-tagline" value="${esc(v.tagline || "")}">
        <input type="hidden" id="rc-speaking" value="${esc(v.speaking || "")}">

        <label class="role-field">
          <span>昵称</span>
          <input id="rc-name" maxlength="20" placeholder="比如：老船长" value="${esc(v.name || "")}">
        </label>

        <div class="role-row-two">
          <label class="role-field">
            <span>年龄</span>
            <input id="rc-age" maxlength="20" placeholder="比如：35" value="${esc(v.age || "")}">
          </label>
          <label class="role-field">
            <span>性别</span>
            <input id="rc-gender" maxlength="10" placeholder="比如：男 / 女" value="${esc(v.gender || "")}">
          </label>
        </div>

        <label class="role-field">
          <span>性格</span>
          <textarea id="rc-personality" maxlength="200" rows="2" placeholder="他是个什么样的人？">${esc(v.personality || "")}</textarea>
        </label>

        <label class="role-field">
          <span>人物事迹</span>
          <textarea id="rc-deeds" maxlength="300" rows="2" placeholder="他做过什么？经历过什么？">${esc(v.deeds || "")}</textarea>
        </label>

        <label class="role-field">
          <span>背景故事</span>
          <textarea id="rc-background" maxlength="300" rows="2" placeholder="他来自哪里？现在是什么处境？">${esc(v.background || "")}</textarea>
        </label>

        <label class="role-field">
          <span>补充说明</span>
          <textarea id="rc-extra" maxlength="300" rows="3" placeholder="例如：兴趣爱好：xxx，开场白：xxxx">${esc(v.extra || "")}</textarea>
        </label>
      </div>`;
}

function renderRoleForm(values, title, subtitle, buttonText, source){
  const box = $("role-select");
  if (!box) return;

  roleFormSource = source || "custom";

  box.innerHTML = `
    <div class="role-select-inner">
      <div class="role-create-head">
        <button class="role-back-btn" type="button" id="role-back-btn">← 返回角色列表</button>
        <h2>${esc(title)}</h2>
        <p>${esc(subtitle)}</p>
      </div>

      ${roleFormHTML(values)}

      <div class="role-form-actions">
        <button class="role-save-btn" type="button" id="role-save-btn">${esc(buttonText)}</button>
        <button class="role-back-btn" type="button" id="role-back-cancel">取消</button>
      </div>
    </div>`;

  $("role-back-btn").onclick = () => renderRoleSelect();
  $("role-back-cancel").onclick = () => renderRoleSelect();
  $("role-save-btn").onclick = () => createRole();

  if (!values || !values.name){
    const nameInput = $("rc-name");
    if (nameInput) nameInput.focus();
  }
}

function renderRoleCreate(){
  renderRoleForm({}, "写一个角色", "所有字段都可以不填，留空的交给角色自己。", "保存并开始聊", "custom");
}

function renderRoleDraft(role, note){
  const draft = Object.assign({}, role);
  const extra = (draft.extra || "").trim();

  // AI 已经写了开场白，就放进补充说明里给用户看/改
  if (draft.opening && !/开场白\s*[:：]/.test(extra)){
    draft.extra = (extra ? extra + "\n" : "") + "开场白：" + draft.opening;
  }

  renderRoleForm(draft, "这个角色可以吗？",
    note || "AI 查资料整理的，可以直接改。", "就这样开始聊", "ai_search");
}

// AI 帮我查：先输入名字，再等搜索和整理
function renderRoleSearch(){
  const box = $("role-select");
  if (!box) return;

  box.innerHTML = `
    <div class="role-select-inner">
      <div class="role-create-head">
        <button class="role-back-btn" type="button" id="role-search-back">← 返回角色列表</button>
        <h2>AI 帮我查</h2>
        <p>说一个名字或描述，我上网查资料，整理成角色。</p>
      </div>

      <label class="role-field">
        <span>想扮演谁？</span>
        <input id="rs-query" maxlength="60" placeholder="比如：孙悟空 / 晚清商人 / 高冷侦探">
      </label>

      <div class="role-form-actions">
        <button class="role-save-btn" type="button" id="rs-start">开始查资料</button>
        <span class="role-search-status" id="rs-status">大约需要 10~20 秒</span>
      </div>
    </div>`;

  $("role-search-back").onclick = () => renderRoleSelect();
  $("rs-start").onclick = () => searchRoleDraft();

  const input = $("rs-query");
  if (input){
    input.focus();
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing){
        e.preventDefault();
        searchRoleDraft();
      }
    });
  }
}

async function searchRoleDraft(){
  const input = $("rs-query");
  const query = input ? input.value.trim() : "";
  if (!query){
    alert("先说一个角色名或描述");
    if (input) input.focus();
    return;
  }

  const btn = $("rs-start");
  const status = $("rs-status");

  if (btn){
    btn.disabled = true;
    btn.textContent = "正在查资料...";
  }
  if (status) status.textContent = "正在上网搜索，再整理角色...";

  const timer = setTimeout(() => {
    if (status) status.textContent = "资料有点多，再等一下...";
  }, 8000);

  const data = await getJson("/roleplay/roles/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: query })
  });

  clearTimeout(timer);

  if (!data || !data.role){
    if (btn){
      btn.disabled = false;
      btn.textContent = "开始查资料";
    }
    if (status) status.textContent = "没查到，换个说法再试";
    alert("没查到，换个说法再试");
    return;
  }

  renderRoleDraft(data.role, data.note);
}

// 保存角色，然后直接开聊
async function createRole(){
  const payload = {
    name: $("rc-name").value.trim(),
    age: $("rc-age").value.trim(),
    gender: $("rc-gender").value.trim(),
    personality: $("rc-personality").value.trim(),
    deeds: $("rc-deeds").value.trim(),
    background: $("rc-background").value.trim(),
    extra: $("rc-extra").value.trim(),
    emoji: ($("rc-emoji").value || "").trim() || "🎭",
    tagline: $("rc-tagline").value.trim(),
    speaking: $("rc-speaking").value.trim(),
    source: roleFormSource
  };

  const saveBtn = $("role-save-btn");
  const saveText = saveBtn ? saveBtn.textContent : "保存并开始聊";
  if (saveBtn){
    saveBtn.disabled = true;
    saveBtn.textContent = "保存中...";
  }

  const data = await getJson("/roleplay/roles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!data || !data.role){
    if (saveBtn){
      saveBtn.disabled = false;
      saveBtn.textContent = saveText;
    }
    alert("保存失败，请检查内容后再试");
    return;
  }

  if (!roleList) roleList = [];
  roleList.push(data.role);

  await startRole(data.role.id);

  // 开聊失败时还留在表单里，把按钮恢复
  if (chatMode !== "role-chat" && saveBtn){
    saveBtn.disabled = false;
    saveBtn.textContent = saveText;
  }
}

// 发一次「开始角色」的请求。
// 不用 getJson，是因为要把 HTTP 状态码带出来，方便判断是旧服务器还是别的问题。
async function postStartRole(roleId){
  const res = await fetch(API.base + "/roleplay/start", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ role_id: roleId })
  });

  if (res.status === 401){
    handleAuthExpired();
    const err = new Error("登录已过期，请重新登录");
    err.status = 401;
    throw err;
  }

  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch(e){}

  if (!res.ok){
    const detail = data && data.detail ? data.detail : text.slice(0, 80);
    const err = new Error(`HTTP ${res.status}${detail ? "：" + detail : ""}`);
    err.status = res.status;
    throw err;
  }

  return data;
}

// 选了角色，开一个新会话
async function startRole(roleId){
  if (chatBusy) return;
  chatBusy = true;

  let data = null;
  let lastError = null;

  // 线上可能有两台服务器在轮换，旧的那台会 404。
  // 试两次，至少多一次机会落到新版本上。
  for (let attempt = 0; attempt < 2; attempt++){
    try{
      data = await postStartRole(roleId);
      break;
    }catch(err){
      lastError = err;
      if (err.status === 401) break;
      if (attempt === 0) await new Promise((resolve) => setTimeout(resolve, 400));
    }
  }

  chatBusy = false;

  if (!data || !data.session_id){
    const message = lastError ? lastError.message : "后端没有返回会话";
    alert(`开始角色失败：${message}\n\n如果线上有两台服务器，可能有一台还是旧版本。\n请先停掉旧的副本再试。`);
    return;
  }

  activeRole = data.role;
  roleMemory = data.memory || "";
  roleSessionId = data.session_id;
  state.activeId = roleSessionId;
  roleSessionCache.add(roleSessionId);
  state.loaded.add(roleSessionId);

  let s = state.sessions.find((x) => x.id === roleSessionId);
  if (!s){
    s = { id: roleSessionId, title: activeRole.name };
    state.sessions.unshift(s);
  }
  s.title = activeRole.name;
  s.messages = [{ role: "assistant", text: data.opening || "" }];

  chatMode = "role-chat";
  roleMenuOpen = true;
  showChatPanels(chatMode);
  renderRoleBar();
  renderChat();
  renderHistory();

  const input = $("chat-input");
  if (input) input.focus();
}

// 切换玩法：normal / role-select / role-chat
function chatSetMode(mode){
  if (chatBusy) return;

  if (mode === "normal"){
    if (chatMode === "normal" && state.activeId !== null
        && !roleSessionCache.has(state.activeId)){
      normalSessionId = state.activeId;
    }

    chatMode = "normal";
    activeRole = null;
    roleMemory = "";
    roleSessionId = null;

    let pick = null;
    if (normalSessionId && state.sessions.some((s) => s.id === normalSessionId)
        && !roleSessionCache.has(normalSessionId)){
      pick = normalSessionId;
    }
    if (pick === null){
      const found = state.sessions.find((s) => !roleSessionCache.has(s.id));
      pick = found ? found.id : null;
    }

    state.activeId = pick;
    showChatPanels("normal");
    renderRoleBar();
    renderHistory();

    if (pick !== null && !state.loaded.has(pick)) openSession(pick);
    else renderChat();
    return;
  }

  if (mode === "role-select"){
    if (chatMode === "normal") normalSessionId = state.activeId;

    chatMode = "role-select";
    roleMenuOpen = true;
    activeRole = null;
    roleMemory = "";
    roleSessionId = null;
    state.activeId = null;

    showChatPanels("role-select");
    renderRoleBar();
    renderRoleSelect();
    renderHistory();
    return;
  }

  if (mode === "role-chat" && activeRole){
    chatMode = "role-chat";
    showChatPanels("role-chat");
    renderRoleBar();
    renderChat();
  }
}

// 重新拉一下记忆，看有没有刚生成的
async function refreshRoleMemory(){
  if (!activeRole) return;
  const roleId = activeRole.id;

  const data = await getJson(`/roleplay/memory/${roleId}`);
  if (!activeRole || activeRole.id !== roleId) return;

  if (data && typeof data.memory === "string" && data.memory !== roleMemory){
    roleMemory = data.memory;
    renderRoleBar();
  }
}

// 清空当前角色的记忆
async function clearRoleMemory(){
  if (!activeRole) return;
  if (!confirm("清空这个角色对你的记忆？")) return;

  const roleId = activeRole.id;
  const data = await getJson("/roleplay/memory/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role_id: roleId })
  });

  if (!data){
    alert("清空失败，请稍后再试");
    return;
  }

  roleMemory = "";
  renderRoleBar();
}


// ===== 左侧会话列表 =====

// 这个会话是不是角色会话
function isRoleSession(session){
  return Boolean(session.role_id) || roleSessionCache.has(Number(session.id));
}

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

  const normalSessions = state.sessions.filter((s) => !isRoleSession(s));
  const roleSessions = state.sessions.filter((s) => isRoleSession(s));

  const normalRows = normalSessions.map((s) => `
    <div class="history-item${s.id === state.activeId && !historySelectMode ? " active" : ""}" data-sid="${s.id}">
      ${pickDotHTML(s.id)}
      <span class="hi-title">${esc(s.title || "新对话")}</span>
      <span class="del" title="删除会话" data-del="${s.id}">🗑</span>
    </div>`).join("");

  const roleRows = roleSessions.map((s) => `
    <div class="history-item role-history-item${s.id === state.activeId && !historySelectMode ? " active" : ""}" data-sid="${s.id}">
      <span class="role-mini">🎭</span>
      <span class="hi-title">${esc(s.title || "新角色")}</span>
      <span class="del" title="删除会话" data-del="${s.id}">🗑</span>
    </div>`).join("");

  const normalEmpty = normalSessions.length ? "" :
    `<div class="history-empty">还没有普通聊天</div>`;

  const roleMenu = `
    <div class="role-menu">
      <button class="role-menu-toggle${roleMenuOpen ? " open" : ""}" type="button" id="role-menu-toggle">
        <span class="role-menu-arrow">▸</span>
        <span class="role-menu-name">角色扮演</span>
        <span class="role-menu-count">${roleSessions.length}</span>
      </button>
      <div class="role-menu-list" style="display:${roleMenuOpen ? "block" : "none"}">
        ${roleRows || `<div class="history-empty">还没有角色聊天</div>`}
        <button class="role-menu-new" type="button" id="role-menu-new">＋ 新的角色聊天</button>
      </div>
    </div>`;

  box.innerHTML = normalRows + normalEmpty + roleMenu + selectBarHTML();

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

  const roleToggle = $("role-menu-toggle");
  if (roleToggle){
    roleToggle.onclick = () => {
      roleMenuOpen = !roleMenuOpen;
      renderHistory();
    };
  }

  const roleNew = $("role-menu-new");
  if (roleNew){
    roleNew.onclick = () => {
      if (historySelectMode) return;
      chatSetMode("role-select");
    };
  }

  bindPickDots(box, renderHistory);
  bindSelectBar(
    box,
    normalSessions.length,
    () => { historyPicked = new Set(normalSessions.map((s) => Number(s.id))); },
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

  const oldSessions = new Map(state.sessions.map((s) => [s.id, s]));

  // 服务器只返回会话标题，不返回消息。
  // 这里把本地已经拉过的消息带过去，否则切一下角色/发一条消息，
  // 旧会话的 messages 就被清空了，点回去会变成空白。
  state.sessions = list.map((item) => {
    const old = oldSessions.get(item.id);
    if (old && Array.isArray(old.messages)){
      item.messages = old.messages;
    }
    return item;
  });

  // 后端会告诉每个会话是不是角色会话，先记下来，
  // 切回普通聊天时就不会误把角色会话当普通聊天打开
  state.sessions.forEach((s) => {
    if (s.role_id) roleSessionCache.add(Number(s.id));
    else roleSessionCache.delete(Number(s.id));
  });

  // 被删掉的会话，把“已加载”标记也清掉
  const aliveIds = new Set(state.sessions.map((s) => s.id));
  state.loaded = new Set([...state.loaded].filter((id) => aliveIds.has(id)));

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

  // 消息按需拉；没有 messages 也重新拉，防止缓存标记还在但内容被覆盖掉了
  if (!state.loaded.has(id) || !Array.isArray(s.messages)){
    const rows = await getJson(`${API.sessions}/${id}/messages`);
    s.messages = (Array.isArray(rows) ? rows : []).map((m) => ({ role: m.role, text: m.content }));
    state.loaded.add(id);
  }

  // 这个会话是角色扮演还是普通闲聊？
  const roleInfo = s.role_id ? await getJson(`/roleplay/session/${id}`) : null;

  if (roleInfo && roleInfo.role){
    activeRole = roleInfo.role;
    roleMemory = roleInfo.memory || "";
    roleSessionId = id;
    chatMode = "role-chat";
    roleMenuOpen = true;
    roleSessionCache.add(id);
    showChatPanels("role-chat");
    renderRoleBar();
  }else{
    activeRole = null;
    roleMemory = "";
    roleSessionId = null;
    chatMode = "normal";
    normalSessionId = id;
    roleSessionCache.delete(id);
    showChatPanels("normal");
  }

  if (state.view === "chat"){
    renderChat();
    renderHistory();
  }
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

  // 页面刚打开时访客会话可能还在创建，等它完成再发，避免发出没 token 的请求
  if (!(await ensureSession(false))){
    appendNotice(feed, "会话还没准备好，请刷新页面重试");
    return;
  }

  chatBusy = true;
  input.value = "";

  const count = $("char-count");
  if (count) count.textContent = "0 字符";

  const sessionId = state.activeId;
  const ctl = newAbortController();

  appendRow(feed, "user", text);

  // 先放一个「接入中」的占位气泡，第一块字到了再换成打字机。
  // 角色扮演不显示这种技术提示，免得破坏角色感。
  const aiRow = appendRow(feed, "ai", null);
  const bubble = aiRow.querySelector(".bubble");
  bubble.classList.add("loading-bubble");
  bubble.textContent = (chatMode === "role-chat" && activeRole) ? "……" : "接入大模型中...";

  const typer = createTyper(feed, bubble);
  let failed = null;

  try{
    const payload = { messages: text };
    if (sessionId !== null) payload.session_id = sessionId;
    if (chatMode === "role-chat" && activeRole) payload.role_id = activeRole.id;

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

      // 角色聊天不用技术化的报错，免得破坏角色感
      if (chatMode === "role-chat" && activeRole){
        appendNotice(feed, "角色暂时没接上话，请稍后再试");
      }else{
        appendNotice(feed,
          "请求失败：" + (err && err.message ? err.message : err) +
          "\n请确认后端已启动：python -m api.main");
      }
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

    // 角色聊天：聊到第 6 轮后，后端会在后台整理记忆，这里刷新一下记忆条
    if (chatMode === "role-chat" && activeRole){
      setTimeout(refreshRoleMemory, 1200);
      setTimeout(refreshRoleMemory, 3500);
      setTimeout(refreshRoleMemory, 7000);
    }else if (chatMode === "normal" && state.activeId !== null){
      normalSessionId = state.activeId;
    }
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

  // 回到闲聊时，恢复上次停在哪：普通聊天 / 选角色 / 角色聊天
  if (viewName === "chat"){
    showChatPanels(chatMode);
    if (chatMode === "role-select") renderRoleSelect();
    else if (chatMode === "role-chat") renderRoleBar();

    if (chatMode !== "role-select") renderChat();
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

  // 角色玩法里点「新会话」就回到角色选择，不直接清成普通聊天
  if (state.view === "chat" && chatMode !== "normal"){
    chatSetMode("role-select");
    return;
  }

  setTimeout(() => {
    if (state.view !== "chat") return;
    abortCurrent();
    chatBusy = false;
    state.activeId = null;
    normalSessionId = null;
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

// 闲聊顶部的玩法切换：普通聊天 / 角色扮演
document.querySelectorAll(".chat-plugin").forEach((btn) => {
  btn.onclick = () => {
    if (chatBusy) return;
    chatSetMode(btn.dataset.plugin === "normal" ? "normal" : "role-select");
  };
});


// ===== 手机端侧栏抽屉 =====
// 桌面上侧栏常驻，这两个函数不起作用（CSS 里 .sidebar-toggle 只在窄屏显示）。
// 手机上侧栏默认滑出屏幕，点汉堡按钮滑入，点遮罩或选中会话后收回。

function openSidebar(){
  document.body.classList.add("sidebar-open");
}

function closeSidebar(){
  document.body.classList.remove("sidebar-open");
}

function toggleSidebar(){
  if (document.body.classList.contains("sidebar-open")) closeSidebar();
  else openSidebar();
}

// 手机上选中一个会话后自动收起侧栏，把屏幕让给对话
document.addEventListener("click", (e) => {
  if (e.target.closest("#history-chat .history-item") ||
      e.target.closest("#history-trip .history-item")){
    closeSidebar();
  }
});

// 窗口变宽（横屏/旋转回桌面宽度）时，保证回到「侧栏常驻」状态
window.addEventListener("resize", () => {
  if (window.innerWidth > 768) closeSidebar();
});


// ===== 启动 =====

let appModulesInited = false;

// 出行 / 客服只初始化一次。
// 正常路径在启动时调用；如果首屏自动进入失败、用户从登录框兜底登录，
// 也要在这里补一次，否则出行模块的壳子没有渲染。
function initAppModules(){
  if (appModulesInited) return;
  appModulesInited = true;
  if (typeof tripInit === "function") tripInit();
  if (typeof customerInit === "function") customerInit();
  syncStickyHeads();
}

// 登录成功后要重置界面：清掉上一个用户的残留数据
window.onLoginSuccess = async function(){
  state.sessions = [];
  state.activeId = null;
  state.loaded = new Set();
  state.view = "chat";

  // 角色玩法的状态也要清，避免带着上一个用户的数据
  chatMode = "normal";
  activeRole = null;
  roleMemory = "";
  roleSessionId = null;
  normalSessionId = null;
  roleSessionCache = new Set();
  roleMenuOpen = false;
  roleList = null;
  roleListLoading = false;

  renderUserBadge();
  initAppModules();

  // 出行模块的本地状态也要清，否则会带着上一个用户的会话
  if (typeof tripNewSession === "function") tripNewSession();
  if (typeof customerIntro === "function") customerIntro();

  switchView("chat");
  await loadSessions();
  renderChat();
  await syncTripRecords();
};

// 登录过期：
//   - 访客：静默换一个新访客身份，刷新后继续用，不再弹登录页
//   - 真实账号：弹登录框，让用户重新登录自己的账号
let authExpiredHandling = false;

window.onAuthExpired = async function(wasTrial){
  // 页面启动时可能同时发好几个请求，token 一过期就会一起 401。
  // 这里加个闸，避免同时创建多个访客账号。
  if (authExpiredHandling) return;
  authExpiredHandling = true;

  try{
    if (!wasTrial){
      showLogin();
      return;
    }

    const ok = await ensureSession(true);
    if (ok) location.reload();
    else showLogin();
  }finally{
    authExpiredHandling = false;
  }
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

  // 先确保有会话：
  //   有 token → 校验；没 token / token 失效 → 静默创建一个访客账号。
  // 页面本身已经直接显示主界面，这一步在后台完成，不会先闪登录框。
  const ok = await ensureSession(true);
  if (!ok){
    // 连访客账号都建不出来（通常是后端或数据库异常），才退回登录框兜底
    switchLoginMode("login");
    showLogin();
    loginError(sessionError ? "自动进入失败：" + sessionError : "自动进入失败，请刷新重试");
    return;
  }

  // 会话就绪：进入主界面
  showApp();
  renderUserBadge();
  initAppModules();

  await loadSessions();

  if (state.activeId !== null) await openSession(state.activeId);
  else renderChat();
});
