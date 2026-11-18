/**
 * HTTP 客户端 —— 所有接口请求都从这里走。
 *
 * 它统一处理三件事，避免每个页面各写一遍：
 *   1. 带上登录 token（Authorization: Bearer）
 *   2. 把后端的错误（HTTPException 的 detail）变成能直接显示的中文文案
 *   3. token 失效（401）时通知上层跳去登录，而不是让每个页面自己判断
 *
 * 为什么不用 axios：
 *   零依赖，fetch 已经够用；流式请求本来就要手写，多加一个库没必要。
 */

/** 后端返回的错误。status 是 HTTP 状态码，message 是可以直接给用户看的文案 */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** 401 时调这里。在 main.ts 里注册，避免网络层直接依赖路由和状态管理 */
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler
}

/** token 存在这里；登录/退登时由 auth store 更新 */
let authToken: string | null = null

export function setAuthToken(token: string | null): void {
  authToken = token
}

export function getAuthToken(): string | null {
  return authToken
}

/** 给请求加认证头。返回新对象，不改调用方传进来的那个 */
function withAuth(headers?: HeadersInit): HeadersInit {
  const merged: Record<string, string> = {}
  if (headers) {
    new Headers(headers).forEach((value, key) => {
      merged[key] = value
    })
  }
  if (authToken) {
    merged['Authorization'] = `Bearer ${authToken}`
  }
  return merged
}

/**
 * 从响应里抠出错误文案。
 *
 * 后端的报错统一是 {"detail": "..."}（FastAPI 的 HTTPException），
 * 偶尔会是 {"detail": [{"msg": ...}]}（pydantic 参数校验失败）。
 * 两种都兜住，实在解析不了就显示状态码。
 */
async function readError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown }
    const detail = data?.detail

    if (typeof detail === 'string') return detail

    // pydantic 校验错误是数组，取每条的 msg
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => (typeof item === 'object' && item && 'msg' in item ? String(item.msg) : ''))
        .filter(Boolean)
      if (messages.length) return messages.join('；')
    }
  } catch {
    // 不是 JSON（比如网关返回的 HTML），走下面的兜底
  }

  return `请求失败（${response.status}）`
}

/** 发一个请求并解析 JSON。失败抛 ApiError */
export async function request<T>(
  path: string,
  options: RequestInit & { skipAuth?: boolean } = {},
): Promise<T> {
  const { skipAuth, ...rest } = options
  const headers = skipAuth ? (rest.headers ?? {}) : withAuth(rest.headers)
  let response: Response
  try {
    response = await fetch(path, { ...rest, headers })
  } catch (error) {
    // 网络断了、后端没起来，都是这一类
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, '连不上服务器，请检查网络或后端是否已启动')
  }

  if (response.status === 401) {
    onUnauthorized?.()
    throw new ApiError(401, await readError(response))
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readError(response))
  }

  // 204 没有内容
  if (response.status === 204) return undefined as T

  return (await response.json()) as T
}

/** 便捷方法 */
export const http = {
  get: <T>(path: string, options?: RequestInit & { skipAuth?: boolean }) =>
    request<T>(path, { ...options, method: 'GET' }),

  post: <T>(path: string, body?: unknown, options?: RequestInit & { skipAuth?: boolean }) =>
    request<T>(path, {
      ...options,
      method: 'POST',
      headers:
        body === undefined
          ? options?.headers
          : { 'Content-Type': 'application/json', ...options?.headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),

  delete: <T>(path: string, options?: RequestInit & { skipAuth?: boolean }) =>
    request<T>(path, { ...options, method: 'DELETE' }),

  /**
   * 带认证地取二进制内容（图片用）。
   * <img src> 没法带请求头，所以图片要先 fetch 成 blob 再转 objectURL。
   */
  async blob(path: string, signal?: AbortSignal): Promise<Blob> {
    const response = await fetch(path, { headers: withAuth(), signal })

    if (response.status === 401) {
      onUnauthorized?.()
      throw new ApiError(401, '请重新登录')
    }
    if (!response.ok) {
      throw new ApiError(response.status, await readError(response))
    }

    return await response.blob()
  },
}
