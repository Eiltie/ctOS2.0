// 打字机渲染器：把流式文本一段段「打」到气泡里。
//
// 为什么要打字机：后端是一块块推字过来的，如果每块直接赋值，
// 会出现「一次糊出一大片」的跳变。这里把积压的字按帧匀着放出来。
//
// 用法：
//   const typer = createTyper(feed, bubbleEl);
//   typer.push("一段字");      // 流式来字时调用
//   typer.done();              // 流结束
//   typer.renderFinal("全文");  // 用定稿覆盖（后端 DONE 事件）
//   typer.cut();               // 中断，返回已显示的字
//
// ── 性能说明（重要）────────────────────────────────────────
// 原来的 tick() 每一帧做三件事，其中第二件是强制同步布局（forced reflow）：
//   1. body.data = shown          ← 写 DOM
//   2. scrollDown(container)      ← 读 scrollHeight（强制浏览器立刻重算布局）
//   3. 再写 scrollTop
// 流式输出时这是每秒 60 次「写→读→写」，每次读 scrollHeight 都要求
// 浏览器把前面所有 DOM 改动和样式一起算完，等于每帧多做一次完整布局。
//
// 现在改成：
//   - 只有「用户本来就在底部」时才跟随滚动（往上翻历史时不会被拽回去）
//   - 滚动合并到下一帧统一做，且一帧只读一次 scrollHeight
//   - 判断是否贴底用缓存值，不必每帧精确测量
// ──────────────────────────────────────────────────────────

function createTyper(container, bubbleEl){
  const queue = [];
  let shown = "";
  let body = null;
  let cursor = null;
  let active = false;
  let finished = false;
  let cutOff = false;
  let raf = 0;

  /** 待处理的积压字符数：维护成计数器，避免每帧 queue.reduce() 扫全队列 */
  let backlog = 0;

  /** 用户是否贴着底部看（初始为 true）。往上翻时置 false，就不再拽回去 */
  let stickToBottom = true;

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

  /**
   * 跟随滚动。
   *
   * container.scrollTop = container.scrollHeight 这一行看着简单，
   * 但它会「读 scrollHeight（强制同步布局）→ 写 scrollTop（再一轮布局）」，
   * 放在每帧里就是每秒 60 次强制重排，是流式卡顿的主要来源之一。
   *
   * 这里做两件事降低开销：
   *   1. 只有用户贴着底部看时才跟随（往上翻历史时完全不碰滚动）
   *   2. 同一轮里多次调用只排一次，实际滚动延到下一帧统一做
   */
  let scrollPending = false;

  function followScroll(){
    if (!stickToBottom || !container || scrollPending) return;
    scrollPending = true;
    requestAnimationFrame(() => {
      scrollPending = false;
      if (!stickToBottom || !container || !container.isConnected) return;
      container.scrollTop = container.scrollHeight;
    });
  }

  function takeQuota(){
    const pressure = Math.min(1, backlog / 160);
    const cps = TYPE_MIN_CPS + (TYPE_MAX_CPS - TYPE_MIN_CPS) * pressure;
    let quota = Math.max(1, Math.round(cps * TYPE_FRAME_MS / 1000));

    while (quota > 0 && queue.length){
      const piece = queue[0];
      const take = piece.slice(0, quota);
      shown += take;
      quota -= take.length;
      backlog -= take.length;
      if (take.length < piece.length) queue[0] = piece.slice(take.length);
      else queue.shift();
    }
    if (backlog < 0) backlog = 0;
  }

  function tick(){
    raf = 0;
    if (cutOff || !alive()) return;

    if (queue.length){
      ensureBody();
      takeQuota();
      body.data = shown;
      followScroll();
    }
    if (finished && queue.length === 0){
      dropCursor();
      body = null;
      paintFinal();
      followScroll();
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
      const s = String(piece);
      queue.push(s);
      backlog += s.length;
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
      while (queue.length){
        const piece = queue.shift();
        shown += piece;
        backlog -= piece.length;
      }
      backlog = 0;
      if (alive() && shown){
        ensureBody();
        body.data = shown;
        dropCursor();
        body = null;
        paintFinal();
        followScroll();
      }
      return shown;
    },
    renderFinal(text){
      cutOff = true;
      finished = true;
      if (raf){ cancelAnimationFrame(raf); raf = 0; }
      queue.length = 0;
      backlog = 0;
      shown = String(text == null ? "" : text);

      body = null;
      cursor = null;
      bubbleEl.textContent = "";
      bubbleEl.classList.remove("loading-bubble");
      if (!shown) return shown;

      paintFinal();
      followScroll();
      return shown;
    },
    get text(){ return shown; },

    /** 外部在用户滚动时调用：贴底就继续跟随，往上翻就停 */
    setStick(v){ stickToBottom = !!v; },

    untouched
  };
}

/**
 * 给一个滚动容器挂上「贴底判断」。
 *
 * 用 passive 监听 + rAF 节流，滚动事件不会阻塞主线程；
 * 判断结果只写进一个布尔值，不触发任何布局写入。
 */
function bindStickToBottom(container, typer, threshold){
  if (!container || container.__stickBound) return;
  container.__stickBound = true;

  const limit = threshold == null ? 120 : threshold;
  let raf = 0;

  const check = () => {
    raf = 0;
    if (typer && typeof typer.setStick === "function"){
      const gap = container.scrollHeight - container.scrollTop - container.clientHeight;
      typer.setStick(gap < limit);
    }
  };

  container.addEventListener("scroll", () => {
    if (!raf) raf = requestAnimationFrame(check);
  }, { passive: true });
}
