// 提交反馈：侧栏入口（桌面）+ 右下角浮标（手机）共用一个弹窗。
//
// ============================ 关于这个文件 ============================
// 独立功能，不依赖任何业务模块，也不需要了可以整块删掉：
//   1. static/js/common/feedback.js           （本文件）
//   2. static/index.html 里 id="feedback-entry" 的按钮块
//   3. static/index.html 里 id="feedback-fab" 的浮标块
//   4. static/css/modules.css 里「===== 反馈 =====」那一段
//   5. api/main.py 里「===== 反馈 =====」那一段 + databases/db_feedback.py
// 删掉之后项目行为和加之前完全一样。
// ====================================================================

const FEEDBACK_RATINGS = ["很满意", "满意", "一般", "不太满意"];

// 当前选中了哪个评价（可空：只填文字也能提交）
let feedbackRating = null;

// 提交过就不再打扰（同一次页面会话里）
let feedbackSent = false;


// 打开弹窗
function openFeedback(){
  const modal = document.getElementById("feedback-modal");
  if (!modal) return;

  if (feedbackSent){
    alert("感谢反馈，你已经提交过了。");
    return;
  }

  // 清空上一次的状态
  feedbackRating = null;
  const text = document.getElementById("feedback-content");
  const contact = document.getElementById("feedback-contact");
  const err = document.getElementById("feedback-error");
  if (text) text.value = "";
  if (contact) contact.value = "";
  if (err){ err.textContent = ""; err.style.display = "none"; }

  document.querySelectorAll("#feedback-modal .fb-mood").forEach((el) => el.classList.remove("on"));
  updateFeedbackCount();

  modal.classList.add("show");
  if (typeof modal.show === "function") modal.show();
  else modal.setAttribute("open", "");
  if (text) setTimeout(() => text.focus(), 80);
}

// 关闭弹窗
function closeFeedback(){
  const modal = document.getElementById("feedback-modal");
  if (!modal) return;
  if (typeof modal.hide === "function") modal.hide();
  else modal.removeAttribute("open");
  modal.classList.remove("show");
}

// 选中一个评价
function pickRating(btn, value){
  feedbackRating = (feedbackRating === value) ? null : value;   // 再点一次取消
  document.querySelectorAll("#feedback-modal .fb-mood").forEach((el) => {
    el.classList.toggle("on", el === btn && feedbackRating !== null);
  });
}

// 字数统计
function updateFeedbackCount(){
  const text = document.getElementById("feedback-content");
  const counter = document.getElementById("feedback-count");
  if (!text || !counter) return;
  counter.textContent = `${text.value.length} / 500`;
}

// 当前在哪个模块（提交时带上，方便统计哪个模块问题多）
function currentPageName(){
  try{
    if (typeof state !== "undefined" && state && state.view) return state.view;
  }catch(e){ /* state 还没初始化 */ }

  // 登录页也允许提反馈
  const login = document.getElementById("login-screen");
  if (login && getComputedStyle(login).display !== "none") return "login";
  return "chat";
}

// 提交
async function submitFeedback(){
  const btn = document.getElementById("feedback-submit");
  const err = document.getElementById("feedback-error");
  const content = (document.getElementById("feedback-content").value || "").trim();
  const contact = (document.getElementById("feedback-contact").value || "").trim();

  if (!content && !feedbackRating){
    showFeedbackError("请至少选择一个评价，或填写反馈内容");
    return;
  }

  if (btn){ btn.disabled = true; btn.textContent = "提交中…"; }
  if (err){ err.style.display = "none"; }

  try{
    const res = await fetch("/feedback", {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        content: content.slice(0, 500),
        contact: contact.slice(0, 100),
        rating: feedbackRating,
        page: currentPageName(),
      }),
    });

    if (res.status === 429){
      showFeedbackError("提交太频繁了，请稍后再试");
      return;
    }

    if (!res.ok){
      const data = await res.json().catch(() => ({}));
      showFeedbackError(data.detail || "提交失败，请稍后再试");
      return;
    }

    feedbackSent = true;
    closeFeedback();

    // 提交成功后给个明显的确认，别让用户以为没点上
    const ok = document.createElement("div");
    ok.className = "feedback-toast";
    ok.textContent = "✓ 感谢反馈，已收到你的意见";
    document.body.appendChild(ok);
    setTimeout(() => ok.remove(), 2600);

  }catch(e){
    showFeedbackError("网络错误，请稍后再试");
  }finally{
    if (btn){ btn.disabled = false; btn.textContent = "提交"; }
  }
}

function showFeedbackError(text){
  const err = document.getElementById("feedback-error");
  if (!err) return;
  err.textContent = text;
  err.style.display = "block";
}

// 弹窗打开时按 Esc 关闭
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeFeedback();
});
