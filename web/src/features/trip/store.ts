/**
 * 智能出行的状态。
 *
 * 结构：
 *   左边一列出行记录（GET /trip/list，和对话的会话列表是两套数据）
 *   右边一列对话，由若干个 TripTurn 组成
 *
 * 每一轮的形态（CHAT / ROUTE / TRAVEL）由事件决定，不由用户选。
 * 具体的翻译逻辑在 events.ts，这里只负责「发请求 → 收事件 → 更新列表」。
 */
import { computed, reactive } from 'vue'
import type { TripEvent, TripSummary } from '@/shared/types/api'
import type { StreamHandlers } from '@/shared/api/stream'
import { createImageQueue } from '@/shared/lib/imageQueue'
import {
  askTrip,
  choosePlace,
  chooseRoute,
  chooseSpots,
  deleteTrip as apiDeleteTrip,
  deleteTrips as apiDeleteTrips,
  getTrip,
  listTrips,
} from './api'
import {
  createEventApplier,
  createTurn,
  turnFromHistory,
  type TripTurn,
} from './events'

interface State {
  /** 左侧的记录列表 */
  trips: TripSummary[]
  tripsLoading: boolean
  tripsError: string

  /** 右侧当前的对话 */
  currentTripId: number | null
  turns: TripTurn[]

  /** 正在跑（禁用输入） */
  running: boolean
  /** 加载历史轮次中 */
  turnsLoading: boolean
  /** 全局错误 */
  error: string
}

const state = reactive<State>({
  trips: [],
  tripsLoading: false,
  tripsError: '',

  currentTripId: null,
  turns: [],

  running: false,
  turnsLoading: false,
  error: '',
})

/**
 * 待发图片。
 *
 * 出行的识图能力和对话一样：
 *   先 POST /chat/attachment 传图拿 id，
 *   发 /trip/chat 时把 id 放进 image_ids，Agent 就能看到图并据此判断
 *   （比如用户发一张景点的照片问「这地方怎么去」）。
 */
const images = createImageQueue()

/** 当前这条流的中止函数 */
let abort: (() => void) | null = null

// ---------------------------------------------------------------- 记录列表

/**
 * 加载出行记录。
 *
 * silent：静默刷新（跑完一轮后让新记录出现在左边，但不能闪「加载中」）。
 * 这个坑在对话模块踩过一次，这里一次做好。
 */
async function loadTrips(options: { silent?: boolean } = {}) {
  if (!options.silent) {
    state.tripsLoading = true
    state.tripsError = ''
  }

  try {
    state.trips = await listTrips()
  } catch (error) {
    if (!options.silent) {
      state.tripsError = error instanceof Error ? error.message : '出行记录加载失败'
    }
  } finally {
    if (!options.silent) state.tripsLoading = false
  }
}

/** 打开一条历史记录：把每一轮还原成界面状态 */
async function openTrip(tripId: number) {
  stop()

  state.currentTripId = tripId
  state.turns = []
  state.error = ''
  state.turnsLoading = true

  try {
    const detail = await getTrip(tripId)
    state.turns = (detail.turns ?? []).map((t) =>
      reactive(
        turnFromHistory({
          kind: t.turn_kind,
          query: t.user_query,
          aiOutput: t.ai_output,
        }),
      ),
    )
  } catch (error) {
    state.error = error instanceof Error ? error.message : '记录加载失败'
  } finally {
    state.turnsLoading = false
  }
}

/** 新建：清空右侧，等用户说第一句 */
function newTrip() {
  stop()
  state.currentTripId = null
  state.turns = []
  state.error = ''
  images.clear()
}

async function removeTrip(tripId: number) {
  await apiDeleteTrip(tripId)
  state.trips = state.trips.filter((t) => t.id !== tripId)
  if (state.currentTripId === tripId) newTrip()
}

async function removeTrips(ids: number[]) {
  await apiDeleteTrips(ids)
  const removed = new Set(ids)
  state.trips = state.trips.filter((t) => !removed.has(t.id))
  if (state.currentTripId !== null && removed.has(state.currentTripId)) newTrip()
}

// ---------------------------------------------------------------- 跑一轮

/**
 * 通用的「跑一次流」。
 *
 * 四个接口（chat / route/choose / route/place / guide/spots）的事件格式一致，
 * 只有请求体和「要不要新建一轮」不同，所以共用这一个函数。
 *
 * @param start 发起请求的函数，接收 handlers
 * @param turn  这一轮对应的 TripTurn（续流时用同一轮）
 */
