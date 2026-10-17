/* ============================================================
   智能出行模块（前端）

   后端契约:
       POST /trip/chat     { query, history }  ->  text/event-stream
       GET  /trip/list                         ->  出行记录列表
       GET  /trip/{id}                         ->  单条完整记录
       DELETE /trip/{id}                       ->  删除

   事件: START / STEP / TOKEN / DONE / CHAT / ERROR

   依赖（由 app.js 提供）：
       $  esc  md  API  state  sessionList
       send  renderSessions  syncTitle  newAbortSignal
   ============================================================ */

const TRIP_SECTIONS = [
  { key: "weather",    label: "天气" },
  { key: "spots",      label: "景点推荐" },
  { key: "itinerary",  label: "行程安排" },
  { key: "route_plan", label: "详细路线" }
];

const tripHistory = [];   // 用户说过的话，用于多轮合并（刷新即清空）

// 点一下就能问的示例（空的引导区用；点击即发送）
const TRIP_EXAMPLES = [
  { q: "下周想去杭州玩3天，带老人", meta: "3 天 · 带老人 · 雨天偏好室内" },
  { q: "成都4天，带小孩",           meta: "4 天 · 带小孩 · 节奏放缓" },
  { q: "三亚周末游，两个人",         meta: "2 天 · 情侣 · 看海为主" }
];

// 四个环节的流程条（和这张图的执行顺序一致）
const TRIP_FLOW = ["查询天气", "推荐景点", "安排行程", "规划路线"];

/* ---------- 空状态引导 ---------- */
function tripIntroHTML(){
  const steps = TRIP_FLOW
    .map((s, i) => `${i ? '<span class="flow-arrow">→</span>' : ""}` +
                   `<span class="flow-node"><b>${String(i + 1).padStart(2, "0")}</b>${esc(s)}</span>`)
    .join("");
  const cards = TRIP_EXAMPLES
    .map((e) => `<div class="tw-card" data-q="${esc(e.q)}">` +
                `<div class="tc-q">${esc(e.q)}</div>` +
                `<div class="tc-meta">${esc(e.meta)}</div></div>`)
    .join("");
  return `<div class="trip-welcome">` +
         `<h3>想去哪儿玩？交给我安排。</h3>` +
         `<div class="trip-flow">${steps}</div>` +
         `<div class="tw-label">试试这些</div>` +
         `<div class="tw-cards">${cards}</div>` +
         `</div>`;
}

function tripReset(){
  const out = $("tripOut");
  out.innerHTML = tripIntroHTML();
  out.querySelectorAll(".tw-card").forEach((c) => {
    c.onclick = () => send(c.dataset.q);
  });
  // 回到空状态：取消"当前打开哪条记录"的高亮
  activeTripId = null;
  if (state.mode === "trip") renderTripSessions();
}

// 第一条用户消息一到，就把引导区收起来
function tripDropIntro(){
  const w = $("tripOut").querySelector(".trip-welcome");
  if (w) w.remove();
}

/* ---------- 出行历史列表 ----------
   出行记录和闲聊会话是两套数据（出行存在 trip_* 表，闲聊存在 sessions 表），
   所以出行模式下左侧换成出行记录，点开时恢复四段卡片。 */

let tripRecords = [];        // 出行记录列表，来自 GET /trip/list
let activeTripId = null;     // 当前打开的出行记录 id（后端 trip_sessions.id）

async function syncTripRecords(){
  try{
    const res = await fetch(API.base + "/trip/list");
    if (!res.ok) return;
    const list = await res.json();
    if (Array.isArray(list)) tripRecords = list;
  }catch(e){
    // 后端没起就静默跳过
  }
}

function renderTripSessions(){
  if (!tripRecords.length){
    sessionList.innerHTML =
      `<div style="padding:14px 10px;color:#6b7280;font-size:13px;line-height:1.6">` +
      `还没有出行记录。<br>在上面说一句「想去哪儿玩」，规划完就会存进来。</div>`;
    return;
  }

  sessionList.innerHTML = tripRecords.map((r) => `
    <div class="session ${r.id === activeTripId ? "active" : ""}" data-trip="${r.id}">
      <span class="name">${esc(r.title || "出行记录")}</span>
      <button class="del" title="删除这条记录" data-deltrip="${r.id}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 6h18"/><path d="M8 6V4h8v2"/>
          <path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/>
        </svg>
      </button>
    </div>`).join("");

  sessionList.querySelectorAll(".session").forEach((el) => {
    el.onclick = () => {
      if (state.busy) return;
      openTripRecord(Number(el.dataset.trip));
    };
  });

  sessionList.querySelectorAll(".del").forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      if (state.busy) return;
      removeTripRecord(Number(btn.dataset.deltrip));
    };
  });
}

