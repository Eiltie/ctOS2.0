/* 出行｜公共壳子 + 这个模块的全部界面逻辑
 *
 * 做什么：进度条、开场/对话态切换、SSE 流、四段卡片、计时、出行记录列表，
 *         以及路线和攻略各自的等待面板（候选路线、地点候选、景点勾选）。
 * 谁在用：trip.js（入口）调 tripInit；app.js 调 sendTrip。
 *
 * 为什么没有"模式"了：
 *   智能出行是一个 Agent，用户只说一句话，由它决定走路线还是攻略。
 *   所以界面不再有"当前模式"——进度条和段落都按**这一轮实际返回了什么**来画：
 *   收到 START 里的 mode 才切换进度条，收到 STEP/DONE 的 key 才建对应段落。
 */

// 两种能力的"长相"：进度条有哪几步、每段叫什么、从哪条接口进来。
// 这不是让用户选的东西，只是界面上的映射表。
const TRIP_VIEWS = {
  ROUTE: {
    steps: ["route_need", "route_compare", "route_decision", "route_tips"],
    stepLabels: ["确认需求", "查询候选", "推荐方案", "出发提醒"],
    sections: [
      { key: "route_need",     label: "需求确认" },
      { key: "route_compare",  label: "候选路线对比" },
      { key: "route_decision", label: "推荐方案" },
      { key: "route_tips",     label: "出发提醒" }
    ]
  },
  TRAVEL: {
    steps: ["weather", "spots", "itinerary", "advice"],
    stepLabels: ["查询天气", "推荐景点", "安排行程", "游玩建议"],
    sections: [
      { key: "weather",    label: "天气" },
      { key: "spots",      label: "景点推荐" },
      { key: "itinerary",  label: "行程安排" },
      { key: "advice",     label: "游玩建议" },
      // 拆分前的老记录第四段是"详细路线"。新记录没有这一列，不会显示
      { key: "route_plan", label: "详细路线（旧版）" }
    ]
  }
};

// 所有段落，两边合在一起——按 key 找标题，不用先知道是哪一边的
const TRIP_SECTION_LABELS = Object.assign(
  {}, TRIP_VIEWS.TRAVEL.sections.reduce((acc, s) => (acc[s.key] = s.label, acc), {}),
  TRIP_VIEWS.ROUTE.sections.reduce((acc, s) => (acc[s.key] = s.label, acc), {}),
);

// 只有一个入口：用户说什么，交给 Agent 判断
const TRIP_ENDPOINT = "/trip/chat";

// 当前这一轮走的是哪条能力。只影响进度条画什么，不影响用户操作
let tripView = null;

// 开场页的示例和预设问题
const TRIP_EXAMPLES = [
  { q: "从杭州东站到灵隐寺，带老人，少走路", meta: "路线 · 少步行" },
  { q: "下周去杭州玩 3 天，带老人",        meta: "攻略 · 3 天" },
  { q: "北京有什么好玩的",                 meta: "直接问就行" }
];

const TRIP_QUICK_QUESTIONS = [
  "从杭州东站到灵隐寺怎么走",
  "下周去杭州玩3天，带老人",
  "北京有什么好玩的",
  "去杭州要准备什么"
];

const TRIP_PLACEHOLDER = "说说你的出行需求：想去哪玩、或者从哪到哪怎么走";

let tripBusy = false;
let tripCanRetry = false;
let lastTripText = "";
let tripHistory = [];
let tripRecords = [];
let activeTripId = null;
let openChatId = null;

let tripT0 = 0;
let tripClock = null;

// 中途停下来等用户选择的时间，不算进这一轮的用时
let tripWaitedTotal = 0;
let tripWaitStart = 0;


/* ===== 顶部进度条 ===== */

function tripRenderShell(){
  const box = $("trip-fixed");
  if (!box) return;

  // 还没跑任何一轮时给个中性的骨架；跑起来后按 START 的 mode 重画
  const view = tripView ? TRIP_VIEWS[tripView] : null;
  const steps = view ? view.steps.map((key, i) =>
    `<div class="process-step" data-step="${key}" data-state="wait">` +
    `<span class="step-num">${String(i + 1).padStart(2, "0")}</span> ${esc(view.stepLabels[i])}</div>` +
    (i < view.steps.length - 1 ? `<span class="step-arrow"></span>` : "")
  ).join("") : "";

  // 顶部只留进度条。开场态已经有居中的欢迎语了，不需要再放一个大标题。
  box.innerHTML =
    `<div class="trip-header" data-sticky-head>` +
      `<div class="process-flow">${steps}</div>` +
      `<div class="trip-cards">${tripCardsHTML()}</div>` +
    `</div>`;

  box.querySelectorAll(".trip-card").forEach((card) => {
    card.onclick = () => {
      const input = $("trip-input-hero") || $("trip-input");
      if (!input) return;
      input.value = card.dataset.q;
      sendTrip();
    };
  });

  // 正在跑的时候不要把示例卡片又亮出来
  tripCardsShow(!tripBusy);
  if (typeof syncStickyHeads === "function") syncStickyHeads();
}

// 开场页的示例卡片（顶部那三张）
function tripCardsHTML(){
  return TRIP_EXAMPLES.map((e) =>
    `<div class="trip-card" data-q="${esc(e.q)}"><h4>${esc(e.q)}</h4><p>${esc(e.meta)}</p></div>`
  ).join("");
}

function tripCardsShow(show){
  const box = $("trip-fixed");
  const cards = box && box.querySelector(".trip-cards");
  if (!cards) return;
  cards.style.display = show ? "" : "none";
  if (typeof syncStickyHeads === "function") syncStickyHeads();
}

function tripRenderQuickPrompts(){
  const box = $("trip-quick-hero");
  if (box){
    box.innerHTML = TRIP_QUICK_QUESTIONS.map((question) =>
      `<button class="prompt-btn trip-quick-btn" type="button">${esc(question)}</button>`
    ).join("");
  }

  document.querySelectorAll(".trip-quick-btn").forEach((button) => {
    button.onclick = () => {
      if (tripBusy) return;

      // 开场态用中间那个输入框，对话态用底部那个
      const input = tripHeroVisible() ? $("trip-input-hero") : $("trip-input");
      if (!input) return;

      input.value = button.textContent.trim();
      sendTrip();
    };
  });
}

// 输入框提示语（两个模式共用一个）
function tripRenderPlaceholder(){
  // 手机上输入框窄，长文案会被右侧发送按钮挡掉，换成短版
  const isNarrow = window.matchMedia("(max-width: 768px)").matches;
  const text = isNarrow ? "想去哪玩？或问从哪到哪怎么走" : TRIP_PLACEHOLDER;

  ["trip-input-hero", "trip-input"].forEach((id) => {
    const input = $(id);
    if (input) input.placeholder = text;
  });
}

