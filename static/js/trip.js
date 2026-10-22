const TRIP_SECTIONS = [
  { key: "weather",    label: "天气" },
  { key: "spots",      label: "景点推荐" },
  { key: "itinerary",  label: "行程安排" },
  { key: "route_plan", label: "详细路线" }
];

const STEP_KEYS = ["weather", "spots", "itinerary", "route_plan"];
const FLOW_LABELS = ["查询天气", "推荐景点", "安排行程", "规划路线"];

const TRIP_EXAMPLES = [
  { q: "下周想去杭州玩3天，带老人", meta: "3 天 · 带老人 · 雨天偏好室内" },
  { q: "成都4天，带小孩",           meta: "4 天 · 带小孩 · 节奏放缓" },
  { q: "三亚周末游，两个人",         meta: "2 天 · 情侣 · 看海为主" }
];

let tripBusy = false;
let tripHistory = [];
let tripRecords = [];
let activeTripId = null;

let tripT0 = 0;
let tripClock = null;


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

function tripRenderShell(){
  const box = $("trip-fixed");
  if (!box) return;

  const steps = STEP_KEYS.map((key, i) =>
    `<div class="process-step" data-step="${key}" data-state="wait">` +
    `<span class="step-num">${String(i + 1).padStart(2, "0")}</span> ${esc(FLOW_LABELS[i])}</div>` +
    (i < STEP_KEYS.length - 1 ? `<span class="step-arrow"></span>` : "")
  ).join("");

  box.innerHTML =
    `<div class="trip-header" data-sticky-head>` +
      `<h2>输入您的目的地，ctOS 将为您规划</h2>` +
      `<div class="process-flow">${steps}</div>` +
      `<div class="trip-cards">${tripCardsHTML()}</div>` +
    `</div>`;

  box.querySelectorAll(".trip-card").forEach((card) => {
    card.onclick = () => {
      const input = $("trip-input");
      if (!input) return;
      input.value = card.dataset.q;
      sendTrip();
    };
  });

  if (typeof syncStickyHeads === "function") syncStickyHeads();
}

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

function tripIntro(){
  tripRenderShell();

  const feed = tripFeed();
  if (feed) feed.innerHTML = "";

  tripStepsReset();
  tripCardsShow(true);
  activeTripId = null;
  tripClockStop();

  const btn = $("trip-scroll-btn");
  if (btn) btn.style.display = "none";

  if (state.view === "trip") renderTripHistory();
}


async function loadTripRecords(){
  const list = await getJson("/trip/list");
  if (Array.isArray(list)) tripRecords = list;
}

let openChatId = null;

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

  if (!tripRecords.length){
    box.innerHTML = `<div class="empty-history">还没有出行记录。<br>在上面说一句「想去哪儿玩」，规划完就会存进来。</div>`;
    return;
  }

  box.innerHTML = tripRecords.map((r) => {
    const opened = chatIsOnScreen(r.id);
    return `
    <div class="history-item${opened ? " active" : ""}" data-cid="${r.id}">
      <span class="hi-title">${esc(r.title || "出行会话")}</span>
      <span class="del" title="删除这个出行会话" data-delchat="${r.id}">🗑</span>
    </div>`;
  }).join("");

  box.querySelectorAll(".history-item").forEach((item) => {
    item.onclick = () => openTripChat(Number(item.dataset.cid));
  });

  box.querySelectorAll(".del").forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      removeTripChat(Number(el.dataset.delchat));
    };
  });
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
  tripCardsShow(false);
  tripStepsReset();

  const feed = tripFeed();
  feed.innerHTML = "";

  (record.turns || []).forEach((turnRec) => {
    renderStoredTurn(feed, turnRec);
  });

  tripScroll();
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

  const wrap = document.createElement("div");
  wrap.className = "trip-secs";

  TRIP_SECTIONS.forEach((sec) => {
    const text = ai[sec.key];
    if (!text) return;

    const el = document.createElement("div");
    el.className = "trip-sec";
    el.dataset.sec = sec.key;
    el.dataset.state = "done";
    el.innerHTML =
      `<div class="sec-head"><span class="dot"></span><span>${esc(sec.label)}</span>` +
      `<span class="sec-state">已完成</span></div>` +
      `<div class="sec-body">${esc(text)}</div>`;
    wrap.appendChild(el);
  });

  if (wrap.childNodes.length) turn.appendChild(wrap);
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


