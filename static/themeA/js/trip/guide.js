/* 出行｜旅游攻略的界面：去某地玩几天
 *
 * 做什么：开场页的景点卡片墙，以及勾景点那个等待面板。
 * 谁在用：base.js 的 tripRenderHeroExtras 和 tripHandleEvent 调用。
 *
 * 注意：这里已经没有"模式"的概念了。用户不选，Agent 判断；
 *       攻略只有一个暂停点（勾景点），勾完一路跑到「游玩建议」。
 */

/* 开场页的景点卡片。
 *
 * 只写"这是什么、为什么值得去"，不写门票和营业时间——
 * 这些会变，写死了反而误导。真正的准确信息留给生成攻略时联网查。
 * 这张表是起步用的样例，按城市往里加就行。
 */
const GUIDE_CARDS = [
  { city: "杭州", name: "西湖", tag: "湖景 · 步行",
    intro: "断桥、苏堤、白堤连成一线，靠走和坐船，是杭州最经典的一圈。" },
  { city: "杭州", name: "灵隐寺", tag: "寺庙 · 爬山",
    intro: "飞来峰石刻加山间古寺，逛下来半天，台阶多，带老人要慢。" },
  { city: "杭州", name: "西溪湿地", tag: "湿地 · 坐船",
    intro: "水道纵横，坐摇橹船最舒服，适合半天慢逛。" },
  { city: "成都", name: "四川科技馆", tag: "室内 · 亲子",
    intro: "天府广场旁，互动展项多，室内不受天气影响，适合带孩子。" },
  { city: "成都", name: "宽窄巷子", tag: "街区 · 吃逛",
    intro: "老街区改建，逛吃为主，晚上人多但热闹。" },
  { city: "成都", name: "熊猫基地", tag: "动物 · 室外",
    intro: "看熊猫要趁早，上午活跃，园区大，建议留半天。" }
];

let guideCardPicked = null;

function renderGuideCards(){
  const wall = $("trip-cardwall");
  if (!wall) return;

  wall.innerHTML =
    `<div class="trip-cardwall-title">或者从下面挑一个</div>` +
    `<div class="trip-card-grid">` +
    GUIDE_CARDS.map((c, i) =>
      `<div class="trip-card guide-card" data-i="${i}">` +
        `<h4>${esc(c.city)} · ${esc(c.name)}</h4>` +
        `<p>${esc(c.tag)}</p>` +
        `<div class="guide-card-intro" style="display:none">` +
          `<div class="gci-line">${esc(c.intro)}</div>` +
          `<div class="gci-line gci-note">门票和开放时间会变，生成攻略时再联网确认。</div>` +
          `<button class="gci-go" type="button">按这个生成攻略</button>` +
        `</div>` +
      `</div>`
    ).join("") +
    `</div>`;

  wall.querySelectorAll(".guide-card").forEach((card) => {
    card.onclick = (e) => {
      if (e.target.classList.contains("gci-go")){
        const c = GUIDE_CARDS[Number(card.dataset.i)];
        if (!c) return;
        const input = $("trip-input-hero");
        if (!input) return;
        input.value = `想去${c.city}玩 3 天，重点想去${c.name}`;
        tripShowHero();
        sendTrip();
        return;
      }

      // 点卡片展开简介，再点收起
      wall.querySelectorAll(".guide-card").forEach((other) => {
        if (other === card) return;
        other.classList.remove("is-open");
        const box = other.querySelector(".guide-card-intro");
        if (box) box.style.display = "none";
      });

      const open = card.classList.toggle("is-open");
      const box = card.querySelector(".guide-card-intro");
      if (box) box.style.display = open ? "" : "none";
      if (typeof syncStickyHeads === "function") syncStickyHeads();
    };
  });
}




/* ===== 景点清单 ===== */

