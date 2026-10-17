/* ============================================================
   ctOS 2.0 前端控制器
   后端契约: POST /chat  { "messages": "<string>" }  ->  text/plain 流式响应
   ============================================================ */
const API = {
  // 同源部署时留空即可；若页面由别处托管，改成 "http://127.0.0.1:4070"
  base: "",
  chat: "/chat",
  model: "deepseek-v4-flash"
};

/* ---------- 流式平滑输出参数（想调手感就改这里） ---------- */
const STREAM_SMOOTH        = true;  // false = 关掉平滑，收到即显示（回到原来的即时效果）
const STREAM_FRAME_MS      = 16;    // 每帧间隔，约 60fps
const STREAM_MIN_CPS       = 22;    // 最慢吐字速度（字/秒）：队列不多时按这个走，越小越慢
const STREAM_MAX_CPS       = 130;   // 最快吐字速度（字/秒）：积压太多时的上限，防止长回答越拖越久

const $ = (id) => document.getElementById(id);
const stream     = $("stream");
const input      = $("input");
const sendBtn    = $("send");
const sessionList= $("sessionList");
const barTitle   = $("barTitle");

/* ---------- 模块（闲聊 / 智能出行 / 智能客服） ---------- */
// ctOS 2.0 是多模块的：闲聊走 /chat（一张聊天图），智能出行走 /trip/chat（一张出行 agent 图），
// 智能客服走 /customer/chat（一张 RAG 检索图）。
// 三个模块共用这一个外壳，只切换主区面板与发送目标。
const state = {
  sessions: [],       // [{ id, title, messages:[{role,text,ts}] }]
  activeId: null,
  busy: false,
  mode: "chat"        // "chat" | "trip" | "customer"
};

/* ---------- 流式输出的运行时变量 ---------- */
let streamBuf     = [];     // 已收到但还没显示的字（队列）
let shownText     = "";     // 当前已经显示出来的文本
let streamTimer   = null;   // 驱动平滑输出的定时器
let streamStarted = false;  // 是否已经开始吐字（用于把 PROCESSING 换成正文）
let streaming     = false;  // 是否处于流式接收中

/* ---------- 工具 ---------- */
const now = () => {
  const d = new Date();
  return String(d.getHours()).padStart(2,"0") + ":" + String(d.getMinutes()).padStart(2,"0");
};
const uid = () => Math.random().toString(36).slice(2, 9);

