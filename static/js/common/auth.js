// 前端认证：token 的存取、请求头发、登录态检查。
//
// token 存在 localStorage，刷新页面还在。
// 所有需要登录的请求都要带上 Authorization: Bearer <token>。

const TOKEN_KEY = "ctos_token";
const USER_KEY = "ctos_user";


// 读 token；没有返回 null
function getToken(){
  try { return localStorage.getItem(TOKEN_KEY); }
  catch(e){ return null; }
}

// 存 token 和用户信息
function saveAuth(token, user){
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user || {}));
  } catch(e){ /* 隐私模式下 localStorage 不可用，忽略 */ }
}

// 清掉登录态
function clearAuth(){
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch(e){}
}

// 读当前用户信息（只用于显示，不作鉴权依据）
function currentUser(){
  try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); }
  catch(e){ return null; }
}

// 拼请求头：有 token 就带上
function authHeaders(extra){
  const headers = Object.assign({}, extra || {});
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  return headers;
}

// 登录过期时统一处理：清掉本地状态，弹回登录页
let onAuthExpired = null;

function handleAuthExpired(){
  clearAuth();
  if (typeof onAuthExpired === "function") onAuthExpired();
}

// 带认证的 fetch：401 自动触发登录过期处理
async function authFetch(url, options){
  const opts = Object.assign({}, options || {});
  opts.headers = authHeaders(opts.headers);
  const res = await fetch(url, opts);

  if (res.status === 401){
    handleAuthExpired();
    throw new Error("登录已过期，请重新登录");
  }
  return res;
}

// 带认证的 GET JSON
async function authJson(url, options){
  try {
    const res = await authFetch(url, options);
    if (!res.ok) return null;
    return await res.json();
  } catch(e){
    return null;
  }
}


// ---------------------------------------------------------------- 登录页

// 显示登录页、隐藏主界面
function showLogin(){
  const login = document.getElementById("login-screen");
  const app = document.getElementById("app-root");
  if (login) login.style.display = "flex";
  if (app) app.style.display = "none";
}

// 显示主界面、隐藏登录页
function showApp(){
  const login = document.getElementById("login-screen");
  const app = document.getElementById("app-root");
  if (login) login.style.display = "none";
  if (app) app.style.display = "";
}

// 在登录页显示一条错误
function loginError(text){
  const el = document.getElementById("login-error");
  if (!el) return;
  el.textContent = text || "";
  el.style.display = text ? "block" : "none";
}

// 切换登录 / 注册表单
function switchLoginMode(mode){
  const isRegister = mode === "register";
  const title = document.getElementById("login-title");
  const sub = document.getElementById("login-sub");
  const btn = document.getElementById("login-submit");
  const toggle = document.getElementById("login-toggle");

  if (title) title.textContent = isRegister ? "注册账号" : "登录 ctOS";
  if (sub) sub.textContent = isRegister ? "创建一个账号，开始使用" : "登录后继续你的对话";
  if (btn) { btn.textContent = isRegister ? "注册并登录" : "登录"; btn.dataset.mode = mode; }
  if (toggle) toggle.textContent = isRegister ? "已有账号？去登录" : "还没有账号？去注册";

  loginError("");
}

// 提交登录或注册
async function submitAuth(){
  const btn = document.getElementById("login-submit");
  const mode = (btn && btn.dataset.mode) || "login";

  const email = (document.getElementById("login-email").value || "").trim();
  const password = document.getElementById("login-password").value || "";

  if (!email || !password){
    loginError("邮箱和密码都要填");
    return;
  }

  const isRegister = mode === "register";
  const url = isRegister ? "/auth/register" : "/auth/login";

  if (btn){ btn.disabled = true; btn.textContent = isRegister ? "注册中..." : "登录中..."; }
  loginError("");

  try{
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok){
      loginError(data.detail || "操作失败，请重试");
      return;
    }

    saveAuth(data.token, data.user);
    document.getElementById("login-password").value = "";

    showApp();
    if (typeof onLoginSuccess === "function") onLoginSuccess();
  }catch(e){
    loginError("网络错误：" + (e && e.message ? e.message : e));
  }finally{
    if (btn){
      btn.disabled = false;
      btn.textContent = isRegister ? "注册并登录" : "登录";
    }
  }
}

// 退出登录
function logout(){
  clearAuth();
  if (typeof abortCurrent === "function") abortCurrent();
  document.getElementById("login-email").value = "";
  document.getElementById("login-password").value = "";
  switchLoginMode("login");
  showLogin();
}

// 在侧栏显示当前登录的邮箱
function renderUserBadge(){
  const el = document.getElementById("user-email");
  if (!el) return;
  const u = currentUser();
  el.textContent = u && u.email ? u.email : "";
  el.title = u && u.email ? u.email : "";
}
