/**
 * 对话状态 —— 会话列表、当前会话的消息、流式发送。
 *
 * 为什么用模块级的 reactive 而不是 Pinia：
 *   当前需求只有「一个模块一份状态」，加一个依赖不划算。
 *   如果以后变成多模块共享复杂状态，再换 Pinia 也只是改这个文件。
 *
 * 对外暴露的都是响应式数据，组件直接解构着用。
 */
import { computed, reactive } from 'vue'
import type { ChatSession } from '@/shared/types/api'
import { createImageQueue } from '@/shared/lib/imageQueue'
import { deleteSession, deleteSessions, listMessages, listSessions } from './api'

export interface UiMessage {
  /** 前端自己的 id，用于列表 key；后端不返回消息 id */
  uid: number
  role: 'user' | 'assistant'
  content: string
  /** 图片 id 列表 */
  images: number[]
  /** 正在流式输出中（用于显示光标/动画） */
  streaming?: boolean
  /** 这一条失败了，附错误文案 */
  error?: string
}

interface State {
  sessions: ChatSession[]
  sessionsLoading: boolean
  sessionsError: string

  currentSessionId: number | null
  messages: UiMessage[]

  /** 正在等回复 */
  streaming: boolean
  /** 流式错误（会显示在页面上） */
  streamError: string

  /**
   * 正在拉某个会话的消息。
   * 和 sessionsLoading 分开：切换会话不该让左侧列表闪，只该让消息区显示骨架。
   */
  messagesLoading: boolean

  /**
   * 当前会话绑定的角色 id（null = 普通闲聊）。
   * 发消息时带上它，后端就走角色扮演分支。
   */
  activeRoleId: string | null
}

/** 待发图片队列（实现在 shared/lib/imageQueue.ts，和出行共用一份逻辑） */
const images = createImageQueue()

const state = reactive<State>({
  sessions: [],
  sessionsLoading: false,
  sessionsError: '',

  currentSessionId: null,
  messages: [],

  streaming: false,
  streamError: '',

  messagesLoading: false,

  activeRoleId: null,
})

/** 设置/清除当前角色（由角色扮演那边在开始会话时调用） */
function setActiveRole(roleId: string | null) {
  state.activeRoleId = roleId
}

/** 消息自增 id */
let uidSeed = 0
const nextUid = () => ++uidSeed

/** 当前正在跑的这条流的中止函数 */
let abortStream: (() => void) | null = null

// ---------------------------------------------------------------- 图片
//
// 实现在 shared/lib/imageQueue.ts，和出行共用同一套逻辑。
// 这里只是把接口名再导一遍，让页面代码不用关心内部结构。

const addImage = images.add
const removeImage = images.remove
const clearImages = images.clear

// ---------------------------------------------------------------- 会话列表

/**
 * 重新拉会话列表。
 *
 * silent：静默刷新。
 *   切换会话时会顺手调一次（让新会话出现在左边），
 *   如果这时把 sessionsLoading 置为 true，左边整个列表会闪成「加载中…」。
 *   用户点一下会话就闪一下，观感很差。所以那类调用用 silent。
 */
async function loadSessions(options: { silent?: boolean } = {}) {
  if (!options.silent) {
    state.sessionsLoading = true
    state.sessionsError = ''
  }

  try {
    state.sessions = await listSessions()
  } catch (error) {
    // 静默刷新失败不打扰用户：保留原来的列表，下一次再试
    if (!options.silent) {
      state.sessionsError = error instanceof Error ? error.message : '会话列表加载失败'
    }
  } finally {
    if (!options.silent) state.sessionsLoading = false
  }
}

async function removeSession(sessionId: number) {
  await deleteSession(sessionId)

  state.sessions = state.sessions.filter((item) => item.id !== sessionId)

  if (state.currentSessionId === sessionId) {
    newChat()
  }
}

/** 批量删除会话，返回实际删掉的数量 */
async function removeSessions(ids: number[]): Promise<number> {
  if (!ids.length) return 0

  const result = await deleteSessions(ids)

  const removed = new Set(ids)
  state.sessions = state.sessions.filter((item) => !removed.has(item.id))

  // 当前正在看的那个被删了，清空右边
  if (state.currentSessionId !== null && removed.has(state.currentSessionId)) {
    newChat()
  }

  return result.deleted
}

// ---------------------------------------------------------------- 当前会话

/**
 * 打开一个会话。
 *
 * 关于角色：
 *   会话是不是角色会话，以「列表里带回来的 role_id」为准。
 *   但有一个例外：刚从角色选择页点卡片进来的新会话，
 *   本地会话列表还没刷新，查不到它的 role_id ——
 *   这时 preserveRole 为 true，保留调用方刚刚设置好的 activeRoleId。
 */
