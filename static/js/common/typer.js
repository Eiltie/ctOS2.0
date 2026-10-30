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
function createTyper(container, bubbleEl){
  const queue = [];
  let shown = "";
  let body = null;
  let cursor = null;
  let active = false;
  let finished = false;
  let cutOff = false;
  let raf = 0;

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

  function takeQuota(){
    const backlog = queue.reduce((n, s) => n + s.length, 0);
    const pressure = Math.min(1, backlog / 160);
    const cps = TYPE_MIN_CPS + (TYPE_MAX_CPS - TYPE_MIN_CPS) * pressure;
    let quota = Math.max(1, Math.round(cps * TYPE_FRAME_MS / 1000));

    while (quota > 0 && queue.length){
      const piece = queue[0];
      const take = piece.slice(0, quota);
      shown += take;
      quota -= take.length;
      if (take.length < piece.length) queue[0] = piece.slice(take.length);
      else queue.shift();
    }
  }

  function tick(){
    raf = 0;
    if (cutOff || !alive()) return;

    if (queue.length){
      ensureBody();
      takeQuota();
      body.data = shown;
      scrollDown(container);
    }
    if (finished && queue.length === 0){
      dropCursor();
      body = null;
      paintFinal();
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
      queue.push(String(piece));
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
      while (queue.length) shown += queue.shift();
      if (alive() && shown){
        ensureBody();
        body.data = shown;
        dropCursor();
        body = null;
        paintFinal();
      }
      return shown;
    },
    renderFinal(text){
      cutOff = true;
      finished = true;
      if (raf){ cancelAnimationFrame(raf); raf = 0; }
      queue.length = 0;
      shown = String(text == null ? "" : text);

      body = null;
      cursor = null;
      bubbleEl.textContent = "";
      bubbleEl.classList.remove("loading-bubble");
      if (!shown) return shown;

      paintFinal();
      scrollDown(container);
      return shown;
    },
    get text(){ return shown; },
    untouched
  };
}