/** 转义 HTML，避免把用户/模型输出当标签渲染 */
function esc(s){
  return String(s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

/** 极简 Markdown -> HTML（先转义再放行白名单语法）
 *
 *  streaming 参数：流式输出过程中传 true。
 *  此时模型可能只吐到一半——比如 ``` 开了头但结尾的反引号还没到。
 *  默认行为是「没闭合就不当代码块」，结果会露出裸的 ``` 符号；
 *  传 true 则把未闭合的部分也先按代码块渲染，视觉上更连贯。
 */
function md(src, streaming){
  let s = esc(src);

  // 围栏代码块 ```lang\n...```
  const blocks = [];
  s = s.replace(/```[a-zA-Z0-9_-]*\n([\s\S]*?)```/g, (_, code) => {
    blocks.push(code.replace(/\n$/, ""));
    return "\u0000BLOCK" + (blocks.length - 1) + "\u0000";
  });

  // 流式过程中：处理还没等到结尾反引号的「半开」代码块
  // 形如 ```python\n部分代码...   （后面没有 ``` 闭合）
  if (streaming){
    s = s.replace(/```[a-zA-Z0-9_-]*\n([\s\S]*)$/, (_, code) => {
      // 去掉最后一个多余的换行（那是排版换行，不是代码的一部分）
      blocks.push(code.replace(/\n$/, ""));
      // 末尾加个标记，稍后把它渲染成「还在写」的代码块
      return "\u0000BLOCK" + (blocks.length - 1) + "\u0000\u0000OPEN\u0000";
    });
  }

  // 行内代码
  s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  // 加粗 / 斜体
  s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>");

  // 列表
  s = s.replace(/^(?:[-*+]|\d+\.)\s+(.+)$/gm, "<li>$1</li>");
  s = s.replace(/(?:<li>[\s\S]*?<\/li>\s*)+/g, (m) => "<ul>" + m.trim() + "</ul>");

  // 段落
  s = s.split(/\n{2,}/).map((p) => {
    const t = p.trim();
    if (!t) return "";
    if (/^<(ul|pre|\u0000BLOCK)/.test(t)) return t;
    return "<p>" + t.replace(/\n/g, "<br>") + "</p>";
  }).join("");

  // 还原代码块；\u0000OPEN\u0000 标记的表示还在流式写入中
  s = s.replace(/\u0000BLOCK(\d+)\u0000(\u0000OPEN\u0000)?/g, (_, i, open) =>
    open ? '<pre class="block-open">' + blocks[+i] + "</pre>" : "<pre>" + blocks[+i] + "</pre>"
  );
  return s;
}

/* ---------- 渲染 ---------- */
function avatarFor(role){
  if (role === "user") return '<div class="avatar me">ME</div>';
  return '<div class="avatar ai">AI</div>';
}

function bubble(role, text, ts){
  const who = role === "user" ? "你" : "ctOS";
  return `
    <div class="msg ${role === "user" ? "user" : "ai"}">
      ${avatarFor(role)}
      <div class="body">
        <div class="meta"><span class="who">${who}</span><span>${ts || now()}</span></div>
        <div class="bubble">${md(text)}</div>
      </div>
    </div>`;
}

function renderStream(){
  const s = active();
  // messages 为 null 表示「这个会话来自后端，消息还没拉取」
  if (!s || !s.messages || s.messages.length === 0){ stream.innerHTML = ""; return; }

  stream.innerHTML = s.messages.map((m) =>
    m.role === "error"
      ? `<div class="msg error">
           <div class="avatar">!</div>
           <div class="body">
             <div class="meta"><span class="who">系统</span><span>${m.ts || now()}</span></div>
             <div class="bubble">${esc(m.text)}</div>
           </div>
         </div>`
      : bubble(m.role, m.text, m.ts)
  ).join("");

  scrollDown();
}

function scrollDown(){
  requestAnimationFrame(() => { stream.scrollTop = stream.scrollHeight; });
}

function appendMsg(role, text, ts){
  const s = active();
  if (!s) return null;
  if (!s.messages) s.messages = [];   // 来自后端、还没拉过消息的会话
  s.messages.push({ role, text, ts: ts || now() });
  renderStream();
  return s.messages[s.messages.length - 1];
}

function appendThinking(){
  const el = document.createElement("div");
  el.className = "msg ai";
  el.id = "thinkingMsg";
  el.innerHTML = `
    ${avatarFor("ai")}
    <div class="body">
      <div class="meta"><span class="who">ctOS</span><span>${now()}</span></div>
      <div class="bubble">
        <div class="thinking">
          <div class="dots"><i></i><i></i><i></i></div>
          <span>PROCESSING</span>
        </div>
      </div>
    </div>`;
  stream.appendChild(el);
  scrollDown();
}
function clearThinking(){
  const el = $("thinkingMsg");
  if (el) el.remove();
}

/* ---------- 流式接收（带平滑输出） ----------
   后端 text/plain 的裸文本流，实测首块 1.1s 到达、全部内容在 0.045s 内吐完，
   直接渲染等于「啪」一下全出现。这里把「到达」和「显示」解耦：
   收到的字先进队列，再由定时器按固定节奏往外吐，形成打字机效果。
------------------------------------------------------------------ */

// 计算这一帧该吐几个字。
// 用「字/秒」而不是「按剩余比例」，手感才稳定：
//   · 队列不多 —— 按 STREAM_MIN_CPS 匀速走，就是打字机的手感
//   · 积压很多 —— 逐步加速到 STREAM_MAX_CPS，避免长回答越拖越久
// 每帧字数 = 当前速度 × 帧间隔，至少 1 个（否则会卡住不出字）。
function drainCount(queueLen){
  if (queueLen <= 0) return 0;

  // 积压越多，速度向上限靠拢
  const pressure = Math.min(1, queueLen / 120);
  const cps = STREAM_MIN_CPS + (STREAM_MAX_CPS - STREAM_MIN_CPS) * pressure;
  const perFrame = Math.round(cps * STREAM_FRAME_MS / 1000);

  return Math.max(1, Math.min(perFrame, queueLen));
}

// 建一个「正在生长」的气泡，先显示 PROCESSING
function appendStreaming(){
  const el = document.createElement("div");
  el.className = "msg ai";
  el.id = "streamingMsg";
  el.innerHTML = `
    ${avatarFor("ai")}
    <div class="body">
      <div class="meta"><span class="who">ctOS</span><span id="streamTime">${now()}</span></div>
      <div class="bubble" id="streamBubble">
        <div class="thinking">
          <div class="dots"><i></i><i></i><i></i></div>
          <span>PROCESSING</span>
        </div>
      </div>
    </div>`;
  stream.appendChild(el);
  scrollDown();
  return el;
}

// 把已显示的文字画到气泡上
// 传 streaming=true 给 md()，让它把「还没闭合的代码块」也先渲染出来
function paintStreaming(text){
  const bubble = $("streamBubble");
  if (!bubble) return;
  bubble.innerHTML = md(text, true);
  scrollDown();
}

// 驱动一次平滑输出。返回 true 表示队列已吐完。
function pumpStreaming(){
  const bubble = $("streamBubble");
  if (!bubble) return true;

  const n = drainCount(streamBuf.length);
  if (n > 0){
    shownText += streamBuf.slice(0, n).join("");
    streamBuf.splice(0, n);

    // 第一帧吐字时，把 PROCESSING 换成正文
    if (!streamStarted){
      streamStarted = true;
      bubble.classList.add("streaming");
    }
    paintStreaming(shownText);
  }
  return streamBuf.length === 0;
}

// 流结束：停掉定时器，去掉光标，把最终文本落进会话数据里
function finishStreaming(fullText){
  streaming = false;
  if (streamTimer){
    clearInterval(streamTimer);
    streamTimer = null;
  }

  const el = $("streamingMsg");
  if (el) el.remove();

  const s = active();
  if (!s) return null;

  // 以后端给的完整文本为准（平滑显示可能少吐了几个字）
  const finalText = (fullText && fullText.length) ? fullText : shownText;

  if (!finalText || !finalText.trim().length){
    return appendMsg("error", "后端返回了空内容，请检查 /chat 的流式输出。");
  }

  const msg = { role: "ai", text: finalText, ts: now() };
  if (!s.messages) s.messages = [];
  s.messages.push(msg);
  renderStream();
  return msg;
}

/* ---------- 会话 ---------- */
function active(){ return state.sessions.find((s) => s.id === state.activeId); }

// 后端会话 id 的本地记录。后端只认整数 id，前端会话用随机串，
// 这里用一张映射表把两者对应起来，并持久化到 localStorage。
const LS_KEY = "ctos_session_map";

function loadMap(){
  try{
    return JSON.parse(localStorage.getItem(LS_KEY) || "{}");
  }catch(e){
    return {};
  }
}
function saveMap(map){
  try{ localStorage.setItem(LS_KEY, JSON.stringify(map)); }catch(e){}
}

let serverMap = loadMap();   // { 前端会话id: 后端session_id }

function newSession(title){
  const s = {
    id: uid(),
    title: title || "新对话",
    messages: [],
    titled: false        // 是否已用用户的第一句话取过标题
  };
  state.sessions.unshift(s);
  state.activeId = s.id;
  saveActive();
  renderSessions();
  renderStream();
  syncTitle();
  return s;
}

function renderSessions(){
  // 出行模式下，左侧显示出行记录；其余模式显示闲聊会话
  if (state.mode === "trip") return renderTripSessions();

  sessionList.innerHTML = state.sessions.map((s) => `
    <div class="session ${s.id === state.activeId ? "active" : ""}" data-id="${s.id}">
      <span class="name">${esc(s.title)}</span>
      <button class="del" title="删除会话" data-del="${s.id}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 6h18"/><path d="M8 6V4h8v2"/>
          <path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/>
        </svg>
      </button>
    </div>`).join("");

  // 删除按钮：阻止冒泡，避免触发外层的「切换会话」
  sessionList.querySelectorAll(".del").forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      if (state.busy) return;
      removeSessionFlow(btn.dataset.del);
    };
  });

  sessionList.querySelectorAll(".session").forEach((el) => {
    el.onclick = () => {
      if (state.busy) return;
      state.activeId = el.dataset.id;
      saveActive();
      renderSessions(); renderStream(); syncTitle();
      // 会话来自后端时，消息还在数据库里，需要拉一次
      ensureMessages(el.dataset.id);
    };
  });
}


/* ---------- 与后端的会话同步 ---------- */
// 前端会话 id 是随机串，后端是整数。serverMap 记录两者的对应关系。

/* ---------- 删除会话 ---------- */
async function removeSessionFlow(frontendId){
  const s = state.sessions.find((x) => x.id === frontendId);
  if (!s) return;

  // 还没入库的本地空会话，直接删掉就行，不用问
  const serverId = serverMap[frontendId];
  const hasServer = serverId !== undefined;

  const tip = hasServer
    ? `确定删除会话「${s.title}」吗？\n\n该会话的全部聊天记录会一起删除，无法恢复。`
    : `确定删除这个空白会话吗？`;

  if (!confirm(tip)) return;

  // 先删后端
  if (hasServer){
    try{
      const res = await fetch(API.base + `/sessions/${serverId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("HTTP " + res.status);
    }catch(e){
      alert("删除失败：" + (e && e.message ? e.message : e) + "\n\n请确认后端已启动。");
      return;
    }
    delete serverMap[frontendId];
    saveMap(serverMap);
  }

  // 再从前端列表移除
  const idx = state.sessions.findIndex((x) => x.id === frontendId);
  if (idx >= 0) state.sessions.splice(idx, 1);

  // 如果删的正好是当前打开的，切到剩下的第一个；一个都不剩就新建
  if (state.activeId === frontendId){
    if (state.sessions.length){
      state.activeId = state.sessions[0].id;
      saveActive();
      renderSessions();
      syncTitle();
      renderStream();
      await ensureMessages(state.activeId);
    } else {
      newSession();
      welcome();
    }
    return;
  }

  renderSessions();
}

// 记住当前停留的会话。存的是「后端会话 id」而不是前端随机 id，
// 因为前端 id 每次刷新都会重新生成，存了也没法用来找回。
const ACTIVE_KEY = "ctos_active_session";
function saveActive(){
  try{
    const sid = serverMap[state.activeId];
    localStorage.setItem(ACTIVE_KEY, sid === undefined ? "" : String(sid));
  }catch(e){}
}
function loadActive(){
  try{
    const v = localStorage.getItem(ACTIVE_KEY);
    return v ? Number(v) : null;
  }catch(e){ return null; }
}

// 从后端拉取会话列表，合并进前端（已存在的保留本地消息，不重复加载）
async function syncSessionsFromServer(){
  let list;
  try{
    const res = await fetch(API.base + "/sessions");
    if (!res.ok) return;
    list = await res.json();
  }catch(e){
    return;   // 后端没起就静默跳过，不影响本地使用
  }
  if (!Array.isArray(list)) return;

  // 注意：serverMap 是存在 localStorage 里的、刷新后还在；
  // 而 state.sessions 只在内存里、刷新后是空的。
  // 所以「这个会话是不是已经显示了」必须看 state.sessions，不能看 serverMap，
  // 否则刷新后所有历史会话都会被误判成「已经有了」而全部跳过。
  const shown = new Set(state.sessions.map((s) => serverMap[s.id]).filter((v) => v !== undefined));

  // 后端 id -> 前端会话 id，用于把已显示的会话和后端对应起来
  let changed = false;
  for (const row of list){
    if (shown.has(row.id)) continue;         // 界面上已经有了

    const fid = uid();
    serverMap[fid] = row.id;
    state.sessions.push({
      id: fid,
      title: row.title || "新对话",
      messages: null,                         // null = 还没从后端拉过
      titled: true                            // 已有后端标题，不再改
    });
    changed = true;
  }
  if (changed){
    saveMap(serverMap);
    renderSessions();
  }
}

// 某个会话的消息若还没加载过，就从后端拉
async function ensureMessages(frontendId){
  const s = state.sessions.find((x) => x.id === frontendId);
  if (!s || s.messages !== null) return;      // 已加载过

  const sid = serverMap[frontendId];
  if (sid === undefined){ s.messages = []; return; }

  try{
    const res = await fetch(API.base + `/sessions/${sid}/messages`);
    if (!res.ok){ s.messages = []; return; }
    const rows = await res.json();
    s.messages = rows.map((m) => ({
      role: m.role === "user" ? "user" : "ai",
      text: m.content,
      ts: ""
    }));
  }catch(e){
    s.messages = [];
  }
  renderStream();
}

function syncTitle(){
  const s = active();
  barTitle.textContent = s ? s.title : "新对话";
}

/* ---------- 停止生成 ----------
   每跑一次请求都换一个新的 AbortController，点"停止"就 abort 掉当前这个。
   注意：abort 只断掉【前端与后端的连接】，后端那个跑图线程会自己跑完
   （只是结果没人接收）。好处是界面立刻恢复自由，能切模块、能发新消息。 */
let currentAbort = null;

let stoppedByUser = false;   // 标记"这一轮是用户点停止掐掉的"

function newAbortSignal(){
  if (currentAbort) currentAbort.abort();      // 保险：上一次没清干净就先掐掉
  currentAbort = new AbortController();
  stoppedByUser = false;                       // 新一轮开始，清掉上次的标记
  return currentAbort.signal;
}

function stopCurrent(){
  if (currentAbort) currentAbort.abort();
  currentAbort = null;
  stoppedByUser = true;
  state.busy = false;
  setBusy(false);
  $("hintLeft").textContent = "已停止";
}

$("stop").onclick = stopCurrent;

/* ---------- 发送 ---------- */
async function send(text){
  const content = (text !== undefined ? text : input.value).trim();
  if (!content || state.busy) return;

  // 出行模块：走另一条链路（SSE 事件流），和闲聊图互不干扰
  if (state.mode === "trip"){
    state.busy = true;
    setBusy(true);
    if (text === undefined){ input.value = ""; autosize(); }
    try{
      await sendTrip(content);
    }catch(err){
      // 用户点了"停止"：不报错，安静收尾
      if (err && err.name === "AbortError") return;
      tripError("请求失败：" + (err && err.message ? err.message : err) +
                "\n\n请确认后端已启动：python src/ctOS_chat_api.py（端口 4070）");
    }finally{
      tripClockStop();
      // 只有"正常跑完"才显示用时；用户主动停的就保留"已停止"
      if (!stoppedByUser) $("hintLeft").textContent = `本次用时 ${fmtSec(tripSeconds())}`;
      state.busy = false;
      setBusy(false);
      input.focus();
    }
    return;
  }

  // 智能客服模块：一问一答，不进会话记录（每次提问都是独立的一次检索）
  if (state.mode === "customer"){
    state.busy = true;
    setBusy(true);
    if (text === undefined){ input.value = ""; autosize(); }
    try{
      await sendCustomer(content);
    }catch(err){
      if (err && err.name === "AbortError") return;   // 用户点了停止
      customerError("请求失败：" + (err && err.message ? err.message : err) +
                    "\n\n请确认后端已启动：python src/ctOS_chat_api.py（端口 4070）");
    }finally{
      state.busy = false;
      setBusy(false);
      input.focus();
    }
    return;
  }

  let s = active();
  if (!s) s = newSession();

  // 从后端拉回来的旧会话，发新消息前先把历史消息读出来，避免覆盖
  if (!s.messages) await ensureMessages(s.id);

  // 用户说的第一句话 -> 用它取会话标题。
  // 注意不能判断 messages.length === 0：会话里已经有那条欢迎语了，
  // 长度永远是 1 以上，所以要用 titled 标记。
  if (!s.titled){
    s.title = content.slice(0, 14) + (content.length > 14 ? "…" : "");
    s.titled = true;
    renderSessions(); syncTitle();
  }

  appendMsg("user", content);

  if (text === undefined){
    input.value = "";
    autosize();
  }

  state.busy = true;
  setBusy(true);
  appendThinking();

  let accumulated = "";

  try{
    // 带上后端会话 id，让服务端能把历史接上（首次为空，由后端新建）
    const payload = { messages: content };
    if (serverMap[s.id] !== undefined){
      payload.session_id = serverMap[s.id];
    }

    const res = await fetch(API.base + API.chat, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok){
      throw new Error("HTTP " + res.status + " " + res.statusText);
    }

    // 后端把本次使用的 session_id 放在响应头里，首次对话时记下来
    const sid = res.headers.get("X-Session-Id");
    if (sid && serverMap[s.id] === undefined){
      serverMap[s.id] = Number(sid);
      saveMap(serverMap);
    }
    // 此时映射已就绪，记下「当前停留在这个会话」，刷新后才能回到这里
    saveActive();

    // 后端返回 text/plain 的流。收到的内容先进队列，由定时器按节奏吐出来。
    if (!res.body){
      throw new Error("当前浏览器不支持流式读取（res.body 为空）");
    }

    clearThinking();
    appendStreaming();

    // 重置流式状态
    streamBuf = [];
    shownText = "";
    streamStarted = false;
    streaming = true;

    // 启动平滑输出：定时从队列取字画到气泡上
    if (streamTimer) clearInterval(streamTimer);
    if (!STREAM_SMOOTH){
      // 关掉平滑时，收到即画（走原逻辑，不排队）
      streamTimer = null;
    } else {
      streamTimer = setInterval(() => {
        if (!streaming) return;
        pumpStreaming();
      }, STREAM_FRAME_MS);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");

    // 往队列里塞字（或直接显示）
    const enqueue = (piece) => {
      if (!piece) return;
      accumulated += piece;
      if (STREAM_SMOOTH){
        // 逐字入队，才能保证吐字是均匀的
        for (const ch of piece) streamBuf.push(ch);
      } else {
        shownText = accumulated;
        paintStreaming(shownText);
      }
    };

    while (true){
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      enqueue(decoder.decode(value, { stream: true }));
    }

    // 冲掉解码器里可能残留的字节
    enqueue(decoder.decode());

    // 等队列吐完再收尾，否则会「啪」一下跳到最后
    if (STREAM_SMOOTH){
      await new Promise((resolve) => {
        const wait = setInterval(() => {
          if (!streaming || streamBuf.length === 0){
            clearInterval(wait);
            resolve();
          }
        }, STREAM_FRAME_MS);
      });
    }

    finishStreaming(accumulated);
  }catch(err){
    streaming = false;
    if (streamTimer){ clearInterval(streamTimer); streamTimer = null; }
    clearThinking();
    const el = $("streamingMsg");
    if (el) el.remove();

    // 已经收到部分内容就保留下来，同时提示中断
    const partial = STREAM_SMOOTH ? shownText : accumulated;
    if (partial){
      appendMsg("ai", partial);
      appendMsg("error",
        "回复中断：" + (err && err.message ? err.message : err));
    } else {
      appendMsg("error",
        "请求失败：" + (err && err.message ? err.message : err) +
        "\n\n请确认后端已启动：python src/ctOS_chat_api.py（端口 4070）");
    }
  }finally{
    state.busy = false;
    setBusy(false);
    input.focus();
  }
}

function setBusy(b){
  sendBtn.disabled = b;

  // 跑图期间：发送按钮换成"停止生成"按钮（靠 CSS 的 .composer.running 切换）
  document.querySelector(".composer").classList.toggle("running", b);

  // 计时器在跑的时候，别用 READY 把它盖掉（出行模块靠它显示"规划中 12s"）
  if (!b) $("hintLeft").textContent = "READY";
  else if (!$("hintLeft").textContent.startsWith("规划中")) $("hintLeft").textContent = "PROCESSING…";
}

/* ---------- 输入框 ---------- */
function autosize(){
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 148) + "px";
  $("hintRight").textContent = input.value.length + " 字符";
}

input.addEventListener("input", autosize);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing){
    e.preventDefault();
    send();
  }
});
sendBtn.onclick = () => send();

