/**
 * 后端接口的类型定义 —— 全项目唯一的一份「数据长什么样」。
 *
 * 为什么单独一个文件：
 *   后端返回的字段名是字符串，前端写错一个字母，TypeScript 不会报，
 *   要等用户在浏览器里点开那一页才炸。把字段定义成类型之后：
 *     - 字段名写错 → 编译期就报错
 *     - 后端加了新字段 → 这里补一行，用到的页面立刻有提示
 *     - 后端删了字段 → 这里删掉，所有用它的地方一起报错
 *
 * 和 api/contract.py 的关系：
 *   那份 Python 文件是「声明」，这里是「消费方」。
 *   `npm run check:api` 会去比对两者是否一致；CI 里也会跑。
 *
 * 命名约定：
 *   尽量保持和后端字段**一模一样**（snake_case），不做驼峰转换。
 *   多一层转换就多一处理解偏差，出问题时还要两边对照着看。
 */

// ---------------------------------------------------------------- 认证

export interface User {
  id: number
  email: string
  display_name: string
}

export interface AuthResponse {
  token: string
  user: User
}

/** POST /auth/trial 比普通登录多一个标记，前端靠它显示「访客」字样 */
export interface TrialResponse extends AuthResponse {
  is_trial: boolean
}

// ---------------------------------------------------------------- 闲聊会话

/** GET /sessions 的一条。role_id 有值说明这是角色扮演会话 */
export interface ChatSession {
  id: number
  title: string
  created_at: string
  updated_at: string
  role_id: string | null
}

/**
 * GET /sessions/{id}/messages 的一条。
 * images 里只有图片 id，像素内容要走 GET /chat/attachment/{id}（需要带 token）。
 */
export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  images: number[]
}

// ---------------------------------------------------------------- 图片附件

/** POST /chat/attachment 的返回 */
export interface UploadedImage {
  image_id: number
  mime: string
  bytes: number
  url: string
}

// ---------------------------------------------------------------- 角色扮演

/** 角色卡：列表里用的精简版 */
export interface RoleCard {
  id: string
  name: string
  group: string
  emoji: string
  tagline: string
  opening: string
  /** preset = 内置角色；custom / ai_search = 用户自己的 */
  source?: string
}

/** 完整档案：角色详情页用 */
export interface RoleProfile extends RoleCard {
  age: string
  gender: string
  personality: string
  deeds: string
  background: string
  extra: string
  speaking: string
}

/** POST /roleplay/roles/search 的返回：AI 查出来的草稿，还没存库 */
export interface RoleSearchResult {
  role: RoleProfile
  note: string
}

/** POST /roleplay/start 的返回 */
export interface RoleStartResult {
  session_id: number
  role: RoleCard
  opening: string
  memory: string
}

/** GET /roleplay/session/{id} 的返回。role 为 null 表示这是普通闲聊 */
export interface RoleSessionInfo {
  session_id: number
  role: RoleCard | null
  memory: string
}

// ---------------------------------------------------------------- 智能出行

/**
 * GET /trip/list 的一条。
 * 注意 last_kind 只代表**最后一轮**是什么，不代表整个会话都是那种类型：
 * 同一个会话里可以先后调路线子图、攻略子图、直接回答。
 */
export interface TripSummary {
  id: number
  title: string
  created_at: string
  updated_at: string
  turn_count: number
  /** 空字符串表示还没有轮次 */
  last_kind: TripTurnKind | ''
}

/** 一轮的类型，对应后端的 trip_sessions.turn_kind */
export type TripTurnKind = 'CHAT' | 'ROUTE' | 'TRAVEL'

/**
 * 一轮里 AI 的产出。三组字段各管一摊：
 *   CHAT   → chat_reply
 *   ROUTE  → route_need / route_compare / route_decision / route_tips
 *   TRAVEL → weather / spots / itinerary / advice
 */
export interface TripAiOutput {
  chat_reply: string
  route_need: string
  route_compare: string
  route_decision: string
  route_tips: string
  weather: string
  spots: string
  itinerary: string
  advice: string
}

/** GET /trip/{id} 里 turns[] 的一项 */
export interface TripTurn {
  id: number
  title: string
  turn_kind: TripTurnKind
  destination: string
  days: number
  start_date: string
  user_query: string
  ai_output: TripAiOutput
}

/** GET /trip/{id} 的返回 */
export interface TripDetail {
  id: number
  title: string
  created_at: string
  updated_at: string
  turns: TripTurn[]
}

