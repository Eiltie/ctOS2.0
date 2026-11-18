/**
 * 流式读取 —— 后端有 6 个接口返回流，但格式并不一样。
 *
 *   纯文本流（POST /chat）
 *     每收到一段就是一个字符串，没有 JSON 包壳。
 *     这一轮的会话 id 在响应头 X-Session-Id 里。
 *
 *   事件流（/trip/chat、/trip/route/choose、/trip/route/place、
 *          /guide/spots、/customer/chat）
 *     后端按 SSE 格式发：每行 "data: {...}"，一条事件以空行结束。
 *     事件的类型看 JSON 里的 kind 字段。
 *
 * 这个文件只负责「把字节流切成一条条消息」，不认识业务语义。
 * 业务语义（哪条事件该干什么）由 features/*\/stream.ts 处理 —— 这样分工，
 * 以后后端加一种事件，只会动业务那层，不会碰这里。
 */

/** 事件流里的一条。data 是已经解析好的对象 */
export interface StreamEvent {
  kind: string
  [key: string]: unknown
}

export interface StreamHandlers {
  /** 收到一条事件流事件 */
  onEvent?: (event: StreamEvent) => void
  /** 纯文本流收到一段文字 */
  onText?: (chunk: string) => void
  /** 流正常结束 */
  onDone?: () => void
  /** 出错（网络断开、后端报错、解析失败） */
  onError?: (error: Error) => void
}

/**
 * 发一个流式请求并逐块读取。
 *
 * 为什么手写而不是用 EventSource：
 *   EventSource 只支持 GET，而这几个接口都是 POST 带 JSON 请求体。
 *   所以只能 fetch + ReadableStream 手工解析。
 *
 * 返回值是中止函数：用户点「停止生成」或者切走页面时调用它。
 */
export function streamRequest(
  path: string,
  body: unknown,
  format: 'text' | 'sse',
  handlers: StreamHandlers,
): () => void {
  const controller = new AbortController()

  void (async () => {
    try {
      const response = await fetch(path, {
        method: 'POST',
        headers: buildHeaders(),
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!response.ok) {
        throw new Error(await readStreamError(response))
      }

      if (!response.body) {
        throw new Error('服务器没有返回内容')
      }

      if (format === 'text') {
        await readTextStream(response, handlers)
      } else {
        await readSseStream(response, handlers)
      }

      handlers.onDone?.()
    } catch (error) {
      // 用户主动中止不算错误，不弹提示
      if (error instanceof DOMException && error.name === 'AbortError') {
        handlers.onDone?.()
        return
      }
      handlers.onError?.(error instanceof Error ? error : new Error(String(error)))
    }
  })()

  return () => controller.abort()
}

/** 从 token 存取处拿认证头。放在这里避免和 http.ts 互相 import */
let tokenProvider: (() => string | null) | null = null

export function setStreamTokenProvider(provider: () => string | null): void {
  tokenProvider = provider
}

function buildHeaders(): HeadersInit {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = tokenProvider?.()
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

/** 流式请求失败时，响应体可能是一段 JSON 报错，尽量把中文文案拿出来 */
async function readStreamError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown }
    if (typeof data?.detail === 'string') return data.detail
  } catch {
    // 忽略
  }
  if (response.status === 401) return '登录已过期，请重新登录'
  return `请求失败（${response.status}）`
}

/** 纯文本流：直接切字符串 */
async function readTextStream(response: Response, handlers: StreamHandlers): Promise<void> {
  const reader = response.body!.getReader()
  const decoder = new TextDecoder('utf-8')

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    if (value) {
      const text = decoder.decode(value, { stream: true })
      if (text) handlers.onText?.(text)
    }
  }

  // 把解码器里剩下的补出来
  const tail = decoder.decode()
  if (tail) handlers.onText?.(tail)
}

/**
 * 事件流：按 SSE 规则切。
 *
 * 一条事件长这样（后端 common/sse.py 的 sse() 生成的）：
 *     data: {"kind":"TOKEN","key":"weather","text":"晴"}\n\n
 *
 * 要注意的坑：
 *   一个网络分片不一定正好切在事件边界上，
 *   可能收到半行，也可能一次收到三条。所以必须自己缓冲、按空行切。
 */
async function readSseStream(response: Response, handlers: StreamHandlers): Promise<void> {
  const reader = response.body!.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    if (!value) continue

    buffer += decoder.decode(value, { stream: true })

    // SSE 用空行分隔事件；把完整的事件切出来，剩下的留在 buffer 里等下一块
    let boundary = findBoundary(buffer)
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary.start)
      buffer = buffer.slice(boundary.end)

      const event = parseSseBlock(raw)
      if (event) handlers.onEvent?.(event)

      boundary = findBoundary(buffer)
    }
  }

  // 收尾：有些情况下最后一条没有以空行结束
  const rest = buffer.trim()
  if (rest) {
    const event = parseSseBlock(rest)
    if (event) handlers.onEvent?.(event)
  }
}

/** 找出下一个事件分隔位置。\n\n 或 \r\n\r\n 都算 */
function findBoundary(buffer: string): { start: number; end: number } | -1 {
  const lf = buffer.indexOf('\n\n')
  const crlf = buffer.indexOf('\r\n\r\n')

  if (lf === -1 && crlf === -1) return -1
  if (crlf !== -1 && (lf === -1 || crlf < lf)) {
    return { start: crlf, end: crlf + 4 }
  }
  return { start: lf, end: lf + 2 }
}

/** 解析一个事件块：取出所有 data: 行，拼起来再当 JSON 解析 */
function parseSseBlock(raw: string): StreamEvent | null {
  const dataLines: string[] = []

  for (const line of raw.split(/\r?\n/)) {
    if (!line.startsWith('data:')) continue
    dataLines.push(line.slice(5).trimStart())
  }

  if (!dataLines.length) return null

  const payload = dataLines.join('\n')

  // 后端约定：事件结束时发 [DONE] 字样（当前没有用到，留着兼容）
  if (payload === '[DONE]') return null

  try {
    const parsed = JSON.parse(payload) as StreamEvent
    if (!parsed || typeof parsed !== 'object' || typeof parsed.kind !== 'string') {
      return null
    }
    return parsed
  } catch {
    // 半截 JSON 不应该出现（已经按空行切开了），真出现了就丢掉这条
    console.warn('[sse] 无法解析的事件：', payload.slice(0, 200))
    return null
  }
}