// 开场页额外的内容（现在只有攻略的景点卡片墙）
function tripRenderHeroExtras(){
  if (typeof renderGuideCards === "function"){
    renderGuideCards();
    return;
  }

  const wall = $("trip-cardwall");
  if (wall) wall.innerHTML = "";
}


/* ===== 进度条状态 ===== */

function tripStepsReset(){
  const box = $("trip-fixed");
  if (!box) return;
  box.classList.remove("is-running");
  box.querySelectorAll(".process-step").forEach((el) => { el.dataset.state = "wait"; });
  box.querySelectorAll(".step-arrow").forEach((el) => el.classList.remove("is-active", "is-past"));
}

function tripStepSet(idx, state){
  const box = $("trip-fixed");
  if (!box || idx < 0) return;

  const steps = box.querySelectorAll(".process-step");
  const arrows = box.querySelectorAll(".step-arrow");

  steps.forEach((el, i) => {
    if (i < idx){
      if (state !== "wait" && el.dataset.state !== "done" && el.dataset.state !== "error"){
        el.dataset.state = "done";
      }
    }else if (i === idx){
      if (state !== "wait" || el.dataset.state === "wait") el.dataset.state = state;
    }else if (state !== "wait"){
      if (el.dataset.state !== "done") el.dataset.state = "wait";
    }
  });

  arrows.forEach((el, i) => {
    const from = steps[i] ? steps[i].dataset.state : "wait";
    const to = steps[i + 1] ? steps[i + 1].dataset.state : "wait";
    el.classList.toggle("is-past", from === "done" && to !== "wait");
    el.classList.toggle("is-active", from !== "done" && (from === "busy" || to === "busy"));
  });

  if (state !== "wait") box.classList.add("is-running");
}

function tripStepsFinish(hasError){
  const box = $("trip-fixed");
  if (!box) return;

  if (!hasError){
    box.querySelectorAll(".process-step").forEach((el) => { el.dataset.state = "done"; });
  }

  box.querySelectorAll(".step-arrow").forEach((el) => {
    el.classList.remove("is-active");
    el.classList.add("is-past");
  });
}

function tripStepsInterrupt(){
  const box = $("trip-fixed");
  if (!box) return;
  box.querySelectorAll(".process-step").forEach((el) => {
    if (el.dataset.state === "busy") el.dataset.state = "error";
  });
  box.querySelectorAll(".step-arrow").forEach((el) => el.classList.remove("is-active"));
}


/* ===== 内容区滚动 ===== */

function tripFeed(){
  return $("trip-feed");
}

function tripScroll(){
  const feed = tripFeed();
  if (feed) scrollDown(feed);
  tripScrollHintUpdate();
}

function tripScrollHintUpdate(){
  const feed = tripFeed();
  const btn = $("trip-scroll-btn");
  if (!feed || !btn) return;
  const gap = feed.scrollHeight - feed.scrollTop - feed.clientHeight;
  btn.style.display = gap > 200 ? "block" : "none";
}

let tripScrollBound = false;

function tripBindScrollHint(){
  const feed = tripFeed();
  const btn = $("trip-scroll-btn");
  if (!feed) return;

  if (!tripScrollBound){
    feed.addEventListener("scroll", tripScrollHintUpdate);
    tripScrollBound = true;
  }

  if (btn){
    btn.onclick = () => {
      feed.scrollTo({ top: feed.scrollHeight, behavior: "smooth" });
    };
  }

  tripScrollHintUpdate();
}


/* ===== 开场态 / 对话态 ===== */

function tripHeroVisible(){
  const hero = $("trip-hero");
  return !!hero && hero.style.display !== "none";
}

// 按当前时间给一句问候
function tripGreetingText(){
  const h = new Date().getHours();
  if (h >= 5 && h < 11) return "早上好，有什么我能帮你的吗？";
  if (h >= 11 && h < 13) return "中午好，有什么我能帮你的吗？";
  if (h >= 13 && h < 18) return "下午好，有什么我能帮你的吗？";
  if (h >= 18 && h < 23) return "晚上好，有什么我能帮你的吗？";
  return "夜深了，有什么我能帮你的吗？";
}

function tripRefreshGreeting(){
  const el = $("trip-greeting");
  if (el) el.textContent = tripGreetingText();
}

// 切到开场态：清空内容，输入框回到中间
function tripShowHero(focusInput = false){
  const hero = $("trip-hero");
  const pane = $("trip-chat-pane");
  const bottom = $("trip-bottom");

  if (hero) hero.style.display = "";
  if (pane) pane.style.display = "none";
  if (bottom) bottom.style.display = "none";

  const feed = tripFeed();
  if (feed) feed.innerHTML = "";

  tripRefreshGreeting();
  tripRenderPlaceholder();
  tripRenderQuickPrompts();
  tripRenderHeroExtras();

  if (focusInput){
    const input = $("trip-input-hero");
    if (input) input.focus();
  }
}

// 切到对话态：收起开场页，显示内容区和底部输入框
function tripShowChatPane(){
  const hero = $("trip-hero");
  const pane = $("trip-chat-pane");
  const bottom = $("trip-bottom");

  if (hero) hero.style.display = "none";
  if (pane) pane.style.display = "";
  if (bottom) bottom.style.display = "";

  const input = $("trip-input");
  if (input) input.focus();
}


/* ===== 出行记录（路线、攻略共用一个列表，靠 last_kind 打标签） ===== */

const TRIP_KIND_TAGS = {
  ROUTE: { cls: "route", text: "路线" },
  TRAVEL: { cls: "guide", text: "攻略" },
  CHAT: { cls: "chat", text: "问答" },
};

function tripKindTagHTML(kind){
  const tag = TRIP_KIND_TAGS[kind];
  if (!tag) return "";
  return `<span class="kind-tag ${tag.cls}">${tag.text}</span>`;
}

async function loadTripRecords(){
  const list = await getJson("/trip/list");
  if (Array.isArray(list)) tripRecords = list;
}

function rememberChatId(chatId, turn){
  const id = Number(chatId);
  if (!id) return;
  openChatId = id;
  if (turn) turn.dataset.chatId = String(id);

  const feed = tripFeed();
  if (feed){
    feed.querySelectorAll(".trip-turn").forEach((t) => {
      if (!t.dataset.chatId) t.dataset.chatId = String(id);
    });
  }

  renderTripHistory();
}