// ---------------------------------------------------------------- 流式事件

/**
 * 出行的事件（POST /trip/chat、/trip/route/choose、/trip/route/place、/guide/spots）
 *
 * 一条流里会先后出现这些 type，前端要按 type 分派处理。
 * 字段大多是可选的 —— 每种事件只带自己需要的那几个。
 */
export type TripEvent =
  /** 进度提示 / 8 秒心跳。只显示在「正在做什么」，不产生内容 */
  | { kind: 'SAY'; text: string }
  /** Agent 直接回答一个提问。chat_id 是这个回答落库后的会话 id */
  | { kind: 'CHAT'; message: string; chat_id: number | null }
  /** 开始做事。mode=ROUTE 是路线，mode=TRAVEL 是攻略 */
  | { kind: 'START'; mode?: 'ROUTE' | 'TRAVEL'; query?: string }
  /** 进度条走到某一步。key 是步骤名 */
  | { kind: 'STEP'; key: string; text: string }
  /** 逐字推送。key 说明这段字属于哪一段 */
  | { kind: 'TOKEN'; key: string; text: string }
  /** 某一段定稿。key 是哪一段，text 是完整内容 */
  | { kind: 'DONE'; key: string; text: string }
  /** 路线停住，等用户选方案 */
  | {
      kind: 'ASK'
      thread_id: string
      question: string
      options: RouteOption[]
      recommended_id: string
      recommended_name: string
      recommended_text: string
    }
  /** 地名认不准，等用户从候选里挑 */
  | {
      kind: 'ASK_PLACE'
      question: string
      name: string
      options: PlaceOption[]
      chat_id: number | null
      thread_id: string
    }
  /** 攻略停住，等用户勾景点 */
  | {
      kind: 'ASK_SPOTS'
      thread_id: string
      question: string
      spots: string
      spot_names: string[]
    }
  /** 出错了。message 是可以直接给用户看的文案 */
  | { kind: 'ERROR'; message: string }
  /** 这一轮已经落库 */
  | { kind: 'SAVED'; chat_id: number }
  /**
   * AI 生成了一张图（路线示意图 / 行程海报）。
   *
   * 出行这边的生图是「能力补充」：
   * 路线或攻略做完后 Agent 主动问一句，用户说要才画。
   * 取图走 GET /chat/attachment/{image_id}，和用户上传的图同一条路。
   */
  | { kind: 'IMAGE'; image_id: number; chat_id: number | null }

/** ASK 事件里的一条路线候选 */
export interface RouteOption {
  id: string
  /** 方案一 / 方案二 */
  name: string
  /** 一行摘要：打车 · 约44分钟 · 16.7公里 · 约43元 */
  label: string
  /** 补充说明：红绿灯 9 个；畅通 59%… */
  note: string
  /** 结构化的展示信息（后端已经整理好，前端直接画卡片即可） */
  card: RouteOptionCard
  /** 表格行（和 card 内容重复，用哪个都行） */
  row?: RouteOptionRow
  /** 是否是后端推荐的 */
  recommended?: boolean
}

/** 路线方案卡片的展示数据 */
export interface RouteOptionCard {
  /** drive / transit / bus / walk / bike … 决定用什么图标 */
  mode: string
  /** 打车 / 公交 / 地铁 … */
  title: string
  /** 点到点直达 · 不用换乘 */
  desc: string
  minutes: number
  cost: number
  distance: number
  /** 【步行 0.0 公里】【红绿灯 9 个】 */
  facts: string[]
  /** 换乘线路：地铁1号线 → 地铁3号线 → 103路（可能是空串） */
  lines: string
}

export interface RouteOptionRow {
  name: string
  minutes: string
  distance: string
  cost: string
  walk: string
  transfer: string
}

/** ASK_PLACE 事件里的一个地点候选 */
export interface PlaceOption {
  id: string
  label: string
  note: string
}

/** 客服的事件（POST /customer/chat） */
export type CustomerEvent =
  | { kind: 'START' }
  | { kind: 'TOKEN'; text: string }
  | { kind: 'DONE'; text: string }
  | { kind: 'ERROR'; message: string }

// ---------------------------------------------------------------- 其它

export interface Notice {
  id: string
  title: string
  date: string
  version: string
  intro: string
  items: string[]
}

export interface PresenceOnline {
  online: number
  window_minutes: number
}

export interface HealthInfo {
  ok: boolean
  database: string
  user: string
}
