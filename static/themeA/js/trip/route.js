/* 出行｜路线规划的界面：从 A 到 B 怎么走
 *
 * 做什么：多方案对比、人工选一条、写推荐和提醒的等待面板。
 * 谁在用：base.js 的 tripHandleEvent 收到事件时调用这些函数。
 *
 * 这里放的是这两个面板：
 *   ASK_PLACE  地点没认准，让用户从候选里挑一个
 *   ASK        候选路线出来了，让用户选一条
 *
 * 注意：这里已经没有"模式"的概念了。用户不选，Agent 判断；
 *       这些函数只是在事件到达时把对应的面板画出来。
 */


/* ===== 地点歧义 ===== */

// 地点认不准时弹出候选：点一个就把这句改写后重新发
function showPlaceChoices(turn, flow, event){
  const panel = document.createElement("div");
  panel.className = "route-ask spot-ask";

  const question = document.createElement("div");
  question.className = "route-ask-question";
  question.textContent = event.question || "你指的是下面哪个地点？";
  panel.appendChild(question);

  const optionsBox = document.createElement("div");
  optionsBox.className = "route-options";

  (event.options || []).forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "route-option";

    const label = document.createElement("span");
    label.className = "ro-label";
    label.textContent = option.label || "";

    button.appendChild(label);

    if (option.note){
      const note = document.createElement("span");
      note.className = "ro-note";
      note.textContent = option.note;
      button.appendChild(note);
    }

    button.onclick = () => pickPlace(event, option, panel);
    optionsBox.appendChild(button);
  });

  panel.appendChild(optionsBox);

  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "route-ask-reset";
  reset.textContent = "都不是，我重新说";
  reset.onclick = () => {
    panel.remove();
    const input = $("trip-input");
    if (input) input.focus();
  };
  panel.appendChild(reset);

  turn.appendChild(panel);
  showWaitingHint(turn, "点一个地点，我接着查路线 ↑");
  tripScroll();
  scrollToWaitingPanel();
}

// 从候选里挑了一个地点：带着 thread_id 和这个地点，从原来那份需求接着跑。
//
// 为什么不再"改写原话重新发"：
//   以前是把选中的名字替换进原话，再发给 /trip/chat 重新走一遍 Agent + 解析。
//   那样会重新解析、重新判断，Agent 还可能再把名字改写回去，绕来绕去。
//   现在后端在发 ASK_PLACE 时就把这份需求存进了检查点，
//   这里只要说"我选的是哪个"。
function pickPlace(event, option, panel){
  if (tripBusy) return;

  const placeName = (option.label || "").trim();
  if (!placeName) return;

  // 旧面板、旧提示一起清掉，不留残影
  const turn = panel.closest(".trip-turn");
  panel.remove();
  if (turn){
    turn.querySelectorAll(".route-ask-hint").forEach((hint) => hint.remove());
    turn.querySelectorAll(".route-ask").forEach((item) => item.remove());
    // "地点没认准"这类过程状态行，在真正开始查时换成新的，别留在中间
    turn.querySelectorAll(".trip-status-line").forEach((line) => line.remove());
  }

  // 没有 thread_id（老版本或后端没存成功）：退回改写原话重发
  if (!event.thread_id){
    const asked = event.name || "";
    let query = lastTripText || "";
    if (asked && lastTripText.includes(asked)){
      query = lastTripText.split(asked).join(placeName);
    }
    resumeInTurn(turn, query);
    return;
  }

  resumePlace(turn, event.thread_id, placeName);
}

// 在已有的一轮里继续跑，用户看不到新的气泡
async function resumeInTurn(turn, text){
  const feed = tripFeed();
  if (!turn || !feed || tripBusy) return;

  const result = await tripRunInTurn(
    turn,
    TRIP_ENDPOINT,
    { query: text, history: tripHistory, chat_id: openChatId },
  );

  if (!result.failed && !result.aborted) tripHistory.push(text);
}

// 地点选完之后接着跑：把选中的地点交给后端，从原来那份需求继续
async function resumePlace(turn, threadId, placeName){
  const feed = tripFeed();
  if (!turn || !feed || tripBusy) return;

  // 不往 tripHistory 里塞这句——用户没说新的一句话，
  // 这只是点了个候选，塞进去会把上下文搞乱
  await tripRunInTurn(
    turn,
    "/trip/route/place",
    { thread_id: threadId, place: placeName },
  );
}