function renderTripHistory(){
  const box = $("history-trip");
  if (!box) return;

  // 标题行和图标按钮由 app.js 里共用的 renderHistoryTitle 统一处理
  renderHistoryTitle();

  // 切换列表内容时，先把已经不存在的勾选清掉，避免删完留下幽灵 id
  const aliveIds = new Set(tripRecords.map((r) => Number(r.id)));
  historyPicked = new Set([...historyPicked].filter((id) => aliveIds.has(id)));

  // 每一行：多选模式下前面出现圆形勾选圈；标题前带模式标签
  const rows = tripRecords.map((r) => {
    const opened = chatIsOnScreen(r.id);

    return `
    <div class="history-item${opened && !historySelectMode ? " active" : ""}" data-cid="${r.id}">
      ${pickDotHTML(r.id)}
      ${tripKindTagHTML(r.last_kind)}
      <span class="hi-title">${esc(r.title || "出行会话")}</span>
      <span class="del" title="删除这个出行会话" data-delchat="${r.id}">🗑</span>
    </div>`;
  }).join("");

  box.innerHTML = rows + selectBarHTML();

  // 多选模式下点整行不再打开会话，避免和勾选冲突
  box.querySelectorAll(".history-item").forEach((item) => {
    item.onclick = () => {
      if (historySelectMode) return;
      openTripChat(Number(item.dataset.cid));
    };
  });

  box.querySelectorAll(".del").forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      removeTripChat(Number(el.dataset.delchat));
    };
  });

  bindPickDots(box, renderTripHistory);
  bindSelectBar(
    box,
    tripRecords.length,
    () => { historyPicked = new Set(tripRecords.map((r) => Number(r.id))); },
    removeTripPicked,
    renderTripHistory,
  );
}