/* ---------- 快捷指令（按模块分组） ---------- */
const QUICK = {
  chat: [
    "你好，介绍一下你自己",
    "帮我梳理今天的待办事项",
    "用 Python 写一个快速排序",
    "解释一下 LangGraph 的作用"
  ],
  trip: [
    "下周想去杭州玩3天，带老人",
    "成都4天，带小孩",
    "三亚周末游，两个人"
  ],
  customer: [
    "这个项目有哪些模块？",
    "怎么启动这个项目？",
    "端口怎么改？",
    "智能客服是怎么工作的？"
  ]
};

function renderQuick(){
  const list = QUICK[state.mode] || QUICK.chat;
  $("quick").innerHTML = list.map((q) => `<div class="chip">${esc(q)}</div>`).join("");
  $("quick").querySelectorAll(".chip").forEach((el) => {
    el.onclick = () => send(el.textContent);
  });
}
renderQuick();

/* ---------- 顶栏按钮 ----------
   「新会话」按当前模块分别处理：
       闲聊 —— 新建一个会话，并清空对话区
       出行 —— 清空面板回到引导页（出行记录存在数据库里，不需要在这里建）
       客服 —— 清空面板回到引导页（一问一答，本来就不存会话） */
$("btnNew").onclick = () => {
  if (state.busy) return;

  if (state.mode === "trip"){
    tripReset();
  } else if (state.mode === "customer"){
    customerReset();
  } else {
    newSession();
  }
  input.focus();
};