// 点开一条出行记录：拉详情，把四段卡片重新画出来
async function openTripRecord(tripId){
  let record;
  try{
    const res = await fetch(API.base + `/trip/${tripId}`);
    if (!res.ok) return;
    record = await res.json();
  }catch(e){
    return;
  }

  activeTripId = tripId;
  renderTripSessions();

  const out = $("tripOut");
  out.innerHTML = "";
  out.appendChild(cloneIntro());
  tripDropIntro();                       // 有内容了，收起引导区

  tripAppendUser(record.user_query || "");

  const ai = record.ai_output || {};

  // 闲聊分流存下来的记录：只回一句，没有四段卡片
  if (record.turn_kind === "CHAT"){
    tripChat(ai.chat_reply || "");
    return;
  }

  for (const section of TRIP_SECTIONS){
    const text = ai[section.key];
    if (!text) continue;
    tripSection(section.key);
    tripFinishSection(section.key, text);
    tripSetState(section.key, "done", "已完成");
  }
  tripScroll();
}

// 删除一条出行记录
async function removeTripRecord(tripId){
  const record = tripRecords.find((r) => r.id === tripId);
  if (!record) return;
  if (!confirm(`确定删除出行记录「${record.title}」吗？\n\n删除后无法恢复。`)) return;

  try{
    const res = await fetch(API.base + `/trip/${tripId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("HTTP " + res.status);
  }catch(e){
    alert("删除失败：" + (e && e.message ? e.message : e) + "\n\n请确认后端已启动。");
    return;
  }

  tripRecords = tripRecords.filter((r) => r.id !== tripId);
  if (activeTripId === tripId){
    activeTripId = null;
    tripReset();
  }
  renderTripSessions();
}

// 造一份引导区 DOM（复制一份，避免和模板字符串共享状态）
function cloneIntro(){
  const box = document.createElement("div");
  box.innerHTML = tripIntroHTML();
  box.querySelectorAll(".tw-card").forEach((c) => {
    c.onclick = () => send(c.dataset.q);
  });
  return box;
}

/* ---------- 渲染对话内容 ---------- */
function tripAppendUser(text){
  tripDropIntro();
  const div = document.createElement("div");
  div.className = "trip-user";
  div.innerHTML = `<b>${esc(text)}</b>`;
  $("tripOut").appendChild(div);
}

// 逐字流：按段把字追加到该段正文里
function tripAppendToken(key, text){
  const el = tripSection(key);
  el.dataset.state = "busy";
  const body = el.querySelector(".sec-body");
  body.classList.remove("busy");
  body.appendChild(document.createTextNode(text));
  tripScroll();
}

// 定稿：用整段重渲染，纠正逐字拼接可能的偏差
function tripFinishSection(key, fullText){
  const el = tripSection(key);
  const body = el.querySelector(".sec-body");
  body.classList.remove("busy");
  body.innerHTML = md(fullText, false);
  tripSetState(key, "done");
  tripScroll();
}

function tripStep(key, text){
  const el = tripSection(key);
  const cur = el.querySelector(".trip-step");
  if (cur){ cur.textContent = text; return; }
  const div = document.createElement("div");
  div.className = "trip-step";
  div.textContent = text;
  el.querySelector(".sec-body").appendChild(div);
  tripScroll();
}

function tripChat(msg){
  const div = document.createElement("div");
  div.className = "trip-chat";
  div.innerHTML = md(msg, false);
  $("tripOut").appendChild(div);
  tripScroll();
}

function tripError(msg){
  const div = document.createElement("div");
  div.className = "trip-err";
  div.textContent = msg;
  $("tripOut").appendChild(div);
  tripScroll();
}

function tripScroll(){
  const p = $("tripPanel");
  p.scrollTop = p.scrollHeight;
}

/* ---------- 耗时显示 ----------
   这张图要跑 5 次以上模型 + 几次联网搜索，通常 1~2 分钟，
   所以界面上要让人看得见"正在动、已经用了多久"，否则很像卡死。 */
let tripT0 = 0;
let tripClockId = null;

function tripSeconds(){
  return Math.round((Date.now() - tripT0) / 1000);
}

function tripClockStart(){
  tripT0 = Date.now();
  if (tripClockId) clearInterval(tripClockId);
  tripClockId = setInterval(() => {
    $("hintLeft").textContent = `规划中 ${tripSeconds()}s`;
  }, 1000);
}

function tripClockStop(){
  if (tripClockId){ clearInterval(tripClockId); tripClockId = null; }
}

function fmtSec(s){
  return s >= 60 ? `${Math.floor(s / 60)}分${String(s % 60).padStart(2, "0")}秒` : `${s} 秒`;
}

/* ---------- 四段卡片 ---------- */

// 请求刚发出时先建"天气"卡片并挂上"理解需求中"，让界面立刻有反馈
function tripPendingPhase(){
  tripStep("weather", "正在理解你的需求…");
}

function tripSection(key){
  let el = $("tripOut").querySelector(`[data-sec="${key}"]`);
  if (el) return el;
  const meta = TRIP_SECTIONS.find((s) => s.key === key);
  el = document.createElement("div");
  el.className = "trip-sec";
  el.dataset.sec = key;
  el.dataset.state = "busy";
  el.innerHTML =
    `<div class="sec-head"><span class="dot"></span><span>${esc(meta ? meta.label : key)}</span>` +
    `<span class="sec-state"></span></div><div class="sec-body"></div>`;
  $("tripOut").appendChild(el);
  return el;
}

function tripSetState(key, state, note){
  const el = tripSection(key);
  el.dataset.state = state;
  const st = el.querySelector(".sec-state");
  if (!st) return;
  // 已经记过耗时就别覆盖（TOKEN 流会反复调用本函数把状态打回"进行中"）
  if (st.textContent.startsWith("已完成 ·")) return;
  st.textContent = note || (state === "done" ? "已完成" : state === "busy" ? "进行中" : "等待");
}

// 定稿：记下这一段花了多久
function tripMarkDone(key){
  const st = tripSection(key).querySelector(".sec-state");
  if (st) st.textContent = `已完成 · ${fmtSec(tripSeconds())}`;
}

/* ---------- 发送 ---------- */
async function sendTrip(content){
  tripAppendUser(content);
  tripClockStart();            // 立刻开始计时，前端不再"毫无反馈"
  tripPendingPhase();          // 先亮出"正在理解你的需求…"

  const res = await fetch(API.base + "/trip/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: content, history: tripHistory }),
    signal: newAbortSignal()          // 供"停止生成"掐断
  });
  if (!res.ok) throw new Error("HTTP " + res.status + " " + res.statusText);
  if (!res.body) throw new Error("当前浏览器不支持流式读取");

  tripHistory.push(content);
  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  const handle = (ev) => {
    switch (ev.kind){
      case "START":
        // 计时已在提交时启动；这里不回显合并后的需求，用户只看到自己发的那句
        break;
      case "STEP":      tripStep(ev.key, ev.text); break;
      case "TOKEN":     tripAppendToken(ev.key, ev.text); break;
      case "DONE":      tripFinishSection(ev.key, ev.text); tripMarkDone(ev.key); break;
      case "CHAT":      tripChat(ev.message); tripClockStop(); break;
      case "ERROR":     tripError(ev.message); break;
    }
  };

  while (true){
    const { done, value } = await reader.read();
    if (done) break;
    if (!value) continue;
    buf += decoder.decode(value, { stream: true });

    // SSE：一条事件以空行结束；一行以 "data: " 开头
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0){
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of raw.split("\n")){
        if (!line.startsWith("data: ")) continue;
        try { handle(JSON.parse(line.slice(6))); } catch (e) { /* 半截事件，忽略 */ }
      }
    }
  }

  // 这一轮已经存进数据库了，刷新左边的出行记录列表
  await syncTripRecords();
  renderTripSessions();
}