async function removeTripPicked(){
  const ids = [...historyPicked];
  if (!ids.length) return;

  if (!confirm(`确定删除选中的 ${ids.length} 个出行会话吗？\n\n这些会话的全部对话会一起删除，无法恢复。`)) {
    return;
  }

  const result = await getJson("/trip/delete-batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });

  if (!result){
    alert("批量删除失败：请确认后端已启动。");
    return;
  }

  // 从本地列表里移除，不等服务器重新拉一次
  tripRecords = tripRecords.filter((r) => !ids.includes(Number(r.id)));

  // 如果当前屏幕上的会话被删了，回到空白的新会话
  const onScreenId = currentOnScreenChatId();
  if (onScreenId !== null && ids.includes(onScreenId)){
    tripHistory = [];
    openChatId = null;
    tripIntro();
  }

  historyPicked.clear();
  historySelectMode = false;
  await loadTripRecords();
  renderTripHistory();
}

function currentOnScreenChatId(){
  const feed = tripFeed();
  if (!feed) return null;

  const turns = feed.querySelectorAll(".trip-turn");
  if (!turns.length) return null;

  const raw = turns[0].dataset.chatId;
  return raw ? Number(raw) : null;
}

function chatIsOnScreen(chatId){
  const feed = tripFeed();
  if (!feed) return false;

  const turns = feed.querySelectorAll(".trip-turn");
  if (!turns.length) return false;

  return Number(turns[0].dataset.chatId) === Number(chatId);
}

async function openTripChat(chatId){
  if (tripBusy){
    alert("正在规划中，等这一轮跑完再看历史会话。");
    return;
  }

  if (chatIsOnScreen(chatId)) return;

  const record = await getJson(`/trip/${chatId}`);
  if (!record) return;

  openChatId = Number(chatId);

  // 打开历史会话：进度条按第一轮真正办事的那种能力画
  const firstTripTurn = (record.turns || []).find((t) => t.turn_kind !== "CHAT");
  tripView = firstTripTurn && firstTripTurn.turn_kind === "ROUTE" ? "ROUTE" : "TRAVEL";
  tripRenderShell();
  tripCardsShow(false);
  tripStepsReset();

  // 打开历史会话 = 对话态
  tripShowChatPane();

  const feed = tripFeed();
  // 整段还原历史时暂停入场动画，渲染完再放开（理由见 app.js 的 renderChat）
  feed.classList.add("feed-rendering");
  feed.innerHTML = "";

  (record.turns || []).forEach((turnRec) => {
    renderStoredTurn(feed, turnRec);
  });

  tripScroll();
  requestAnimationFrame(() => feed.classList.remove("feed-rendering"));
  renderTripHistory();

  tripHistory = (record.turns || []).map((t) => t.user_query).filter(Boolean);
}

function renderStoredTurn(feed, turnRec){
  const turn = document.createElement("div");
  turn.className = "trip-turn";
  turn.dataset.chatId = String(openChatId);
  feed.appendChild(turn);

  appendTripUser(turn, turnRec.user_query || "");

  const ai = turnRec.ai_output || {};

  if (turnRec.turn_kind === "CHAT"){
    appendTripChat(ai.chat_reply || "", turn);
    return;
  }

  // 路线和攻略的段落不一样，按这一轮自己的类型取一张表
  const view = turnRec.turn_kind === "ROUTE" ? TRIP_VIEWS.ROUTE : TRIP_VIEWS.TRAVEL;
  if (!view) return;

  // 历史记录也渲染成连贯的一段：按顺序把四段拼起来，每段带小标题
  const flow = document.createElement("div");
  flow.className = "trip-flow";

  view.sections.forEach((sec) => {
    const text = ai[sec.key];
    if (!text) return;

    const made = makeTripBlock(sec.label);
    made.body.textContent = text;
    flow.appendChild(made.block);
  });

  if (flow.childNodes.length) turn.appendChild(flow);
}

async function removeTripChat(chatId){
  const record = tripRecords.find((r) => r.id === chatId);
  if (!record) return;

  if (!confirm(`确定删除出行会话「${record.title || "出行会话"}」吗？\n\n这个会话的全部对话会一起删除，无法恢复。`)) return;

  const result = await getJson(`/trip/${chatId}`, { method: "DELETE" });

  if (!result){
    alert("删除失败：请确认后端已启动。");
    return;
  }

  tripRecords = tripRecords.filter((r) => r.id !== chatId);

  if (chatIsOnScreen(chatId)){
    tripIntro();
    if (tripRecords.length) openTripChat(tripRecords[0].id);
    return;
  }

  renderTripHistory();
}


/* ===== 气泡与段落 ===== */

function tripTarget(target){
  return target || tripFeed();
}

function appendTripUser(target, text){
  const feed = tripTarget(target);
  if (!feed) return;

  const div = document.createElement("div");
  div.className = "trip-user-msg";
  div.innerHTML = `<b>${esc(text)}</b>`;
  feed.appendChild(div);
  tripScroll();
}

function appendTripChat(text, target){
  const feed = tripTarget(target);
  if (!feed) return;

  const div = document.createElement("div");
  div.className = "trip-chat";
  div.textContent = text;
  feed.appendChild(div);
  tripScroll();
}

function appendTripError(text, target){
  const feed = tripTarget(target);
  if (!feed) return;

  const div = document.createElement("div");
  div.className = "trip-err";
  div.textContent = text;
  feed.appendChild(div);
  tripScroll();
}

// 造一个「小标题 + 正文」的段。实时输出和历史记录都用它，保证两边长得一样。
function makeTripBlock(label){
  const block = document.createElement("div");
  block.className = "trip-block";

  const title = document.createElement("div");
  title.className = "trip-block-title";
  title.textContent = label;

  const body = document.createElement("div");
  body.className = "trip-block-body";

  block.appendChild(title);
  block.appendChild(body);

  return { block, body };
}

function createFlow(target){
  const feed = tripTarget(target);

  // 状态行：一行灰色小字，显示"正在做什么"。新状态会覆盖旧的，不进入正文。
  const statusLine = document.createElement("div");
  statusLine.className = "trip-status-line";
  feed.appendChild(statusLine);

  // 正文容器：四段内容按到达顺序写进来，读起来是一整篇文档
  const flow = document.createElement("div");
  flow.className = "trip-flow";
  feed.appendChild(flow);

  // 已经建好的段落。按 key 找标题，不依赖"当前是哪个模式"——
  // 同一轮里也可能既有路线的段、又有攻略的段
  const blocks = {};

  function ensureBlock(key){
    if (blocks[key]) return blocks[key];

    const label = TRIP_SECTION_LABELS[key] || key;
    const made = makeTripBlock(label);
    flow.appendChild(made.block);

    // 每段文字用独立的打字机，这样多段可以各自追加，互不干扰
    const typer = createTyper(feed, made.body);

    // 进度条只点亮"当前这一条能力"里有的那一步
    const view = tripView ? TRIP_VIEWS[tripView] : null;
    const idx = view ? view.steps.indexOf(key) : -1;
    if (idx >= 0) tripStepSet(idx, "busy");

    blocks[key] = { body: made.body, typer, idx };
    return blocks[key];
  }

  return {
    // 状态提示：覆盖上一句，让用户知道正在做什么
    status(text){
      if (!text) return;
      statusLine.textContent = text;
      statusLine.dataset.state = "running";
      tripScroll();
    },

    // 这轮结束：状态行换成结果，避免一直停在"正在理解你的需求"
    finish(text, failed){
      if (failed){
        statusLine.textContent = text || "已完成，但有错误";
        statusLine.dataset.state = "error";
      }else{
        statusLine.textContent = text || "已完成";
        statusLine.dataset.state = "done";
      }
      tripScroll();
    },

    // 逐字内容：第一次收到某个 key 的字，就先建出这一段
    token(key, text){
      if (!text) return;
      ensureBlock(key).typer.push(text);
    },

    // 定稿：用完整内容替换这一段，补齐流式过程中可能漏掉的字
    done(key, text){
      const part = ensureBlock(key);
      part.typer.cut();
      part.typer.renderFinal(text);

      // 行程和景点写完以后，把长文本整理成按天 / 按条的结构，方便阅读
      if (typeof tripDecorateBlock === "function"){
        tripDecorateBlock(key, part.body, text);
      }

      if (part.idx >= 0) tripStepSet(part.idx, "done");
      tripScroll();
    }
  };
}


/* ===== 长文本整理成结构 ===== */

// 把「Day 1｜11月16日｜阴 13~20°C」这种行当成分隔
const TRIP_DAY_RE = /^Day\s*\d+.*$/im;
const TRIP_SPOT_RE = /^\s*\d+[.、]\s*\S+/m;
// 天气段里「- 11月16日：小毛毛雨，……」或「- **11月16日**：阵雨，……」
const TRIP_WDAY_RE = /^\s*[-·]\s*\**\s*(\d{1,2}月\d{1,2}日|\d{4}-\d{2}-\d{2})\s*\**\s*[：:]\s*(.+)$/;

function tripDecorateBlock(key, body, text){
  if (!body || !text) return;

  try{
    if (key === "weather" && hasWeatherDays(text)){
      body.classList.add("is-structured");
      body.innerHTML = "";
      body.appendChild(buildWeatherBar(text));
      return;
    }

    if (key === "itinerary" && TRIP_DAY_RE.test(text)){
      body.classList.add("is-structured");
      body.innerHTML = "";
      body.appendChild(buildDayCards(text));
      return;
    }

    if (key === "spots" && TRIP_SPOT_RE.test(text)){
      body.classList.add("is-structured");
      body.innerHTML = "";
      body.appendChild(buildSpotCards(text));
      return;
    }

    // 游玩建议：把"要带的东西"抽成可勾选的清单，其余建议原样保留在下面
    if (key === "advice" && hasCheckItems(text)){
      body.classList.add("is-structured");
      body.innerHTML = "";
      body.appendChild(buildAdvice(text));
    }
  }catch(err){
    // 结构没解析成功就保持原来的文字，不要让内容消失
    console.warn("整理输出失败，保持原文", err);
    body.classList.remove("is-structured");
    body.textContent = text;
  }
}


function hasWeatherDays(text){
  return text.split("\n").filter((line) => TRIP_WDAY_RE.test(line)).length >= 2;
}


/* ===== 游玩建议：清单 + 原文 ===== */

// 哪些建议算"出发前要准备的东西"。从每一条里看关键词，
// 命中的抽成可勾选的清单项；没命中的保持原样。
const CHECK_WORDS = ["带", "备", "穿", "预约", "领", "确认", "携", "装", "伞", "鞋", "外套"];

function adviceLines(text){
  // 建议段一条一行，开头是「· 」或「- 」
  return text.split("\n")
    .map((l) => l.trim())
    .filter((l) => l.startsWith("·") || l.startsWith("-") || l.startsWith("*"))
    .map((l) => l.replace(/^[·\-\*]\s*/, "").trim())
    .filter(Boolean);
}

function hasCheckItems(text){
  // 只要有一条建议、并且其中至少一条提到"带/预约/穿"这类准备动作，就值得做清单
  const lines = adviceLines(text);
  if (!lines.length) return false;
  return lines.some((line) => CHECK_WORDS.some((w) => line.includes(w)));
}

function buildAdvice(text){
  const wrap = document.createElement("div");
  wrap.className = "trip-advice";

  const all = adviceLines(text);
  if (!all.length) throw new Error("没有可以分条的建议");

  // 只有"带东西、预约、穿什么"这几类才进清单。
  // 一条命中也照样做——总比一条都不做好，用户能勾掉已经准备好的。
  const checks = all.filter((line) => CHECK_WORDS.some((w) => line.includes(w)));

  if (checks.length === 0) throw new Error("没有能勾的建议");

  // 清单：只把关键动作提出来，短一点，长句子留在下面的原文里
  const list = document.createElement("div");
  list.className = "trip-checks";

  checks.forEach((line) => {
    const row = document.createElement("label");
    row.className = "trip-check";

    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = true;
    row.appendChild(box);

    const span = document.createElement("span");
    span.textContent = shortCheckItem(line);
    row.appendChild(span);

    list.appendChild(row);
  });

  const title = document.createElement("div");
  title.className = "trip-seg-title";
  title.textContent = "出发前清单";
  wrap.appendChild(title);
  wrap.appendChild(list);

  // 完整建议原样保留，一个字不删
  const restTitle = document.createElement("div");
  restTitle.className = "trip-seg-title";
  restTitle.textContent = "完整建议";
  wrap.appendChild(restTitle);

  const body = document.createElement("div");
  body.className = "trip-advice-text";
  body.textContent = all.map((l) => "· " + l).join("\n");
  wrap.appendChild(body);

  return wrap;
}


// 从一条建议里抠出一个短标签（十来个字），留给清单用
function shortCheckItem(line){
  // 取「：」前面那半句，没有就整句截短
  const beforeColon = line.split(/[：:]/)[0].trim();
  if (beforeColon.length > 4 && beforeColon.length < 24) return beforeColon;

  const cut = line.search(/[，。；、]/);
  const head = cut > 4 ? line.slice(0, cut) : line;
  return head.length > 22 ? head.slice(0, 22) + "…" : head;
}


// 天气：从「逐日要点」里抽出每天的日期和天气，做成横排天气条。
// 其余文字（整体趋势、出行建议、远期提醒）原样保留在下面，一个字不删。
function buildWeatherBar(text){
  const wrap = document.createElement("div");
  wrap.className = "trip-weather";

  const bar = document.createElement("div");
  bar.className = "trip-weather-bar";

  const rest = [];
  let found = 0;

  text.split("\n").forEach((line) => {
    const m = line.match(TRIP_WDAY_RE);
    if (!m){
      rest.push(line);
      return;
    }

    found += 1;

    const [, dateText, sentence] = m;
    const shortDate = dateText.replace(/^\d{4}-/, "").replace("/", "月").replace("-", "月");

    // 一句话里挑一个天气词当图标，挑不到就按第一个词
    const weatherWord = firstWeatherWord(sentence);

    const day = document.createElement("div");
    day.className = "trip-wday";

    const d = document.createElement("div");
    d.className = "trip-wday-date";
    d.textContent = shortDate;
    day.appendChild(d);

    const icon = document.createElement("div");
    icon.className = "trip-wday-icon";
    icon.textContent = weatherIcon(weatherWord);
    day.appendChild(icon);

    const w = document.createElement("div");
    w.className = "trip-wday-name";
    w.textContent = weatherWord;
    day.appendChild(w);

    bar.appendChild(day);

    // 这一行的完整内容还在下面那段文字里，不丢
  });

  if (!found) throw new Error("没有解析到逐日天气");

  wrap.appendChild(bar);

  // 剩下的文字（含逐日要点的完整句子）原样保留
  const tail = rest
    .join("\n")
    .replace(/\*\*/g, "")          // 去掉 markdown 加粗标记，纯文本更好读
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  if (tail){
    const body = document.createElement("div");
    body.className = "trip-weather-text";
    body.textContent = tail;
    wrap.appendChild(body);
  }

  return wrap;
}


// 从一句话里挑出天气词，用来配图标和短标签
function firstWeatherWord(sentence){
  const words = ["雷阵雨", "雷雨", "大暴雨", "暴雨", "大雨", "中雨", "小雨", "阵雨",
                 "毛毛雨", "小雪", "中雪", "大雪", "雨夹雪", "雪", "雾", "霾",
                 "晴转多云", "多云转晴", "多云", "阴转晴", "晴", "阴"];
  for (const word of words){
    if (sentence.includes(word)) return word;
  }
  return "未知";
}


// 天气状况 → 图标。按关键词猜，猜不到给 ☁️
function weatherIcon(text){
  const rules = [
    [["雷"], "⛈"],
    [["大雪", "中雪", "小雪", "雪"], "❄️"],
    [["大雨", "中雨", "暴雨"], "🌧"],
    [["雨"], "🌦"],
    [["雾", "霾"], "🌫"],
    [["晴"], "☀️"],
    [["多云"], "⛅"],
    [["阴"], "☁️"],
  ];
  for (const [words, icon] of rules){
    if (words.some((w) => text.includes(w))) return icon;
  }
  return "☁️";
}


// 行程：按 Day 拆成一张张卡片
function buildDayCards(text){
  const wrap = document.createElement("div");
  wrap.className = "trip-days";

  const lines = text.split("\n");
  const days = [];
  let current = null;

  lines.forEach((line) => {
    const trimmed = line.trim();

    if (/^Day\s*\d+/i.test(trimmed)){
      const parts = trimmed.split(/[｜|]/).map((x) => x.trim());
      current = { no: parts[0] || "", date: parts[1] || "", weather: parts[2] || "", rows: [] };
      days.push(current);
      return;
    }

    if (!current) return;
    if (!trimmed) return;

    // 「上午：西湖（约 3 小时）」这种行
    const row = trimmed.match(/^(上午|中午|下午|晚上|早上|白天)\s*[：:]\s*(.*)$/);
    if (row){
      let rest = row[2];

      // 模型有时会把整段总结塞进最后一行，把【…】开头的部分摘出来当说明
      const extraIndex = rest.search(/【[^】]{2,}】/);
      if (extraIndex > 20){
        const extra = rest.slice(extraIndex).trim();
        rest = rest.slice(0, extraIndex).trim();
        current.note = current.note ? current.note + " " + extra : extra;
      }

      const durMatch = rest.match(/（约?\s*[^（）]{1,12}?）$/);
      let place = durMatch ? rest.slice(0, rest.length - durMatch[0].length).trim() : rest;
      let dur = durMatch ? durMatch[0].replace(/[（）]/g, "") : "";

      // 单行太长说明混进了总结，把多出来的部分移到说明里
      if (place.length > 40){
        const cut = place.search(/[【。]/);
        if (cut > 6){
          const extra = place.slice(cut).trim();
          place = place.slice(0, cut).trim();
          current.note = current.note ? current.note + " " + extra : extra;
        }
      }

      current.rows.push({ slot: row[1], place, dur });
      return;
    }

    // 「今日提示：……」这类
    if (/^今日提示/.test(trimmed)){
      current.note = trimmed.replace(/^今日提示\s*[：:]\s*/, "");
      return;
    }

    // 没写时段、又特别长的行，多半是模型把总结塞进来了，挪到当日说明里
    if (current.rows.length && trimmed.length > 40){
      current.note = current.note ? current.note + " " + trimmed : trimmed;
      return;
    }

    if (current.rows.length) {
      const last = current.rows[current.rows.length - 1];
      last.place += " " + trimmed;
    }
  });

  const usable = days.filter((d) => d.rows.length);
  if (!usable.length) throw new Error("没有解析到每日安排");

  usable.forEach((day, index) => {
    const card = document.createElement("div");
    card.className = "trip-day";

    const head = document.createElement("div");
    head.className = "trip-day-head";

    const no = document.createElement("span");
    no.className = "trip-day-no";
    no.textContent = "D" + (index + 1);
    head.appendChild(no);

    if (day.date){
      const date = document.createElement("span");
      date.className = "trip-day-date";
      date.textContent = day.date;
      head.appendChild(date);
    }

    if (day.weather){
      const weather = document.createElement("span");
      weather.className = "trip-day-weather";
      weather.textContent = day.weather;
      head.appendChild(weather);
    }

    card.appendChild(head);

    // 横向时间线：上午 → 下午 → 晚上 横着排，中间用箭头连起来。
    // 屏幕窄的时候横向滚动，不会把一天挤成一大块竖排。
    const rows = document.createElement("div");
    rows.className = "trip-day-rows";

    day.rows.forEach((item, i) => {
      if (i > 0){
        const arrow = document.createElement("span");
        arrow.className = "trip-day-arrow";
        arrow.textContent = "→";
        rows.appendChild(arrow);
      }

      const row = document.createElement("div");
      row.className = "trip-day-row";

      const slot = document.createElement("span");
      slot.className = "trip-day-slot";
      slot.textContent = item.slot;
      row.appendChild(slot);

      const place = document.createElement("span");
      place.className = "trip-day-place";
      place.textContent = item.place;
      row.appendChild(place);

      if (item.dur){
        const dur = document.createElement("span");
        dur.className = "trip-day-dur";
        dur.textContent = item.dur;
        row.appendChild(dur);
      }

      rows.appendChild(row);
    });

    card.appendChild(rows);

    if (day.note){
      const note = document.createElement("div");
      note.className = "trip-day-note";
      note.textContent = day.note;
      card.appendChild(note);
    }

    wrap.appendChild(card);
  });

  return wrap;
}


// 景点：按编号拆成小卡
function buildSpotCards(text){
  const wrap = document.createElement("div");
  wrap.className = "trip-spots";

  // 先切掉「【游玩提示】」这类收尾段落，它不属于任何一个景点
  const tailMatch = text.search(/^\s*【[^】]{2,}】/m);
  const spotPart = tailMatch >= 0 ? text.slice(0, tailMatch) : text;
  const tailPart = tailMatch >= 0 ? text.slice(tailMatch).trim() : "";

  const chunks = spotPart.split(/\n(?=\s*\d+[.、]\s)/);

  const items = [];
  chunks.forEach((chunk) => {
    const match = chunk.match(/^\s*(\d+)[.、]\s*(.+)$/s);
    if (!match) return;

    const rest = match[2].trim();
    const firstLineEnd = rest.indexOf("\n");
    const titleLine = firstLineEnd >= 0 ? rest.slice(0, firstLineEnd).trim() : rest;
    const detail = firstLineEnd >= 0 ? rest.slice(firstLineEnd).trim() : "";

    const nameParts = titleLine.split(/\s*——\s*/);
    items.push({
      no: match[1],
      name: nameParts[0].trim(),
      tagline: nameParts[1] ? nameParts[1].trim() : "",
      detail,
    });
  });

  if (!items.length) throw new Error("没有解析到景点");

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "trip-spot";

    const head = document.createElement("div");
    head.className = "trip-spot-head";

    // 用 emoji 当图标：按名字里的关键词猜一个，猜不到给个通用的。
    // 这样做的好处是不会因为外链图片加载失败变成空白。
    const icon = document.createElement("span");
    icon.className = "trip-spot-icon";
    icon.textContent = spotIcon(item.name);
    head.appendChild(icon);

    const name = document.createElement("div");
    name.className = "trip-spot-name";
    name.textContent = item.name;
    head.appendChild(name);

    card.appendChild(head);

    if (item.tagline){
      const tagline = document.createElement("div");
      tagline.className = "trip-spot-tagline";
      tagline.textContent = item.tagline;
      card.appendChild(tagline);
    }

    if (item.detail){
      const detail = document.createElement("div");
      detail.className = "trip-spot-detail";
      detail.textContent = item.detail;
      card.appendChild(detail);
    }

    wrap.appendChild(card);
  });

  // 「【游玩提示】」那段整体放在卡片下面，内容不丢
  if (tailPart){
    const note = document.createElement("div");
    note.className = "trip-spot-note";
    note.textContent = tailPart;
    wrap.appendChild(note);
  }

  return wrap;
}