function runStream(
  start: (handlers: StreamHandlers) => () => void,
  turn: TripTurn,
) {
  state.running = true
  state.error = ''

  // 每一轮有自己的 applier（内部记着各段的 StreamText）
  const applier = createEventApplier(turn)

  abort = start({
    onEvent: (event) => {
      applier.apply(event as TripEvent)

      // 关键：后端每次落库都会在 CHAT / SAVED / ASK_PLACE 事件里带回 chat_id。
      // 必须同步到 currentTripId，否则下一轮会当成「新会话」，
      // 结果就是同一个会话里的每句话都变成一条独立记录。
      if (turn.savedChatId !== null && turn.savedChatId !== state.currentTripId) {
        state.currentTripId = turn.savedChatId
      }
    },

    onDone: () => {
      applier.finish()

      // 再同步一次：有些路径只发 SAVED，或者 applier.finish 里才定下来
      if (turn.savedChatId !== null) {
        state.currentTripId = turn.savedChatId
      }

      state.running = false
      abort = null
      // 让新记录出现在左边（静默，不闪加载中）
      void loadTrips({ silent: true })
    },

    onError: (error) => {
      turn.error = error.message
      applier.finish()
      state.running = false
      abort = null
    },
  })
}

/** 发一句话给智能出行 */
function ask(query: string) {
  const content = query.trim()
  const imageIds = [...images.ids.value]

  if (state.running) return
  // 有图可以只发图；没图必须有文字
  if (!content && imageIds.length === 0) return

  // 只发图时给个占位文字：后端 query 是必填的
  const finalQuery = content || '（发了一张图片）'

  const turn = reactive(createTurn(finalQuery, imageIds))
  state.turns.push(turn)

  // 图片已经交给这一轮了，清空待发区
  images.clear()

  // history：之前每一轮的用户原话（后端用它理解「改成 8 点」这类追问）
  const history = state.turns
    .slice(0, -1)
    .map((t) => t.query)
    .filter(Boolean)

  runStream(
    (handlers) =>
      askTrip(
        {
          query: finalQuery,
          history,
          chatId: state.currentTripId,
          imageIds,
        },
        handlers,
      ),
    turn,
  )
}

/** 路线：用户选了方案 */
function pickRouteOption(turn: TripTurn, choiceId: string) {
  if (!turn.pending || turn.pending.kind !== 'route') return
  const threadId = turn.pending.threadId

  // 面板收起来，继续跑
  turn.pending = null

  runStream(
    (handlers) =>
      chooseRoute({ threadId, choiceId, chatId: state.currentTripId }, handlers),
    turn,
  )
}

/** 地点有歧义：用户挑了一个 */
function pickPlaceOption(turn: TripTurn, place: string) {
  if (!turn.pending || turn.pending.kind !== 'place') return
  const threadId = turn.pending.threadId
  turn.pending = null

  runStream((handlers) => choosePlace({ threadId, place }, handlers), turn)
}

/** 攻略：用户勾完景点 */
function submitSpots(turn: TripTurn, removed: string[], added: string) {
  if (!turn.pending || turn.pending.kind !== 'spots') return
  const threadId = turn.pending.threadId
  turn.pending = null

  runStream((handlers) => chooseSpots({ threadId, removed, added }, handlers), turn)
}

/** 停止：把当前这一轮的流掐掉 */
function stop() {
  abort?.()
  abort = null
  state.running = false

  const last = state.turns.at(-1)

  // 就算中断了，只要后端已经落过库，也要记住 chat_id，
  // 否则用户接着说话又会变成新记录。
  if (last?.savedChatId != null) {
    state.currentTripId = last.savedChatId
  }

  if (last?.streaming) {
    last.streaming = false
    last.phase = ''
    for (const s of last.sectionStates) {
      if (s.streaming) {
        s.streaming = false
        s.done = true
      }
    }
  }
}

// ---------------------------------------------------------------- 对外

const hasTurns = computed(() => state.turns.length > 0)

/** 当前有没有在等用户操作（有的话输入框要提示） */
const waitingForUser = computed(() =>
  state.turns.some((t) => t.pending !== null),
)

export const tripStore = {
  state,
  hasTurns,
  waitingForUser,

  /** 待发图片队列（和对话共用同一套实现） */
  imageQueue: images,

  loadTrips,
  openTrip,
  newTrip,
  removeTrip,
  removeTrips,

  ask,
  pickRouteOption,
  pickPlaceOption,
  submitSpots,
  stop,
}