/* ---------- 引导语 ---------- */
function welcome(){
  const s = active();
  if (!s) return;
  s.messages.push({
    role: "ai",
    text: [
      "**ctOS 2.0 已就绪。**",
      "",
      "我是运行在 LangGraph 之上的智能处理单元，随时可以协助你处理对话、分析与生成类任务。",
      "",
      "可以直接输入指令，或从下方快捷指令开始。"
    ].join("\n"),
    ts: now()
  });
  if (state.mode === "chat") renderStream();
}

/* ---------- 模块切换 ---------- */
function setMode(m){
  state.mode = m;
  document.querySelectorAll(".mode-btn").forEach((b) => {
    b.classList.toggle("on", b.dataset.mode === m);
  });

  const trip     = m === "trip";
  const customer = m === "customer";

  // 三个面板互斥：闲聊用 stream，另外两个各自有面板
  stream.style.display = (trip || customer) ? "none" : "";
  $("tripPanel").classList.toggle("on", trip);
  $("customerPanel").classList.toggle("on", customer);

  // 顶栏标签与标题
  if (customer){
    $("barTag").textContent = "RAG · READY";
    $("barTitle").textContent = "智能客服";
  } else if (trip){
    $("barTag").textContent = "TRIP AGENT · READY";
    $("barTitle").textContent = "智能出行";
  } else {
    $("barTag").textContent = "LANGGRAPH · READY";
    $("barTitle").textContent = active() ? active().title : "新对话";
  }

  // 输入框提示语
  if (customer){
    input.placeholder = "问一个关于本项目的问题…  例：怎么修改端口？";
  } else if (trip){
    input.placeholder = "告诉我想去哪玩…  例：下周想去杭州玩3天，带老人";
  } else {
    input.placeholder = "向 ctOS 发送指令…  (Enter 发送 · Shift+Enter 换行)";
  }

  renderQuick();

  // 左侧列表跟着模式换，三种情况分开处理：
  //   闲聊 —— 显示闲聊会话（sessions 表）
  //   出行 —— 显示出行记录（trip_* 表）
  //   客服 —— 一问一答不留记录，左侧整个收起来
  document.querySelector(".app").classList.toggle("no-sidebar", customer);

  if (trip){
    syncTripRecords().then(renderTripSessions);
  } else if (!customer){
    renderSessions();
  }
}