// 给景点配个图标。只按名字里的关键词猜，猜不到就用 📍。
// 不用真实图片：外链可能挂、也有版权问题，emoji 不会。
function spotIcon(name){
  const rules = [
    [["博物馆", "博物院", "美术馆", "展览"], "🏛"],
    [["寺", "庙", "塔", "宫", "观"], "🛕"],
    [["湖", "湿地", "江", "河", "海", "泉", "溪"], "🌊"],
    [["山", "峰", "岭", "谷"], "⛰"],
    [["园", "植物", "花"], "🌿"],
    [["街", "巷", "古镇", "老城", "市集"], "🏮"],
    [["科技", "科学"], "🔬"],
    [["动物", "动物园", "熊猫"], "🐼"],
    [["船", "游船"], "🚢"],
    [["城墙", "长城", "古城"], "🧱"],
    [["故居", "纪念"], "🏠"],
    [["茶"], "🍵"],
    [["美食", "小吃", "餐"], "🍜"],
  ];

  for (const [words, icon] of rules){
    if (words.some((w) => name.includes(w))) return icon;
  }
  return "📍";
}


/* ===== 计时 ===== */

// 整轮用时 = 从这一轮开始到现在的全部时间，扣掉中途等你选择的时间。
// 中途恢复时不重新计时，否则最后算出来的只有最后一段。
function tripSeconds(){
  if (!tripT0) return 0;
  const waiting = tripWaitStart ? Date.now() - tripWaitStart : 0;
  const used = Date.now() - tripT0 - tripWaitedTotal - waiting;
  return Math.max(0, Math.round(used / 1000));
}