function createSections(target){
  const feed = tripTarget(target);
  const wrap = document.createElement("div");
  wrap.className = "trip-secs";
  feed.appendChild(wrap);

  const parts = {};

  function stepIndex(key){
    const i = STEP_KEYS.indexOf(key);
    return i < 0 ? -1 : i;
  }

  function ensure(key){
    if (parts[key]) return parts[key];

    const idx = stepIndex(key);
    const meta = TRIP_SECTIONS.find((s) => s.key === key) || { key, label: key };

    const el = document.createElement("div");
    el.className = "trip-sec";
    el.dataset.sec = key;
    el.dataset.state = "busy";
    el.innerHTML =
      `<div class="sec-head"><span class="dot"></span><span>${esc(meta.label)}</span>` +
      `<span class="sec-state">进行中</span></div>` +
      `<div class="sec-body"></div>`;
    wrap.appendChild(el);

    const body = el.querySelector(".sec-body");

    const hint = document.createElement("div");
    hint.className = "trip-step";
    body.appendChild(hint);

    const typer = createTyper(feed, body);

    parts[key] = { el, body, hint, typer, idx };
    tripStepSet(idx, "busy");
    return parts[key];
  }

  function setState(key, s, note){
    const p = parts[key];
    if (!p) return;
    p.el.dataset.state = s;
    const st = p.el.querySelector(".sec-state");
    if (st) st.textContent = note;
  }

  return {
    step(key, text){
      const p = ensure(key);
      if (!p.typer.untouched()){ setState(key, "busy", "进行中"); return; }
      p.hint.textContent = text;
      setState(key, "busy", "进行中");
      tripScroll();
    },
    token(key, text){
      const p = ensure(key);
      if (!text) return;
      p.typer.push(text);
      setState(key, "busy", "进行中");
    },
    done(key, text){
      const p = ensure(key);
      p.typer.cut();
      p.typer.renderFinal(text);
      setState(key, "done", "已完成");
      tripStepSet(p.idx, "done");
      tripScroll();
    }
  };
}


function tripSeconds(){
  if (!tripT0) return 0;
  return Math.max(0, Math.round((Date.now() - tripT0) / 1000));
}

function fmtSec(s){
  return s >= 60 ? `${Math.floor(s / 60)}分${String(s % 60).padStart(2, "0")}秒` : `${s} 秒`;
}

function tripClockStart(){
  tripT0 = Date.now();
  clearInterval(tripClock);

  const status = $("trip-status");
  tripClock = setInterval(() => {
    if (status) status.textContent = `规划中 ${tripSeconds()}s`;
  }, 1000);
}

function tripClockStop(finalText){
  clearInterval(tripClock);
  tripClock = null;

  const status = $("trip-status");
  if (status) status.textContent = finalText || "TRIP AGENT";
}


async function sendTrip(){
  const input = $("trip-input");
  const feed = tripFeed();
  if (!input || !feed || tripBusy) return;

  const text = input.value.trim();
  if (!text) return;

  tripBusy = true;
  activeTripId = null;
  input.value = "";

  tripCardsShow(false);
  tripStepsReset();

  const turn = document.createElement("div");
  turn.className = "trip-turn";
  turn.dataset.chatId = openChatId == null ? "" : String(openChatId);
  feed.appendChild(turn);
  appendTripUser(turn, text);

  tripClockStart();

  const sections = createSections(turn);
  const ctl = newAbortController();

  let failed = null;
  let chatTurn = false;
  let touched = false;
  let stepError = -1;

  try{
    const res = await fetch(API.base + "/trip/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
      body: JSON.stringify({ query: text, history: tripHistory, chat_id: openChatId }),
      signal: ctl.signal
    });

    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    if (!res.body) throw new Error("当前浏览器不支持流式读取（res.body 为空）");

    tripHistory.push(text);

    const parser = createSseParser((ev) => {
      switch (ev.kind){
        case "START":
          touched = true;
          tripStepSet(0, "busy");
          break;

        case "STEP": {
          const idx = STEP_KEYS.indexOf(ev.key);
          if (idx >= 0){ touched = true; tripStepSet(idx, "busy"); }
          sections.step(ev.key, ev.text);
          break;
        }

        case "TOKEN":
          touched = true;
          sections.token(ev.key, ev.text);
          break;

        case "DONE":
          touched = true;
          sections.done(ev.key, ev.text);
          break;

        case "CHAT":
          chatTurn = true;
          if (ev.chat_id) rememberChatId(ev.chat_id, turn);
          appendTripChat(ev.message || "", turn);
          break;

        case "SAVED":
          if (ev.chat_id) rememberChatId(ev.chat_id, turn);
          break;

        case "ERROR": {
          stepError = 0;
          appendTripError(ev.message || "出行模块出错了", turn);
          break;
        }
      }
    });

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
  }catch(err){
    if (!(err && err.name === "AbortError")){
      failed = err;
      appendTripError(
        "请求失败：" + (err && err.message ? err.message : err) +
        "\n请确认后端已启动：python src/ctOS_chat_api.py", turn);
    }
  }finally{
    finishAbort(ctl);
    tripBusy = false;
    tripClockStop(failed ? "FAILED" : `用时 ${fmtSec(tripSeconds())}`);

    if (!failed && stepError < 0 && touched && !chatTurn) tripStepsFinish(false);
    else if (failed || stepError >= 0) tripStepsInterrupt();

    tripScroll();

    await loadTripRecords();
    if (state.view === "trip") renderTripHistory();

    const inp = $("trip-input");
    if (inp) inp.focus();
  }
}


function tripNewSession(){
  setTimeout(() => {
    if (state.view !== "trip") return;
    abortCurrent();
    tripBusy = false;
    tripHistory = [];
    openChatId = null;
    tripIntro();
  }, 300);
}

function tripInit(){
  tripRenderShell();

  const feed = tripFeed();
  if (feed) feed.innerHTML = "";

  tripStepsReset();
  tripBindScrollHint();
  openChatId = null;

  loadTripRecords().then(() => {
    if (state.view === "trip") renderTripHistory();
    if (tripRecords.length) openTripChat(tripRecords[0].id);
  });
}