// 在原轮继续跑的那套收尾，两种续跑共用
async function tripRunInTurn(turn, url, body){
  const feed = tripFeed();
  if (!turn || !feed || tripBusy) return { failed: null, aborted: false };

  tripBusy = true;
  tripCanRetry = false;
  setTripSendState("stop");
  tripStepsReset();
  tripClockStart();

  const flow = createFlow(turn);
  const ctx = { turn, flow, touched: false, chatTurn: false, awaitingChoice: false, stepError: -1 };

  const result = await tripStream(url, body, (ev) => tripHandleEvent(ev, ctx));

  tripBusy = false;

  if (result.failed || result.aborted){
    tripCanRetry = true;
    setTripSendState("retry");
    if (result.failed){
      appendTripError(
        "请求失败：" + (result.failed.message ? result.failed.message : result.failed), turn);
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

  const input = $("trip-input");
  if (input) input.focus();

  return result;
}


/* ===== 候选路线 ===== */

// 方案对比表：只放能横向对齐的数（用时/距离/费用/步行/换乘）。
// 红绿灯、路况、线路这些放在卡片和对比文字里，这里不重复。
function buildCompareTable(event){
  const rows = (event.options || []).filter((o) => o.row);
  if (rows.length < 2) return null;   // 只有一条没什么好比

  const wrap = document.createElement("div");
  wrap.className = "route-table-wrap";

  const table = document.createElement("table");
  table.className = "route-table";

  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  ["方式", "用时", "距离", "费用", "步行", "换乘"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((option) => {
    const best = option.id === event.recommended_id;
    const tr = document.createElement("tr");
    if (best) tr.className = "is-best";

    const row = option.row;
    const first = document.createElement("td");
    // 推荐那条前面加个星，和卡片上的"系统推荐"对应
    first.textContent = (best ? "★ " : "") + (row.name || option.name || "");
    if (best) first.className = "is-pick";
    tr.appendChild(first);

    ["minutes", "distance", "cost", "walk", "transfer"].forEach((key) => {
      const td = document.createElement("td");
      td.className = "num";
      td.textContent = row[key] || "—";
      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  wrap.appendChild(table);
  return wrap;
}


function showRouteChoices(turn, flow, event){
  const panel = document.createElement("div");
  panel.className = "route-ask route-cards-ask";

  const head = document.createElement("div");
  head.className = "rc-head";

  const question = document.createElement("div");
  question.className = "route-ask-question";
  question.textContent = event.question || "你想按哪条路线走？";
  head.appendChild(question);

  if (event.recommended_text){
    const recommend = document.createElement("div");
    recommend.className = "route-ask-recommend";
    recommend.textContent = event.recommended_text;
    head.appendChild(recommend);
  }

  panel.appendChild(head);

  // 先摆一张对比表：几个数横着对齐，一眼能比。
  // 卡片和完整文字照旧在下面，表格只是"索引"，不替代内容。
  const table = buildCompareTable(event);
  if (table) panel.appendChild(table);

  const optionsBox = document.createElement("div");
  optionsBox.className = "route-card-grid";

  (event.options || []).forEach((option, index) => {
    const best = option.id === event.recommended_id;
    const card = option.card || {};
    const item = document.createElement("div");
    item.className = "route-card" + (best ? " is-best" : "");

    const top = document.createElement("div");
    top.className = "rc-top";

    const no = document.createElement("span");
    no.className = "rc-no";
    no.textContent = String(index + 1).padStart(2, "0");
    top.appendChild(no);

    if (best){
      const badge = document.createElement("span");
      badge.className = "rc-badge";
      badge.textContent = "系统推荐";
      top.appendChild(badge);
    }

    item.appendChild(top);

    const title = document.createElement("div");
    title.className = "rc-title";
    title.textContent = card.title || option.name || "方案";
    item.appendChild(title);

    if (card.desc){
      const desc = document.createElement("div");
      desc.className = "rc-desc";
      desc.textContent = card.desc;
      item.appendChild(desc);
    }

    const metric = document.createElement("div");
    metric.className = "rc-metric";

    const big = document.createElement("span");
    big.className = "rc-big";
    big.textContent = String(card.minutes ?? "—");
    metric.appendChild(big);

    const unit = document.createElement("span");
    unit.className = "rc-unit";
    unit.textContent = "分钟";
    metric.appendChild(unit);

    if (card.cost !== undefined && card.cost !== null){
      const money = document.createElement("span");
      money.className = "rc-money";
      money.textContent = `约 ${card.cost} 元`;
      metric.appendChild(money);
    }

    item.appendChild(metric);

    const facts = [];
    if (card.facts && card.facts.length) facts.push(card.facts.join(" · "));
    if (card.lines) facts.push(card.lines);

    if (facts.length){
      const factBox = document.createElement("div");
      factBox.className = "rc-facts";
      facts.forEach((line) => {
        const row = document.createElement("div");
        row.textContent = line;
        factBox.appendChild(row);
      });
      item.appendChild(factBox);
    }

    const pick = document.createElement("button");
    pick.type = "button";
    pick.className = "rc-btn";
    pick.textContent = best ? "就选这条" : "选这个";
    pick.onclick = () => chooseRoute(event.thread_id, option.id, turn, flow, panel);
    item.appendChild(pick);

    optionsBox.appendChild(item);
  });

  panel.appendChild(optionsBox);

  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "route-ask-reset";
  reset.textContent = "都不满意，重新说";
  reset.onclick = () => {
    panel.remove();
    const hint = turn.querySelector(".route-ask-hint");
    if (hint) hint.remove();
    const status = $("trip-status");
    if (status) status.textContent = "TRIP AGENT";
    const input = $("trip-input");
    if (input) input.focus();
  };
  panel.appendChild(reset);

  turn.appendChild(panel);
  showWaitingHint(turn, hintTextFor("route"));
  tripScroll();

  // 面板可能比可视区还高，滚到底它才完整露出来
  scrollToWaitingPanel();
}

async function chooseRoute(threadId, choiceId, turn, flow, panel){
  if (tripBusy) return;
  if (!threadId || !choiceId) return;

  tripBusy = true;
  tripClockResume();

  // 点完立刻收起面板和提示，别让它一直挡在输出前面；失败再放回来
  panel.classList.add("is-submitted");
  const oldHint = turn.querySelector(".route-ask-hint");
  if (oldHint) oldHint.remove();

  setTripSendState("stop");

  const compareIndex = TRIP_VIEWS.ROUTE.steps.indexOf("route_compare");
  if (compareIndex >= 0) tripStepSet(compareIndex, "busy");
  flow.status("按你选的方案，正在整理对比和推荐…");

  const ctx = { turn, flow, touched: true, chatTurn: false, awaitingChoice: false, stepError: -1 };

  const result = await tripStream(
    "/trip/route/choose",
    { thread_id: threadId, choice_id: choiceId, chat_id: openChatId },
    (ev) => tripHandleEvent(ev, ctx),
  );

  tripBusy = false;

  // 先把用时算出来，再停表：停表会把这一轮的起点清掉
  const usedText = `用时 ${fmtSec(tripSeconds())}`;
  tripClockStop(result.aborted ? "已停止"
                : (result.failed || ctx.stepError >= 0 ? "FAILED" : usedText));

  if (result.aborted){
    tripStepsInterrupt();
    flow.finish("已停止，可重新选择", true);
    setTripSendState("send");
    panel.classList.remove("is-submitted");
    panel.classList.remove("is-locked");
    panel.querySelectorAll("button").forEach((button) => { button.disabled = false; });
    showWaitingHint(turn, "已停止，可以重新选择 ↑");
  }else if (result.failed || ctx.stepError >= 0){
    tripStepsInterrupt();
    flow.finish("CTOS路线决策失败", true);
    setTripSendState("send");
    if (result.failed){
      appendTripError(
        "请求失败：" + (result.failed.message ? result.failed.message : result.failed) +
        "\n请确认后端已启动。", turn);
    }
    // 出错时把面板和按钮放回来，用户可以再点一次
    panel.classList.remove("is-submitted");
    panel.classList.remove("is-locked");
    panel.querySelectorAll("button").forEach((button) => { button.disabled = false; });
  }else{
    tripStepsFinish(false);
    flow.finish(`CTOS路线决策结束 · ${usedText}`, false);
    setTripSendState("send");
    panel.remove();

    const hint = turn.querySelector(".route-ask-hint");
    if (hint) hint.remove();
  }

  tripScroll();

  await loadTripRecords();
  if (state.view === "trip") renderTripHistory();

  const input = $("trip-input");
  if (input) input.focus();
}