function fmtSec(s){
  return s >= 60 ? `${Math.floor(s / 60)}分${String(s % 60).padStart(2, "0")}秒` : `${s} 秒`;
}

function tripClockStart(){
  tripT0 = Date.now();
  tripWaitedTotal = 0;
  tripWaitStart = 0;
  clearInterval(tripClock);

  const status = $("trip-status");
  tripClock = setInterval(() => {
    if (status) status.textContent = `规划中 ${tripSeconds()}s`;
  }, 1000);
}

function tripClockPause(){
  if (!tripT0 || tripWaitStart) return;

  tripWaitStart = Date.now();
  clearInterval(tripClock);
  tripClock = null;

  const status = $("trip-status");
  if (status) status.textContent = "等待选择";
}

function tripClockResume(){
  if (!tripT0 || !tripWaitStart) return;

  tripWaitedTotal += Date.now() - tripWaitStart;
  tripWaitStart = 0;

  clearInterval(tripClock);
  tripClock = setInterval(() => {
    const status = $("trip-status");
    if (status) status.textContent = `规划中 ${tripSeconds()}s`;
  }, 1000);
}

function tripClockStop(finalText){
  clearInterval(tripClock);
  tripClock = null;

  const status = $("trip-status");
  if (status) status.textContent = finalText || "TRIP AGENT";

  tripT0 = 0;
  tripWaitedTotal = 0;
  tripWaitStart = 0;
}


