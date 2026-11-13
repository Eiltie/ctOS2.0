/* 出行｜页面入口：模式切换
 *
 * 做什么：顶部那条「路线规划 | 旅游攻略」，以及切换模式时的重置。
 * 谁在用：app.js 初始化时调 tripInit()（在 trip/base.js 里，结尾会调 tripRenderPluginBar）。
 *
 * 加载顺序（index.html 里固定）：
 *   trip/base.js  → 壳子
 *   trip/route.js → 注册 ROUTE
 *   trip/guide.js → 注册 TRAVEL
 *   trip.js       → 本文件，画插件条、处理切换
 */

// 画顶部的模式切换条
function tripRenderPluginBar(){
  const bar = $("trip-plugins");
  if (!bar) return;

  bar.innerHTML = TRIP_MODE_ORDER.map((key) => {
    const config = TRIP_MODES[key] || {};
    const active = key === tripMode ? " active" : "";
    return `<button class="trip-plugin${active}" data-mode="${key}" type="button">` +
           `${esc(config.label || key)}</button>`;
  }).join("");

  bar.querySelectorAll(".trip-plugin").forEach((btn) => {
    btn.onclick = () => {
      // 正在跑的时候不让切，避免两轮对话串在一起
      if (tripBusy) return;
      tripSetMode(btn.dataset.mode, { reset: true });
    };
  });
}

// 切模式。
//   reset  = true  用户主动切：开新会话，清上下文，回开场态（但不清左栏记录）
//   silent = true  程序内部切（打开历史记录时）：不重画插件条
function tripSetMode(mode, options = {}){
  if (!TRIP_MODES[mode]) return;

  const reset = options.reset === true;
  const silent = options.silent === true;
  const changed = mode !== tripMode;

  tripMode = mode;

  if (!silent) tripRenderPluginBar();

  if (changed || reset){
    tripRenderShell();
    tripStepsReset();
    tripRenderPlaceholder();
  }

  if (!reset) return;

  // 换模式 = 新会话：清掉上下文和输入，免得把上一个模式的城市带过去
  abortCurrent();
  tripBusy = false;
  tripHistory = [];
  openChatId = null;
  lastTripText = "";
  tripCanRetry = false;

  tripIntro();
  tripShowHero(true);
}
