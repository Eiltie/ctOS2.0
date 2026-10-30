// 通用小工具：不依赖任何其他模块，谁都可以用。
//
// 改动前这些散落在 app.js 顶部，和会话管理、视图切换混在一起，
// 想找 esc() 得先往上翻 800 行。

const $ = (id) => document.getElementById(id);

// 当前时间 HH:MM，用在消息气泡的时间戳
const now = () => {
  const d = new Date();
  return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
};

// HTML 转义：所有用户输入写进 innerHTML 前必须过这一道
function esc(s){
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// 滚到底部
function scrollDown(el){
  if (!el) return;
  el.scrollTop = el.scrollHeight;
}

// GET 一个 JSON：失败返回 null，不抛异常，调用方自己判断
//
// 自动带登录 token（如果 common/auth.js 已经加载并且有 token）。
// 401 时会清掉本地登录态，并把界面弹回登录页。
async function getJson(url, options){
  try{
    const opts = Object.assign({}, options || {});
    if (typeof authHeaders === "function"){
      opts.headers = authHeaders(opts.headers);
    }
    const res = await fetch(API.base + url, opts);

    if (res.status === 401 && typeof handleAuthExpired === "function"){
      handleAuthExpired();
      return null;
    }
    if (!res.ok) return null;
    return await res.json();
  }catch(e){
    return null;
  }
}

// 给输入框绑「回车发送」，避开中文输入法的候选词回车
function bindEnter(inputId, handler){
  const input = $(inputId);
  if (!input) return;
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing){
      e.preventDefault();
      handler();
    }
  });
}
