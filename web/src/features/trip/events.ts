/**
 * 出行事件处理器 —— 把 11 种 SSE 事件翻译成界面状态。
 *
 * ============================================================================
 * 为什么单独一个文件
 * ============================================================================
 * 出行是这个项目最复杂的模块：一场对话里，每一轮可能是完全不同的三种形态。
 *
 *   CHAT    Agent 直接回答          → 一个气泡
 *   ROUTE   调了路线子图            → 四段卡片 + 选方案面板
 *   TRAVEL  调了攻略子图            → 四段卡片 + 勾景点面板
 *
 * 而且同一轮里会混着来：
 *
 *   SAY         收到，正在理解你的需求…
 *   START       mode=ROUTE，开始走路线
 *   STEP        route_need：正在确认起点和终点…
 *   DONE        route_need：四行需求确认
 *   STEP        route_compare：正在查询候选路线…
 *   ASK         停下来等用户选方案  ← 人要操作
 *   —— 用户选完之后 ——
 *   SAY         按你选的方案，正在整理…
 *   TOKEN/DONE  route_compare / route_decision / route_tips 三段逐字填
 *   SAVED       这一轮已落库
 *
 * 把这些判断散写到组件里，一定会乱。所以全部收在这个纯函数里：
 *   输入：当前这一轮的状态
 *   输出：事件到了，状态该怎么变
 * 组件只负责按状态画出来。
 *
 * ============================================================================
 * 关键设计：一轮（turn）= 一次完整的用户提问 + 所有产出
 * ============================================================================
 * 界面上一轮的形态由「这一轮收到过什么」决定，而不是由用户事先选。
 * 这正是后端的设计：用户不需要选「我要路线还是攻略」。
 */

import type {
  PlaceOption,
  RouteOption,
  TripAiOutput,
  TripEvent,
  TripTurnKind,
} from '@/shared/types/api'
import { StreamText } from '@/shared/lib/typewriter'

/** 路线四段 */
export type RouteSectionKey = 'route_need' | 'route_compare' | 'route_decision' | 'route_tips'
/** 攻略四段 */
export type GuideSectionKey = 'weather' | 'spots' | 'itinerary' | 'advice'

export const ROUTE_SECTIONS: RouteSectionKey[] = [
  'route_need',
  'route_compare',
  'route_decision',
  'route_tips',
]

export const GUIDE_SECTIONS: GuideSectionKey[] = ['weather', 'spots', 'itinerary', 'advice']

/** 卡片的标题（和后端 ROUTE_STEP_TEXT / GUIDE_SECTION_KEYS 对应） */
export const SECTION_LABELS: Record<string, string> = {
  route_need: '需求确认',
  route_compare: '路线对比',
  route_decision: '推荐方案',
  route_tips: '出发提醒',
  weather: '天气',
  spots: '景点清单',
  itinerary: '行程安排',
  advice: '游玩建议',
}

/** 等待用户操作的种类 */
export type PendingAsk =
  | { kind: 'route'; threadId: string; question: string; options: RouteOption[]; recommendedId: string; recommendedText: string }
  | { kind: 'place'; threadId: string; question: string; name: string; options: PlaceOption[] }
  | { kind: 'spots'; threadId: string; question: string; spotNames: string[] }
  | null

/** 一轮里每一段的内容（流式填充中） */
export interface SectionState {
  key: string
  /** 正在流式输出 */
  streaming: boolean
  /** 定稿了 */
  done: boolean
}

/** 界面上的一轮 */
export interface TripTurn {
  /** 前端 id */
  uid: number
  /** 用户的提问 */
  query: string
  /** 这一轮带的图片（id） */
  images: number[]
  /** 这一轮的形态，由收到的事件决定 */
  kind: TripTurnKind
  /** 纯文本回答（CHAT 形态用） */
  chatReply: string
  /** AI 生成的图（路线示意图 / 行程海报）的 id */
  imageIds: number[]
  /** 各段内容：key → 文字 */
  sections: Record<string, string>
  /** 各段状态 */
  sectionStates: SectionState[]
  /** 当前在做什么（STEP 的 text / SAY 的 text） */
  phase: string
  /**
   * 路线/攻略跑完后 Agent 的补充说明（比如「要不要生成一张图」）。
   *
   * 为什么单独一个字段：
   *   它出现在四段卡片都完成之后，不算「正在做什么」，
   *   也不该把整轮变成 CHAT 形态（那样卡片和等待面板就没了）。
   *   放在这里，由卡片末尾单独渲染。
   */
  closingNote: string
  /** 进度：点亮到第几步（按 sections 的顺序算） */
  progress: number
  /** 停下来等用户操作 */
  pending: PendingAsk
  /** 正在流式接收 */
  streaming: boolean
  /** 已落库的会话 id */
  savedChatId: number | null
  /** 错误 */
  error: string
}