/* ===== 发送按钮状态 ===== */

function setTripSendState(state){
  document.querySelectorAll(".trip-send-btn").forEach((btn) => {
    btn.classList.toggle("is-stop", state === "stop");
    btn.classList.toggle("is-retry", state === "retry");
    btn.textContent = state === "stop" ? "■" : state === "retry" ? "↻" : "➤";
    btn.title = state === "stop" ? "停止生成" : state === "retry" ? "重试上一条" : "发送";
  });
}

function tripSendOrStop(){
  if (tripBusy){
    abortCurrent();
    return;
  }

  const input = tripHeroVisible() ? $("trip-input-hero") : $("trip-input");
  if (input && input.value.trim()){
    sendTrip();
    return;
  }

  if (tripCanRetry) retryTrip();
  else sendTrip();
}

function retryTrip(){
  const input = tripHeroVisible() ? $("trip-input-hero") : $("trip-input");
  if (!input || tripBusy || !lastTripText) return;

  input.value = lastTripText;
  sendTrip();
}


/* ===== 等待面板（两种能力共用） ===== */

// 加一行"我在等你"的提示，让等待状态更明显
function showWaitingHint(turn, text){
  if (!turn) return;
  if (turn.querySelector(".route-ask-hint")) return;

  const hint = document.createElement("div");
  hint.className = "route-ask-hint";
  hint.textContent = text || "流程已暂停，等你选一个方案 ↑";
  turn.appendChild(hint);
}

// 切到下一个等待面板之前，先把上一轮的面板和提示清掉
function clearWaitingPanels(turn){
  const scope = turn || document;
  scope.querySelectorAll(".route-ask").forEach((panel) => panel.remove());
  scope.querySelectorAll(".route-ask-hint").forEach((hint) => hint.remove());
}

// 不同面板给不同的等待提示，说清楚现在在等什么
function hintTextFor(kind){
  if (kind === "spots") return "流程已暂停，勾完点「就这样，继续排行程」 ↑";
  return "流程已暂停，等你选一个方案 ↑";
}

// 把内容区滚到选方案面板的位置，保证用户第一眼能看到按钮
function scrollToWaitingPanel(){
  const feed = tripFeed();
  const panel = document.querySelector(".route-ask");
  if (!feed || !panel) return;

  feed.scrollTo({ top: panel.offsetTop - 12, behavior: "smooth" });
}

// 新一轮开始前，把上一轮没选完的面板锁掉，避免点了串到新对话里
function lockRoutePanels(){
  document.querySelectorAll(".route-ask").forEach((panel) => {
    panel.classList.add("is-locked");
    panel.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  });
}


/* ===== 一轮对话：发出去，边收边渲染 ===== */

// 这一轮走的是哪条能力：重画进度条。用户看不到"模式"，只看到进度条变了
function tripApplyView(mode){
  if (!mode || !TRIP_VIEWS[mode]) return;
  if (mode === tripView) return;

  tripView = mode;
  tripRenderShell();
  tripStepsReset();
}

function tripHandleEvent(ev, ctx){
  const { turn, flow } = ctx;

  switch (ev.kind){
    case "SAY":
      ctx.touched = true;
      flow.status(ev.text);
      break;

    case "START":
      ctx.touched = true;
      // 这一轮走的是哪条能力：只决定进度条画什么，用户不需要选
      tripApplyView(ev.mode);
      tripStepSet(0, "busy");
      break;

    case "STEP": {
      const view = tripView ? TRIP_VIEWS[tripView] : null;
      const idx = view ? view.steps.indexOf(ev.key) : -1;
      if (idx >= 0){ ctx.touched = true; tripStepSet(idx, "busy"); }
      flow.status(ev.text);
      break;
    }

    case "TOKEN":
      ctx.touched = true;
      flow.token(ev.key, ev.text);
      break;

    case "DONE":
      ctx.touched = true;
      flow.done(ev.key, ev.text);
      break;

    case "CHAT":
      ctx.chatTurn = true;
      if (ev.chat_id) rememberChatId(ev.chat_id, turn);
      appendTripChat(ev.message || "", turn);
      break;

    case "SAVED":
      if (ev.chat_id) rememberChatId(ev.chat_id, turn);
      break;

    case "ERROR":
      ctx.stepError = 0;
      appendTripError(ev.message || "出行模块出错了", turn);
      break;

    // 下面是两种能力各自的等待面板。
    // 不用再问"现在是哪个模式"：事件本身就是线索。
    case "ASK":
      ctx.touched = true;
      ctx.awaitingChoice = true;
      clearWaitingPanels(turn);
      showRouteChoices(turn, flow, ev);
      flow.status("查到了候选路线，在下面点一个方案，我再继续写推荐");
      break;

    case "ASK_PLACE":
      ctx.touched = true;
      ctx.awaitingChoice = true;
      clearWaitingPanels(turn);
      if (ev.chat_id) rememberChatId(ev.chat_id, turn);
      showPlaceChoices(turn, flow, ev);
      flow.status("地点没认准，点一个候选就行");
      break;

    case "ASK_SPOTS":
      ctx.touched = true;
      ctx.awaitingChoice = true;
      clearWaitingPanels(turn);
      showSpotChoices(turn, flow, ev);
      flow.status("景点清单出来了，勾掉不想要的，或者在下面补一个");
      break;

    default:
      break;
  }
}

// 读流并按事件回调。sendTrip 和"接着跑"的请求都用它
async function tripStream(url, body, onEvent){
  const ctl = newAbortController();

  try{
    const res = await fetch(API.base + url, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json", "Accept": "text/event-stream" }),
      body: JSON.stringify(body),
      signal: ctl.signal
    });

    if (res.status === 401){
      handleAuthExpired();
      throw new Error("登录已过期，请重新登录");
    }

    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    if (!res.body) throw new Error("当前浏览器不支持流式读取（res.body 为空）");

    const parser = createSseParser(onEvent);
    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");

    while (true){
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      parser.push(decoder.decode(value, { stream: true }));
    }

    parser.push(decoder.decode());
    parser.end();
    return { failed: null, aborted: false };
  }catch(err){
    if (err && err.name === "AbortError"){
      return { failed: null, aborted: true };
    }
    return { failed: err, aborted: false };
  }finally{
    finishAbort(ctl);
  }
}