function showSpotChoices(turn, flow, event){
  const panel = document.createElement("div");
  panel.className = "route-ask spot-ask";

  const question = document.createElement("div");
  question.className = "route-ask-question";
  question.textContent = event.question || "这些景点可以吗？";
  panel.appendChild(question);

  const list = document.createElement("div");
  list.className = "spot-list";

  (event.spot_names || []).forEach((name) => {
    const row = document.createElement("label");
    row.className = "spot-row";

    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = true;
    box.dataset.name = name;

    const text = document.createElement("span");
    text.textContent = name;

    row.appendChild(box);
    row.appendChild(text);
    list.appendChild(row);
  });

  panel.appendChild(list);

  const addRow = document.createElement("div");
  addRow.className = "spot-add";

  const addInput = document.createElement("input");
  addInput.type = "text";
  addInput.placeholder = "想加一个景点？写在这里，可以留空";
  addInput.className = "spot-add-input";

  addRow.appendChild(addInput);
  panel.appendChild(addRow);

  const actions = document.createElement("div");
  actions.className = "spot-actions";

  const confirmButton = document.createElement("button");
  confirmButton.type = "button";
  confirmButton.className = "spot-confirm";
  confirmButton.textContent = "就这样，继续排行程";

  const skipButton = document.createElement("button");
  skipButton.type = "button";
  skipButton.className = "spot-skip";
  skipButton.textContent = "不改了，直接排";

  actions.appendChild(confirmButton);
  actions.appendChild(skipButton);
  panel.appendChild(actions);

  confirmButton.onclick = () => {
    const removed = [];
    list.querySelectorAll("input[type=checkbox]").forEach((box) => {
      if (!box.checked) removed.push(box.dataset.name);
    });
    submitSpotChoices(event.thread_id, removed, addInput.value.trim(), turn, flow, panel);
  };

  skipButton.onclick = () => {
    submitSpotChoices(event.thread_id, [], "", turn, flow, panel);
  };

  turn.appendChild(panel);
  showWaitingHint(turn, hintTextFor("spots"));
  tripScroll();
  scrollToWaitingPanel();
}

function submitSpotChoices(threadId, removed, added, turn, flow, panel){
  guideResume(
    "/guide/spots",
    { thread_id: threadId, removed, added },
    turn, flow, panel,
    "按你选的景点，正在安排行程…"
  );
}


/* ===== 勾完景点之后：接着跑到游玩建议 ===== */

async function guideResume(url, body, turn, flow, panel, pendingText){
  if (tripBusy) return;

  tripBusy = true;
  tripClockResume();
  panel.classList.add("is-locked");
  panel.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  setTripSendState("stop");

  // 点完先把表单收起来，别让它一直挡在输出前面；失败再放回来
  panel.classList.add("is-submitted");
  const oldHint = turn.querySelector(".route-ask-hint");
  if (oldHint) oldHint.remove();

  flow.status(pendingText);

  const ctx = { turn, flow, touched: false, chatTurn: false, awaitingChoice: false, stepError: -1 };

  const result = await tripStream(url, body, (ev) => tripHandleEvent(ev, ctx));

  tripBusy = false;

  if (result.aborted){
    tripClockStop("已停止");
    tripStepsInterrupt();
    flow.finish("已停止，可重新选择", true);
    setTripSendState("send");

    if (panel.isConnected){
      panel.classList.remove("is-submitted");
      panel.classList.remove("is-locked");
      panel.querySelectorAll("button").forEach((button) => { button.disabled = false; });
      showWaitingHint(turn, "已停止，可以重新选择 ↑");
    }

    tripScroll();
    const stoppedInput = $("trip-input");
    if (stoppedInput) stoppedInput.focus();
    return;
  }

  if (result.failed || ctx.stepError >= 0){
    tripClockStop("FAILED");
    tripStepsInterrupt();
    flow.finish("CTOS任务失败", true);
    setTripSendState("send");

    if (result.failed){
      appendTripError(
        "请求失败：" + (result.failed.message ? result.failed.message : result.failed), turn);
    }

    // 出错时把表单和按钮放回来，允许再试一次
    panel.classList.remove("is-submitted");
    panel.classList.remove("is-locked");
    panel.querySelectorAll("button").forEach((button) => { button.disabled = false; });
  }else if (ctx.awaitingChoice){
    // 又停下来问用户了：暂停计时，等用户选完再接着算
    tripClockPause();
    setTripSendState("send");
    return;
  }else{
    const usedText = `用时 ${fmtSec(tripSeconds())}`;
    tripClockStop(usedText);
    tripStepsFinish(false);
    flow.finish(`CTOS规划结束 · ${usedText}`, false);
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