document.querySelectorAll(".mode-btn").forEach((b) => {
  b.onclick = () => {
    // 注意：这里【不再】因为 state.busy 就拒绝切换。
    // 三个模块各有独立面板，跑图期间切走不影响那张图——
    // 之前拦着会让人以为"网页卡死了"，其实只是按钮被禁用。
    // 只挡住"重复点当前模块"这一种无效操作。
    if (b.dataset.mode === state.mode) return;

    // 只在【不在跑图】时才重置面板。
    // 跑图中重置会清空面板，切回来就看不到进度了（面板 DOM 本来是保留的）。
    if (!state.busy){
      if (b.dataset.mode === "trip") tripReset();
      if (b.dataset.mode === "customer") customerReset();
    }
    setMode(b.dataset.mode);
  };
});

/* ---------- 初始化 ----------
   注意：trip.js 和 customer.js 在 app.js 之后加载，
   所以这里用 DOMContentLoaded 包一层，等三个文件都就绪再跑初始化，
   否则 tripReset() / customerReset() 会因为函数还不存在而报错。 */
document.addEventListener("DOMContentLoaded", () => {
  tripReset();           // 先把出行模块的空状态引导渲染好（点进去就有内容，不是空白）
  customerReset();       // 客服面板同样先渲染空状态引导
  setMode("chat");       // 默认闲聊模块（同时把三个面板的显隐、提示文字摆正）
  $("footModel").textContent = API.model;
  autosize();
  input.focus();

  // 先读出来上次停留的位置 —— 必须赶在 newSession() 之前，
  // 因为 newSession() 会把当前会话写进 localStorage，覆盖掉这个值。
  // 存的是「后端会话 id」，因为前端 id 每次刷新都会重新随机生成，没法用来认路。
  const lastServerId = loadActive();

  // 先建一个本地空会话，保证界面立刻可用（后端没起也能用）
  const bootSession = newSession();
  welcome();

  // 再从后端把历史会话补进侧边栏，并恢复上次打开的那个
  (async function restore(){
    await syncSessionsFromServer();

    // 按后端 id 找回上次那个会话
    const target = state.sessions.find((s) => serverMap[s.id] === lastServerId);
    if (target){
      // 刚才那个空白的新会话没人用，删掉
      const idx = state.sessions.indexOf(bootSession);
      if (idx >= 0 && bootSession.messages && bootSession.messages.length <= 1){
        state.sessions.splice(idx, 1);
      }
      state.activeId = target.id;
      saveActive();
      renderSessions();
      syncTitle();
      await ensureMessages(target.id);
      scrollDown();
    }
  })();
});
