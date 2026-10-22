let customerBusy = false;


function customerIntro(){
  const feed = $("customer-feed");
  if (!feed) return;

  feed.innerHTML = `
    <div class="customer-welcome">
      <div class="radar-wrap">
        <div style="color: var(--cyan); font-weight: bold; font-size: 18px;">R</div>
      </div>
      <h2>ctOS 智能客服</h2>
    </div>`;
}

function renderCustomerHistory(){
  const box = $("history-customer");
  if (!box) return;
  box.innerHTML = "";
}


function customerRow(feed, kind){
  const isUser = kind === "user";

  const row = document.createElement("div");
  row.className = "cust-msg " + (isUser ? "user" : kind === "error" ? "error" : "cs");
  row.innerHTML =
    `<div class="avatar">${isUser ? "ME" : "CS"}</div>` +
    `<div class="cust-bubble"></div>`;
  feed.appendChild(row);
  scrollDown(feed);

  return row.querySelector(".cust-bubble");
}


async function sendCustomer(){
  const input = $("customer-input");
  const feed = $("customer-feed");
  if (!input || !feed || customerBusy) return;

  const query = input.value.trim();
  if (!query) return;

  customerBusy = true;
  input.value = "";

  const intro = feed.querySelector(".customer-welcome");
  if (intro) intro.remove();

  const userBubble = customerRow(feed, "user");
  userBubble.textContent = query;

  const answer = customerRow(feed, "cs");
  answer.innerHTML = `<span class="cust-loading">正在检索…</span>`;
  const typer = createTyper(feed, answer);

  const ctl = newAbortController();
  let failed = null;

  try{
    const res = await fetch(API.base + "/customer/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      signal: ctl.signal
    });

    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    if (!res.body) throw new Error("当前浏览器不支持流式读取");

    const parser = createSseParser((ev) => {
      switch (ev.kind){
        case "START":
          break;

        case "TOKEN":
          typer.push(ev.text || "");
          break;

        case "DONE":
          if (ev.text){
            typer.renderFinal(ev.text);
          }else if (typer.untouched()){
            typer.renderFinal("（没有检索到可用的内容）");
          }
          break;

        case "ERROR":
          customerError(feed, ev.message || "客服模块出错了");
          break;
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
    typer.done();
  }catch(err){
    if (err && err.name === "AbortError"){
      const partial = typer.cut();
      if (!partial) answer.parentNode.remove();
    }else{
      failed = err;
      const partial = typer.cut();
      if (!partial) answer.parentNode.remove();
      customerError(feed,
        "请求失败：" + (err && err.message ? err.message : err) +
        "\n请确认后端已启动：python src/ctOS_chat_api.py");
    }
  }finally{
    finishAbort(ctl);
    customerBusy = false;
    input.focus();
  }
}

function customerError(feed, text){
  const bubble = customerRow(feed, "error");
  bubble.textContent = text;
}


function customerNewSession(){
  setTimeout(() => {
    if (state.view !== "customer") return;
    abortCurrent();
    customerBusy = false;
    customerIntro();
  }, 300);
}

function customerInit(){
  customerIntro();
}
