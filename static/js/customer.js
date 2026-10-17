/* ============================================================
   智能客服模块（前端）

   后端契约: POST /customer/chat  { query }  ->  text/event-stream
   事件: START / TOKEN / DONE / ERROR

   和另外两个模块最大的不同：一问一答，不记会话、不带历史。
   所以这里不需要 sessionId、不需要 tripHistory 那样的累积变量。

   依赖（由 app.js 提供）：
       $  esc  md  API  newAbortSignal
   ============================================================ */

/** 客服面板的空状态引导：说明它只会查资料答题，不闲聊 */
function customerIntroHTML(){
  return `<div class="customer-welcome">` +
         `<div class="cw-title">ctOS 智能客服</div>` +
         `<div class="cw-desc">基于 RAG 三层检索，只回答关于本项目的问题。</div>` +
         `<div class="cw-desc cw-dim">问一句答一句，查不到会直接说没找到。</div>` +
         `</div>`;
}

/** 清空客服面板，回到空状态（切进来时调一次） */
function customerReset(){
  $("customerOut").innerHTML = customerIntroHTML();
}

/** 收起空状态引导（第一次提问时调，之后就只看得到对话） */
function customerDropIntro(){
  const w = $("customerOut").querySelector(".customer-welcome");
  if (w) w.remove();
}

/** 造一条客服消息：头像 + 气泡
 *
 *  who = "user" 靠右（ME 头像），其余靠左（CS 头像）。
 *  结构照搬闲聊模块的 .msg，两个模块视觉保持一致。
 *
 *  注意：这里【不加时间戳】。客服是一问一答、不留记录的，
 *  带上时间反而会让用户以为对话被存下来了。
 */
function customerMsg(who, avatarText){
  const row = document.createElement("div");
  row.className = "cust-msg " + who;

  const avatar = document.createElement("div");
  // 头像配色跟着 who 走：user 用 me 样式，cs 和 error 都用客服样式
  avatar.className = "cust-avatar " + (who === "user" ? "me" : "cs");
  avatar.textContent = avatarText;

  const bubble = document.createElement("div");
  bubble.className = "cust-bubble";

  row.appendChild(avatar);
  row.appendChild(bubble);
  $("customerOut").appendChild(row);
  return bubble;              // 返回气泡，调用方往里写内容
}

/** 追加一条「用户问的」 */
function customerAppendUser(text){
  customerDropIntro();
  const bubble = customerMsg("user", "ME");
  bubble.textContent = text;
  customerScroll();
}

/** 追加一条「客服答的」，先放「正在检索…」占位
 *
 *  检索要调接口，有网络延迟，所以先给个反馈——
 *  等第一个字到了再换成正文，用户不会对着空屏干等。
 */
function customerStartAnswer(){
  const bubble = customerMsg("cs", "CS");
  bubble.innerHTML = `<span class="cust-loading">正在检索…</span>`;
  customerScroll();
  return bubble;
}

/** 收到一个字：清掉占位符，把字加上去
 *
 *  逐字阶段用 md(..., true) 渲染：streaming=true 让未闭合的代码块也能先显示，
 *  否则流式过程中会露出裸的 ``` 符号。和闲聊模块的处理保持一致。
 */
function customerToken(el, text){
  const loading = el.querySelector(".cust-loading");
  if (loading) loading.remove();
  el.dataset.raw = (el.dataset.raw || "") + text;   // 累积原文
  el.innerHTML = md(el.dataset.raw, true);
  customerScroll();
}

/** 整段定稿：用它重渲染，纠正逐字拼接的偏差 */
function customerDone(el, fullText){
  el.dataset.raw = fullText;
  el.innerHTML = md(fullText, false);
  customerScroll();
}

/** 出错提示：排版和一条客服消息一样，只是换成红色 */
function customerError(msg){
  customerDropIntro();
  const bubble = customerMsg("error", "CS");
  bubble.textContent = msg;
  customerScroll();
}

/** 滚到底部（新内容总在下面） */
function customerScroll(){
  const p = $("customerPanel");
  if (p) p.scrollTop = p.scrollHeight;
}

/** 跑一次客服问答：读 SSE 流，按事件类型分派 */
async function sendCustomer(query){
  customerAppendUser(query);

  const res = await fetch(API.base + "/customer/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
    signal: newAbortSignal()          // 供"停止生成"掐断
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  // 先建好回答气泡，里面的「正在检索…」会在第一个字到达时消失
  const answerEl = customerStartAnswer();

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  const handle = (ev) => {
    switch (ev.kind){
      case "START":     /* 占位符已经在了，不用额外处理 */ break;
      case "TOKEN":     customerToken(answerEl, ev.text); break;
      case "DONE":      customerDone(answerEl, ev.text); break;
      case "ERROR":     customerError(ev.message); break;
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
}