let uidSeed = 0
const nextUid = () => ++uidSeed

/** 新建一轮 */
export function createTurn(query: string, imageIds: number[] = []): TripTurn {
  return {
    uid: nextUid(),
    query,
    images: [...imageIds],
    kind: 'CHAT',
    chatReply: '',
    imageIds: [],
    sections: {},
    sectionStates: [],
    phase: '收到，正在理解你的需求…',
    closingNote: '',
    progress: 0,
    pending: null,
    streaming: true,
    savedChatId: null,
    error: '',
  }
}

/**
 * 把一轮从「历史记录」还原成界面状态。
 *
 * 从 GET /trip/{id} 拿到的 ai_output 里，四段已经是定稿的字符串。
 * 这里把它转成和实时流一样的结构，这样回放和历史共用同一套渲染。
 */
export function turnFromHistory(input: {
  kind: TripTurnKind
  query: string
  aiOutput: TripAiOutput
}): TripTurn {
  const { kind, query, aiOutput } = input

  const turn = createTurn(query)
  turn.streaming = false
  turn.phase = ''
  turn.kind = kind

  // 注意：出行这边图片只用于「让 Agent 当轮判断」，不落库到消息表
  // （后端 api/routes/trip.py 的 resolve_images 只取路径，不认领）。
  // 所以历史回放时没有图片可显示，这是后端的设计，不是前端遗漏。

  if (kind === 'CHAT') {
    turn.chatReply = aiOutput.chat_reply || ''
    return turn
  }

  // ROUTE 和 TRAVEL 都是四段，只是 key 不同
  const keys = kind === 'ROUTE' ? ROUTE_SECTIONS : GUIDE_SECTIONS

  for (const key of keys) {
    const text = (aiOutput as unknown as Record<string, string>)[key] ?? ''
    if (!text) continue
    turn.sections[key] = text
    turn.sectionStates.push({ key, streaming: false, done: true })
  }

  turn.progress = turn.sectionStates.length
  return turn
}

/**
 * 事件处理器的核心。
 *
 * 用法：
 *   const applier = createEventApplier(turn)
 *   handlers.onEvent = applier.apply
 *
 * 它是**有状态**的：要在内部记住每一段的 StreamText（用来合并 TOKEN 和 DONE）。
 * 每次开始一轮就新建一个。
 */