async function sendTrip(){
  // 两个输入框：开场态用中间那个，对话态用底部那个
  const heroInput = $("trip-input-hero");
  const bottomInput = $("trip-input");
  const input = tripHeroVisible() ? heroInput : bottomInput;
  const feed = tripFeed();
  if (!input || !feed || tripBusy) return;

  const text = input.value.trim();
  if (!text) return;

  // 等访客会话就绪再发，避免页面刚打开时抢跑
  if (!(await ensureSession(false))){
    appendNotice(feed, "会话还没准备好，请刷新页面重试");
    return;
  }

  tripBusy = true;
  activeTripId = null;
  input.value = "";
  lastTripText = text;
  tripCanRetry = false;
  setTripSendState("stop");

  // 之前如果有没选完的面板，先把旧按钮锁掉，避免点了串到新对话里
  lockRoutePanels();

  // 从开场态切到对话态：输入框落到下方，内容区显示出来
  tripShowChatPane();

  tripCardsShow(false);
  tripStepsReset();

  // 兜底：没有打开任何会话时，历史必须是空的。
  // 万一别处的逻辑又把旧对话塞了进来，这里直接清掉，
  // 保证新会话的第一句话不会被旧城市带偏。
  if (openChatId == null){
    tripHistory = [];
  }

  // 新一轮开始时，把上一个没选完的面板撤掉。
  // 不然它会一直占着页面，用户以为还在等，其实已经过了
  document.querySelectorAll(".route-ask").forEach((panel) => panel.remove());

  const turn = document.createElement("div");
  turn.className = "trip-turn";
  turn.dataset.chatId = openChatId == null ? "" : String(openChatId);
  feed.appendChild(turn);
  appendTripUser(turn, text);

  tripClockStart();

  const flow = createFlow(turn);
  const ctx = { turn, flow, touched: false, chatTurn: false, awaitingChoice: false, stepError: -1 };

  const result = await tripStream(
    TRIP_ENDPOINT,
    { query: text, history: tripHistory, chat_id: openChatId },
    (ev) => tripHandleEvent(ev, ctx),
  );

  // 发出去了才记进历史，失败的那句不留在上下文里
  if (!result.failed && !result.aborted) tripHistory.push(text);

  tripBusy = false;

  if (result.failed || result.aborted){
    tripCanRetry = true;
    setTripSendState(input.value.trim() ? "send" : "retry");
    if (result.failed){
      appendTripError(
        "请求失败：" + (result.failed.message ? result.failed.message : result.failed) +
        "\n请确认后端已启动。", turn);
    }
  }else{
    tripCanRetry = false;
    setTripSendState("send");
  }

  if (!result.failed && ctx.stepError < 0 && ctx.touched && !ctx.chatTurn
      && !ctx.awaitingChoice && !result.aborted){
    tripStepsFinish(false);
  }else if (result.failed || ctx.stepError >= 0 || result.aborted){
    tripStepsInterrupt();
  }

  // 状态行收尾：如果停在等选择 / 等转场，就暂停计时，等用户选完再接着算
  if (ctx.awaitingChoice && !result.aborted){
    tripClockPause();
  }else if (result.aborted){
    tripClockStop("已停止");
    flow.finish("已停止，可重试", true);
  }else{
    const usedText = `用时 ${fmtSec(tripSeconds())}`;
    tripClockStop(result.failed ? "FAILED" : usedText);

    if (ctx.chatTurn){
      flow.finish("CTOS任务完成", false);
    }else if (result.failed || ctx.stepError >= 0){
      flow.finish("CTOS任务失败", true);
    }else if (ctx.touched){
      flow.finish(`CTOS规划结束 · ${usedText}`, false);
    }
  }

  tripScroll();
  if (ctx.awaitingChoice) scrollToWaitingPanel();

  await loadTripRecords();
  if (state.view === "trip") renderTripHistory();

  const inp = $("trip-input");
  if (inp) inp.focus();
}


/* ===== 空态与初始化 ===== */

function tripIntro(){
  // 新会话回到"还没决定走哪条能力"的状态：进度条先空着，
  // 用户说第一句话、收到 START 之后再画
  tripView = null;
  tripRenderShell();
  tripStepsReset();
  tripCardsShow(true);
  activeTripId = null;
  tripClockStop();

  if (!tripBusy){
    lastTripText = "";
    tripCanRetry = false;
    setTripSendState("send");
  }

  const btn = $("trip-scroll-btn");
  if (btn) btn.style.display = "none";

  // 空白会话 = 开场态
  tripShowHero();

  if (state.view === "trip") renderTripHistory();
}

function tripNewSession(){
  // 立刻清空，不要放到 setTimeout 里。
  // 之前延迟 300 毫秒，用户点完马上打字的话，历史还没清就被发出去了，
  // 新会话里会带上旧对话，模型就会说出上一个城市。
  abortCurrent();
  tripBusy = false;
  lastTripText = "";
  tripCanRetry = false;
  setTripSendState("send");
  tripHistory = [];
  openChatId = null;

  // 新会话只清当前对话的上下文，不能清历史列表。
  // 清掉的话左栏会先变空，等别的操作重新拉取才回来。
  tripIntro();

  // 用户主动开新会话，把光标放到输入框里
  tripShowHero(true);

  if (state.view === "trip") renderTripHistory();
}

// 换账号登录时清掉列表缓存，别带着上一个人的出行记录
function tripClearRecords(){
  tripRecords = [];
  if (state.view === "trip") renderTripHistory();
}

function tripInit(){
  tripRenderShell();
  tripRenderPlaceholder();
  tripRenderQuickPrompts();
  setTripSendState("send");

  // 停止/出错后按钮变成"重试"，用户一打字就变回"发送"
  ["trip-input", "trip-input-hero"].forEach((id) => {
    const input = $(id);
    if (!input) return;
    input.oninput = () => {
      if (tripBusy) return;
      setTripSendState(input.value.trim() ? "send" : (tripCanRetry ? "retry" : "send"));
    };
  });

  const feed = tripFeed();
  if (feed) feed.innerHTML = "";

  tripStepsReset();
  tripBindScrollHint();

  // 初始化时一律从空白新会话开始，不自动打开最近的会话。
  // 以前这里会自动打开第一条记录并读进 tripHistory，
  // 结果刷新页面或切回出行模块后，明明是新对话却带着旧历史。
  tripHistory = [];
  openChatId = null;

  // 进开场态。顺带把问候语换成当前时间对应的那句话，
  // 不然页面上会一直是 HTML 里写死的那句"你好"。
  tripShowHero();

  loadTripRecords().then(() => {
    if (state.view === "trip") renderTripHistory();
  });
}
