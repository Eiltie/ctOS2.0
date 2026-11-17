// 前端认证：token 的存取、请求头发、登录态检查、访客会话引导。
//
// 现在的默认行为：
//   打开页面 → 有 token 就校验，没有就静默创建一个访客账号 → 直接进主界面。
//   登录框不再挡在首屏，只有在「主动点账号登录」或「自动进入失败」时才出现。
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

// 是不是自动创建的访客账号
function isTrialUser(user){
  const u = user || {};
  return !!(u.is_trial || (u.email || "").endsWith("@ctos-trial.local"));
}

// 拼请求头：有 token 就带上
function authHeaders(extra){
  const headers = Object.assign({}, extra || {});
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  return headers;
}

// 登录过期时统一处理：清掉本地状态，交给 app.js 决定下一步。
// 访客会静默换一个新访客身份；真实账号才弹登录框。
let onAuthExpired = null;

function handleAuthExpired(){
  const u = currentUser();
  const wasTrial = !u || isTrialUser(u);
  clearAuth();
  if (typeof onAuthExpired === "function") onAuthExpired(wasTrial);
}

// 带认证的 fetch：401 自动触发登录过期处理
async function authFetch(url, options){
  const opts = Object.assign({}, options || {});
  opts.headers = authHeaders(opts.headers);
  const res = await fetch(url, opts);

  if (res.status === 401){
    handleAuthExpired();
    throw new Error("登录已过期，请重新进入");
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


// ---------------------------------------------------------------- 会话引导
//
// 页面启动时调用 ensureSession(true)：
//   1. localStorage 有 token → 调 /auth/me 验证；有效就直接用
//   2. 没 token / token 失效 → POST /auth/trial 静默建一个访客账号
//   3. 失败返回 false，由 app.js 决定是否弹登录框兜底
//
// 聊天发送前调用 ensureSession(false)：有 token 直接放行，没有就等同一个
// 正在进行的引导任务，避免用户手速太快时发出没有 token 的请求。

let sessionTask = null;
let sessionError = "";

// 校验 token。网络错误或服务端 5xx 时保留 token，避免因为一次抖动就丢掉账号。
async function checkToken(token){
  try{
    const res = await fetch("/auth/me", {
      headers: { "Authorization": "Bearer " + token },
    });
    if (res.status === 401) return { ok: false };
    if (!res.ok) return { ok: true };
    return { ok: true, user: await res.json() };
  }catch(e){
    return { ok: true };
  }
}

// 静默创建一个访客账号并保存 token
async function guestLogin(){
  try{
    sessionError = "";
    const res = await fetch("/auth/trial", { method: "POST" });
    const data = await res.json().catch(() => ({}));

    if (!res.ok){
      throw new Error(data.detail || ("HTTP " + res.status));
    }

    saveAuth(data.token, data.user);
    return true;
  }catch(e){
    sessionError = (e && e.message) ? e.message : String(e);
    return false;
  }
}

function ensureSession(validate){
  if (sessionTask) return sessionTask;

  const token = getToken();
  if (token && !validate) return Promise.resolve(true);

  sessionTask = (async () => {
    if (token){
      const info = await checkToken(token);
      if (info.ok){
        if (info.user) saveAuth(token, info.user);
        return true;
      }
      clearAuth();
    }
    return await guestLogin();
  })().finally(() => {
    sessionTask = null;
  });

  return sessionTask;
}


// ---------------------------------------------------------------- 登录页

// 显示登录弹层、隐藏主界面（只有主动登录或自动进入失败时才走这里）
function showLogin(){
  const login = document.getElementById("login-screen");
  const app = document.getElementById("app-root");
  if (login) login.style.display = "flex";
  if (app) app.style.display = "none";
}

// 显示主界面、隐藏登录弹层
function showApp(){
  const login = document.getElementById("login-screen");
  const app = document.getElementById("app-root");
  if (login) login.style.display = "none";
  if (app) app.style.display = "";
}

// 关闭登录弹层：已经有访客身份就回到主界面，没有就重新尝试访客进入
async function closeLogin(){
  loginError("");
  if (getToken()){
    showApp();
    return;
  }
  await continueAsGuest();
}

// 在登录页显示一条错误
function loginError(text){
  const el = document.getElementById("login-error");
  if (!el) return;
  el.textContent = text || "";
  el.style.display = text ? "block" : "none";
}

// 从登录弹层回到免登录的访客模式
async function continueAsGuest(){
  const btn = document.getElementById("login-guest");
  if (btn){ btn.disabled = true; btn.textContent = "正在进入..."; }
  loginError("");

  const ok = await guestLogin();

  if (btn){
    btn.disabled = false;
    btn.textContent = "不登录，直接以访客身份使用";
  }

  if (!ok){
    loginError(sessionError ? "进入失败：" + sessionError : "进入失败，请稍后再试");
    return;
  }

  showApp();
  if (typeof onLoginSuccess === "function") await onLoginSuccess();
}

// 切换登录 / 注册表单
function switchLoginMode(mode){
  const isRegister = mode === "register";
  const title = document.getElementById("login-title");
  const sub = document.getElementById("login-sub");
  const btn = document.getElementById("login-submit");
  const toggle = document.getElementById("login-toggle");

  if (title) title.textContent = isRegister ? "注册账号" : "登录已有账号";
  if (sub) sub.textContent = isRegister
    ? "创建一个账号，之后的会话记录会跟着账号走；访客期间的聊天不会自动带过去"
    : "登录后，新账号的会话记录独立保存；访客期间的聊天不会自动带过去";
  if (btn) { btn.textContent = isRegister ? "注册并登录" : "登录"; btn.dataset.mode = mode; }
  if (toggle) toggle.textContent = isRegister ? "已有账号？去登录" : "还没有账号？去注册";

  loginError("");
}

// 访客有没有值得提醒的数据
function guestHasData(){
  const hasSessions = typeof state !== "undefined"
    && Array.isArray(state.sessions)
    && state.sessions.length > 0;

  const hasTrips = typeof tripRecords !== "undefined"
    && Array.isArray(tripRecords)
    && tripRecords.length > 0;

  return hasSessions || hasTrips;
}

// 访客切到真实账号前，明确告诉用户旧数据不会跟过去
function confirmGuestSwitch(){
  if (!isTrialUser(currentUser())) return true;
  if (!guestHasData()) return true;

  return confirm(
    "你现在是访客。\n\n" +
    "登录或注册后，访客期间的聊天和出行记录不会自动带过去。\n\n" +
    "确定继续吗？"
  );
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

  if (!confirmGuestSwitch()) return;

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
    if (typeof onLoginSuccess === "function") await onLoginSuccess();
  }catch(e){
    loginError("网络错误：" + (e && e.message ? e.message : e));
  }finally{
    if (btn){
      btn.disabled = false;
      btn.textContent = isRegister ? "注册并登录" : "登录";
    }
  }
}

// 退出当前真实账号：清掉登录态后重新加载，启动流程会自动回到访客模式。
// 这样就不会再把人丢回登录页。
function logout(){
  clearAuth();
  if (typeof abortCurrent === "function") abortCurrent();
  location.reload();
}

// 在侧栏显示当前身份，并切换「账号登录 / 退出当前账号」按钮
function renderUserBadge(){
  const el = document.getElementById("user-email");
  if (!el) return;

  const u = currentUser();
  const email = (u && u.email) ? u.email : "";
  const isTrial = isTrialUser(u) || !email;

  // 访客邮箱是 trial_<16位随机串>@ctos-trial.local，太长会把侧栏撑开，
  // 统一显示成「访客」，完整邮箱放进 title，鼠标悬停还能看到。
  el.textContent = isTrial ? "访客" : email;
  el.title = isTrial
    ? "访客模式（临时空间，换设备不同步）：" + email
    : email;

  const entry = document.getElementById("login-entry");
  const out = document.getElementById("logout-btn");
  if (entry) entry.style.display = isTrial ? "" : "none";
  if (out) out.style.display = isTrial ? "none" : "";
}
