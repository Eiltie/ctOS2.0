let customerBusy = false;

// 最近几轮对话，每轮调接口时带给后端。
// 后端用它理解「那它怎么配」这种省略主语的追问。
// 只存在内存里：刷新页面就清空，不写数据库（客服不是会话型产品）。
let customerHistory = [];

// 最多保留几轮（一问一答算一轮）。太多会浪费 token，也没必要。
const CUSTOMER_HISTORY_TURNS = 3;


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
  let answerText = "";   // 攒下最终答案，用来记进历史

  try{
    const res = await fetch(API.base + "/customer/chat", {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ query, history: customerHistory }),
      signal: ctl.signal
    });

    if (res.status === 401){
      handleAuthExpired();
      throw new Error("登录已过期，请重新登录");
    }

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
            answerText = ev.text;
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

    // 这一轮成功了才记进历史（出错的轮次不带上下文，避免污染下一轮）
    if (answerText){
      pushCustomerHistory(query, answerText);
    }
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
        "\n请确认后端已启动：python -m api.main");
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


// 把这一轮问答记进本地历史，供下一轮追问时使用。
// 只保留最近 CUSTOMER_HISTORY_TURNS 轮，太长的历史浪费 token 也没必要。
function pushCustomerHistory(question, answer){
  customerHistory.push({ role: "user", content: question });
  customerHistory.push({ role: "assistant", content: answer });

  const maxItems = CUSTOMER_HISTORY_TURNS * 2;
  if (customerHistory.length > maxItems){
    customerHistory = customerHistory.slice(-maxItems);
  }
}


function customerNewSession(){
  setTimeout(() => {
    if (state.view !== "customer") return;
    abortCurrent();
    customerBusy = false;
    // 新会话清掉上下文，避免上一轮的问题影响这一轮
    customerHistory = [];
    customerIntro();
  }, 300);
}

function customerInit(){
  customerIntro();
}
