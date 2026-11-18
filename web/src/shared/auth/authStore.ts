/**
 * 认证状态：token 的存取、启动时自动登录、登出。
 *
 * 后端的两种进入方式：
 *   POST /auth/trial   访客账号，免注册，打开页面就能用（独立租户，记录只在当前浏览器）
 *   POST /auth/login   正式账号，跨设备保留记录
 *
 * 前端的行为（和旧版一致）：
 *   1. 有本地 token → 先假设有效，调 /auth/me 校验
 *   2. 没有 token，或校验失败 → 自动创建访客账号，直接进主界面
 *   3. 用户主动登录 → 换成正式账号
 *
 * 为什么默认走访客：
 *   打开就能用是体验上的关键。想保留记录的人会自己去登录。
 */
import { computed, reactive } from 'vue'
import { getAuthToken, http, setAuthToken, setUnauthorizedHandler } from '@/shared/api/http'
import type { AuthResponse, TrialResponse, User } from '@/shared/types/api'

const TOKEN_KEY = 'ctos_token'
const USER_KEY = 'ctos_user'

interface AuthState {
  user: User | null
  /** 是不是访客账号（没有正式账号） */
  isGuest: boolean
  /** 启动检查中 */
  booting: boolean
  error: string
}

const state = reactive<AuthState>({
  user: null,
  isGuest: false,
  booting: true,
  error: '',
})

// ---------------------------------------------------------------- token 存取

function saveSession(token: string, user: User) {
  setAuthToken(token)
  state.user = user
  try {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } catch {
    // 隐私模式下 localStorage 可能不可用，不影响本次使用
  }
}

function clearSession() {
  setAuthToken(null)
  state.user = null
  state.isGuest = false
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  } catch {
    // 忽略
  }
}

/** 从 localStorage 恢复 token（页面刷新时） */
function restoreToken(): boolean {
  try {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) return false

    setAuthToken(token)

    const raw = localStorage.getItem(USER_KEY)
    if (raw) state.user = JSON.parse(raw) as User

    return true
  } catch {
    return false
  }
}

// ---------------------------------------------------------------- 身份变化通知

/**
 * 身份变化时通知订阅方。
 *
 * 为什么需要：
 *   登录 / 注册 / 退出之后，账号换了，各个模块手里的会话列表、出行记录
 *   全都是旧账号的，必须重新拉。
 *   让 authStore 直接去调 chatStore / tripStore 会造成循环依赖，
 *   所以做成订阅：谁关心谁自己注册。
 */
type AuthListener = () => void
const listeners = new Set<AuthListener>()

/** 注册一个「身份变了」的回调，返回取消订阅的函数 */
function onIdentityChanged(listener: AuthListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** 通知所有订阅方（内部用，切换账号后调） */
function notifyIdentityChanged() {
  for (const listener of listeners) {
    try {
      listener()
    } catch {
      // 某个订阅方出错不影响其他方
    }
  }
}

// ---------------------------------------------------------------- 登录方式

/** 用正式账号登录 */
async function login(email: string, password: string) {
  const result = await http.post<AuthResponse>('/auth/login', { email, password })
  saveSession(result.token, result.user)
  state.isGuest = false
  state.error = ''
  notifyIdentityChanged()
}

/** 注册并直接登录 */
async function register(email: string, password: string, displayName: string) {
  const result = await http.post<AuthResponse>('/auth/register', {
    email,
    password,
    display_name: displayName,
  })
  saveSession(result.token, result.user)
  state.isGuest = false
  state.error = ''
  notifyIdentityChanged()
}

/**
 * 创建访客账号 —— 注意跳过认证头：
 * 这是个公开接口，带一个失效的 token 反而可能出问题。
 */
async function startGuest() {
  const result = await http.post<TrialResponse>('/auth/trial', undefined, { skipAuth: true })
  saveSession(result.token, result.user)
  state.isGuest = true
  state.error = ''
  notifyIdentityChanged()
}

/** 主动登出：清掉本地 token，回到访客身份 */
async function logout() {
  clearSession()
  await startGuest()
}

// ---------------------------------------------------------------- 启动

/**
 * 页面启动时调用一次。
 *
 * 顺序：
 *   1. 有本地 token → /auth/me 验证
 *   2. 验证失败或没 token → 创建访客
 *   3. 访客也失败 → 记错误（通常意味着后端没起来）
 */
async function boot() {
  state.booting = true
  state.error = ''

  const hadToken = restoreToken()

  if (hadToken) {
    try {
      // 这里要拿响应头（后端可能在 X-Token-Refresh 里给新 token），
      // 所以不用 http.get，直接 fetch。
      const token = getAuthToken()
      const response = await fetch('/auth/me', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const user = (await response.json()) as User
      state.user = user
      // 访客账号的邮箱有固定后缀，靠它判断身份
      state.isGuest = user.email.endsWith('@ctos-trial.local')

      // 后端说该续期了：换上新 token，用户完全感觉不到
      const refreshed = response.headers.get('X-Token-Refresh')
      if (refreshed) {
        setAuthToken(refreshed)
        try {
          localStorage.setItem(TOKEN_KEY, refreshed)
        } catch {
          // 隐私模式忽略
        }
      }

      state.booting = false
      return
    } catch {
      // token 失效，往下走去创建访客
      clearSession()
    }
  }

  try {
    await startGuest()
  } catch (error) {
    state.error = error instanceof Error ? error.message : '无法连接服务器'
  } finally {
    state.booting = false
  }
}

// token 失效时（后端返回 401）统一处理：清掉并自动回到访客身份
setUnauthorizedHandler(() => {
  if (state.user) {
    clearSession()
    void startGuest().catch(() => {
      state.error = '登录已过期'
    })
  }
})

// ---------------------------------------------------------------- 对外

export const authStore = {
  state,

  isLoggedIn: computed(() => state.user !== null && !state.isGuest),
  displayName: computed(() => state.user?.display_name || '访客'),

  boot,
  login,
  register,
  startGuest,
  logout,

  /** 身份变化时通知（登录 / 注册 / 退出 / 换访客） */
  onIdentityChanged,

  /** 当前 token（调试用） */
  token: () => getAuthToken(),
}