async function openSession(sessionId: number, options: { preserveRole?: boolean } = {}) {
  stopStream()

  state.currentSessionId = sessionId
  state.streamError = ''

  const meta = state.sessions.find((item) => item.id === sessionId)

  if (meta) {
    // 列表里有这条：以它的 role_id 为准（null 就是普通闲聊）
    state.activeRoleId = meta.role_id ?? null
  } else if (!options.preserveRole) {
    // 列表里没有，又不是刚选的角色：当成普通会话
    state.activeRoleId = null
  }
  // 列表里没有、但 preserveRole 为 true：保持调用方设好的值不动

  // 标记「消息正在加载」，界面据此显示骨架，而不是把旧消息抹掉再空一下
  state.messagesLoading = true

  try {
    const rows = await listMessages(sessionId)
    state.messages = rows.map((row) => ({
      uid: nextUid(),
      role: row.role,
      content: row.content,
      images: row.images ?? [],
    }))
  } catch (error) {
    state.messages = []
    state.streamError = error instanceof Error ? error.message : '消息加载失败'
  } finally {
    state.messagesLoading = false
  }

  // 静默刷新列表：
  //   新建的会话要出现在左边，但要刷得看不出来 —— 不能闪「加载中」
  void loadSessions({ silent: true })
}

/** 开一个新会话：不调接口，等用户发出第一句话时后端才建会话 */
function newChat() {
  stopStream()
  state.currentSessionId = null
  state.messages = []
  state.streamError = ''
  state.messagesLoading = false
  clearImages()
}

// ---------------------------------------------------------------- 发送

/**
 * 发一条消息并流式接收回复。
 *
 * 后端的行为（见 api/routes/chat.py）：
 *   - 只返回纯文本流
 *   - 会话 id 在响应头 X-Session-Id 里，不发事件
 *   - 所以新会话要靠这个响应头才知道自己的 id
 *   - 带上 role_id 就走角色扮演分支（后端提示词、温度都不一样）
 *   - 带上 image_ids 就把图片拼进这一轮（先上传拿 id，再发消息）
 *
 * 关于「能只发图不发字」：
 *   后端要求 messages 非空才会处理（ChatRequest.messages 是必填的 str）。
 *   但用户经常只想甩一张图，所以这里给个占位文字，不让用户被卡住。
 */
async function send(text: string, options: { imageIds?: number[]; roleId?: string } = {}) {
  const content = text.trim()
  // 没文字就用待发的图片凑一句提示，避免「只发图」被后端拒绝
  const imageIds = options.imageIds ?? [...images.ids.value]

  if (state.streaming) return
  if (!content && imageIds.length === 0) return

  const finalContent = content || '（发了一张图片）'

  state.streamError = ''

  // 先把用户这句话放进列表，让界面立刻有反应
  state.messages.push({
    uid: nextUid(),
    role: 'user',
    content: finalContent,
    images: [...imageIds],
  })

  // 图片已经交给这条消息了，清空待发区
  // （放在 push 之后：万一 push 前出错，图片不会丢）
  if (!options.imageIds) clearImages()

  // 占一个空的回复气泡，流式内容往里填
  const reply: UiMessage = reactive({
    uid: nextUid(),
    role: 'assistant',
    content: '',
    images: [],
    streaming: true,
  })
  state.messages.push(reply)

  state.streaming = true

  const body: Record<string, unknown> = { messages: finalContent, image_ids: imageIds }
  if (state.currentSessionId !== null) body.session_id = state.currentSessionId
  // 有角色就是角色扮演分支，没有就是普通闲聊
  const roleId = options.roleId ?? state.activeRoleId
  if (roleId) body.role_id = roleId

  await new Promise<void>((resolve) => {
    // 这里需要读响应头，所以不能直接用 streamRequest（它不暴露 headers）。
    // 用 fetch 手动处理，逻辑和 streamRequest 的纯文本分支一致。
    void (async () => {
      try {
        const { getAuthToken } = await import('@/shared/api/http')
        const controller = new AbortController()
        abortStream = () => controller.abort()

        const response = await fetch('/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}),
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(`请求失败（${response.status}）`)
        }

        // 新会话的 id 藏在响应头里
        const headerSessionId = response.headers.get('X-Session-Id')
        if (headerSessionId) {
          const id = Number(headerSessionId)
          if (Number.isFinite(id)) {
            state.currentSessionId = id
            // 列表里还没有这条，刷新一下让新会话出现在左侧
            void loadSessions({ silent: true })
          }
        }

        const reader = response.body?.getReader()
        if (!reader) throw new Error('服务器没有返回内容')

        const decoder = new TextDecoder('utf-8')
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          if (value) reply.content += decoder.decode(value, { stream: true })
        }
        reply.content += decoder.decode()
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          // 用户主动停止：保留已经收到的部分
          return
        }
        reply.error = error instanceof Error ? error.message : '发送失败'
        state.streamError = reply.error
      } finally {
        reply.streaming = false
        state.streaming = false
        abortStream = null
        resolve()
      }
    })()
  })
}

/** 停止生成。已经收到的内容保留 */
function stopStream() {
  abortStream?.()
  abortStream = null
  state.streaming = false
}

// ---------------------------------------------------------------- 对外

export const chatStore = {
  state,

  /** 只读的派生值 */
  currentSession: computed(() =>
    state.sessions.find((item) => item.id === state.currentSessionId),
  ),

  hasMessages: computed(() => state.messages.length > 0),

  loadSessions,
  removeSession,
  removeSessions,
  openSession,
  newChat,
  send,
  stopStream,
  setActiveRole,

  // 图片
  imageQueue: images,
  addImage,
  removeImage,
  clearImages,
}



