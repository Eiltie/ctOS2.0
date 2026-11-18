/**
 * 智能客服的状态。
 *
 * 和闲聊 store 的最大区别：**这里的东西全在内存里**。
 *   后端不存会话、不存消息，刷新就没了。
 *   所以不需要 currentSessionId、不需要会话列表，只有一条消息流。
 *
 * 事件处理：
 *   后端发 4 种事件（START / TOKEN / DONE / ERROR）。
 *   TOKEN 是逐字推送，DONE 是定稿。两者可能同时出现 ——
 *   固定话术（寒暄、拒答）会把整段补发成 TOKEN，再发 DONE 全文。
 *   合并规则和闲聊一致：有 DONE 就以 DONE 为准，避免文字重复。
 */
import { computed, reactive } from 'vue'
import type { CustomerEvent } from '@/shared/types/api'
import { StreamText } from '@/shared/lib/typewriter'
import { askCustomer, buildHistory, type CustomerHistoryItem } from './api'

export interface CustomerMessage {
  uid: number
  role: 'user' | 'assistant'
  content: string
  /** 正在流式输出 */
  streaming?: boolean
  /** 失败了的文案 */
  error?: string
  /** 这一条是「正在检索」之类的中间提示，不是正式回答 */
  hint?: boolean
}

interface State {
  messages: CustomerMessage[]
  /** 正在等回答（禁用输入、显示停止按钮） */
  asking: boolean
  /** 当前在做什么（START 之后显示「正在检索资料…」） */
  phase: string
  /** 全局错误 */
  error: string
}

const state = reactive<State>({
  messages: [],
  asking: false,
  phase: '',
  error: '',
})

let uidSeed = 0
const nextUid = () => ++uidSeed

/** 当前这条流的中止函数 */
let abortAsk: (() => void) | null = null

/**
 * 发一个问题。
 *
 * 流程：
 *   1. 把用户问题显示出来
 *   2. 占一个空的回答气泡
 *   3. 订阅事件，累进气泡
 */
function ask(query: string) {
  const content = query.trim()
  if (!content || state.asking) return

  state.error = ''
  state.phase = '正在检索资料…'

  // 用户的问题
  state.messages.push({ uid: nextUid(), role: 'user', content })

  // 回答气泡（空壳，边流边填）
  const reply: CustomerMessage = reactive({
    uid: nextUid(),
    role: 'assistant',
    content: '',
    streaming: true,
  })
  state.messages.push(reply)

  state.asking = true

  // 历史只带「之前的」问答 —— 不含刚刚 push 进去的这条
  const history: CustomerHistoryItem[] = buildHistory(
    state.messages.slice(0, -2).map((m) => ({ role: m.role, content: m.content })),
  )

  // 这一段文字用 StreamText 合并：TOKEN 累加，DONE 覆盖
  const text = new StreamText()

  abortAsk = askCustomer(content, history, {
    onEvent: (raw) => {
      const event = raw as CustomerEvent

      switch (event.kind) {
        case 'START':
          // 后端开始跑了。保持「正在检索」提示，等第一个字到了再撤掉
          break

        case 'TOKEN':
          text.push(event.text)
          reply.content = text.text
          state.phase = ''
          break

        case 'DONE':
          text.finish(event.text)
          reply.content = text.text
          reply.streaming = false
          state.phase = ''
          break

        case 'ERROR':
          reply.error = event.message
          reply.streaming = false
          state.phase = ''
          break
      }
    },

    onError: (error) => {
      reply.error = error.message
      reply.streaming = false
    },

    onDone: () => {
      reply.streaming = false
      state.asking = false
      state.phase = ''
      abortAsk = null

      // 一个字的回答都没收到，也没报错：说明真出问题了
      if (!reply.content && !reply.error) {
        reply.error = '这次没有收到回答，请再问一次'
      }
    },
  })
}

/** 停止生成：已收到的内容保留 */
function stop() {
  abortAsk?.()
  abortAsk = null
  state.asking = false
  state.phase = ''

  const last = state.messages.at(-1)
  if (last?.streaming) {
    last.streaming = false
    if (!last.content) last.error = '已停止'
  }
}

/** 清空对话（界面上的「清空对话」按钮）。没有服务端要清，只是本地清空 */
function clear() {
  stop()
  state.messages = []
  state.error = ''
  state.phase = ''
}

/** 有没有对话内容 */
const hasMessages = computed(() => state.messages.length > 0)

export const customerStore = {
  state,
  hasMessages,
  ask,
  stop,
  clear,
}