export function createEventApplier(turn: TripTurn) {
  /** 每段的流式文字（TOKEN 累加、DONE 覆盖） */
  const streams = new Map<string, StreamText>()

  function streamOf(key: string): StreamText {
    let s = streams.get(key)
    if (!s) {
      s = new StreamText()
      streams.set(key, s)
    }
    return s
  }

  /** 某段开始出现（STEP 或第一个 TOKEN 时） */
  function ensureSection(key: string) {
    if (turn.sectionStates.some((s) => s.key === key)) return
    turn.sectionStates.push({ key, streaming: true, done: false })
  }

  /** 某段完成（DONE 时） */
  function finishSection(key: string, text: string) {
    ensureSection(key)
    const state = turn.sectionStates.find((s) => s.key === key)
    if (state) {
      state.streaming = false
      state.done = true
    }
    turn.sections[key] = text
    turn.progress = turn.sectionStates.filter((s) => s.done).length
  }

  function apply(event: TripEvent) {
    switch (event.kind) {
      // ---------------- 进度说明 ----------------
      case 'SAY':
        // 心跳（后端每 8 秒发一次「仍在处理中」）也走这里。
        // 有等待面板时不要覆盖它，否则用户会以为面板没了。
        if (!turn.pending) turn.phase = event.text
        break

      // ---------------- 开始 ----------------
      case 'START':
        // mode 决定这一轮是路线还是攻略
        if (event.mode === 'ROUTE') turn.kind = 'ROUTE'
        else if (event.mode === 'TRAVEL') turn.kind = 'TRAVEL'
        break

      // ---------------- 直接回答 ----------------
      case 'CHAT':
        // 注意：CHAT 事件有两种用途 ——
        //   1) 这一轮本来就是「直接回答」→ 改形态成 CHAT
        //   2) 路线/攻略跑完后，Agent 主动提议「要不要生成一张图」
        //      → 这时形态已经是 ROUTE/TRAVEL，**不能**改回 CHAT，
        //        否则四段卡片和等待面板（选方案/勾景点）会被整个切走。
        if (turn.kind === 'CHAT') {
          turn.chatReply = event.message
          turn.phase = ''
        } else {
          // 已经进入路线/攻略：这条是跑完后的补充说明（比如「要不要生成一张图」）。
          // 记到 closingNote，卡片末尾单独显示，形态和面板都不动。
          turn.closingNote = event.message
        }
        // 后端在这里告诉我们这条记录落在哪个 chat_id 上。
        // 必须记下来 —— 否则下一轮会当成新会话，每句话都会变成一个独立记录。
        if (typeof event.chat_id === 'number' && event.chat_id !== null) {
          turn.savedChatId = event.chat_id
        }
        break

      // ---------------- 进度条 ----------------
      case 'STEP':
        ensureSection(event.key)
        turn.phase = event.text
        break

      // ---------------- 流式文字 ----------------
      case 'TOKEN': {
        ensureSection(event.key)
        const s = streamOf(event.key)
        s.push(event.text)
        turn.sections[event.key] = s.text
        break
      }

      // ---------------- 某段定稿 ----------------
      case 'DONE': {
        const s = streamOf(event.key)
        s.finish(event.text)
        finishSection(event.key, s.text)
        break
      }

      // ---------------- 停下来等人 ----------------
      case 'ASK':
        turn.pending = {
          kind: 'route',
          threadId: event.thread_id,
          question: event.question,
          options: event.options ?? [],
          recommendedId: event.recommended_id ?? '',
          recommendedText: event.recommended_text ?? '',
        }
        turn.phase = ''
        break

      case 'ASK_PLACE':
        turn.pending = {
          kind: 'place',
          threadId: event.thread_id ?? '',
          question: event.question,
          name: event.name,
          options: event.options ?? [],
        }
        if (typeof event.chat_id === 'number' && event.chat_id !== null) {
          turn.savedChatId = event.chat_id
        }
        turn.phase = ''
        break

      case 'ASK_SPOTS':
        turn.pending = {
          kind: 'spots',
          threadId: event.thread_id,
          question: event.question,
          spotNames: event.spot_names ?? [],
        }
        turn.phase = ''
        break

      // ---------------- 收尾 ----------------
      case 'SAVED':
        turn.savedChatId = event.chat_id
        turn.phase = ''
        break

      // ---------------- 生成的图 ----------------
      case 'IMAGE':
        // 出行这边生图是「能力补充」：
        // 路线/攻略做完后 Agent 主动问，用户说要才画。
        //
        // 注意：不把 kind 改成 CHAT ——
        // 这一轮的卡片和面板要保留，图只是额外挂上去的东西。
        // 之前改成 CHAT 会把用户正在看的选方案面板弄没。
        if (!turn.imageIds.includes(event.image_id)) {
          turn.imageIds.push(event.image_id)
        }
        if (typeof event.chat_id === 'number' && event.chat_id !== null) {
          turn.savedChatId = event.chat_id
        }
        break

      case 'ERROR':
        turn.error = event.message
        break
    }
  }

  /** 流结束时收尾：没定稿的段也标记完成 */
  function finish() {
    turn.streaming = false
    turn.phase = ''

    for (const state of turn.sectionStates) {
      if (state.streaming) {
        state.streaming = false
        state.done = true
      }
    }

    // 没有内容也没有等待面板 → 给个提示，避免空白
    const hasContent =
      turn.chatReply.length > 0 ||
      Object.values(turn.sections).some((t) => t.length > 0) ||
      turn.pending !== null

    if (!hasContent && !turn.error) {
      turn.error = '这次没有收到内容，换个说法再试'
    }
  }

  return { apply, finish }
}

