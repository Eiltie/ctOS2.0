/**
 * 智能出行的接口调用。
 *
 * 四个流式接口 + 会话管理：
 *   POST /trip/chat            唯一入口（Agent 自己判断走哪条路）
 *   POST /trip/route/choose    路线停在选方案 → 用户选完继续
 *   POST /trip/route/place     地点有歧义 → 用户挑完继续
 *   POST /guide/spots          攻略停在勾景点 → 用户勾完继续
 *
 * 四个接口的事件格式完全一致（都是 SSE + kind 字段），
 * 所以这里只需要包一层 streamRequest，不同点只在请求体。
 */
import { http } from '@/shared/api/http'
import { streamRequest, type StreamHandlers } from '@/shared/api/stream'
import type { TripDetail, TripSummary } from '@/shared/types/api'

/** GET /trip/list —— 出行记录（和对话的会话列表是两套数据） */
export function listTrips(): Promise<TripSummary[]> {
  return http.get<TripSummary[]>('/trip/list')
}

/** GET /trip/{id} —— 一个会话的全部轮次 */
export function getTrip(tripId: number): Promise<TripDetail> {
  return http.get<TripDetail>(`/trip/${tripId}`)
}

/** DELETE /trip/{id} */
export function deleteTrip(tripId: number): Promise<{ deleted: boolean }> {
  return http.delete<{ deleted: boolean }>(`/trip/${tripId}`)
}

/**
 * POST /trip/delete-batch —— 批量删除。
 *
 * 为什么用 POST 而不是 DELETE：
 *   DELETE 带请求体不规范，后端也把批量删做成了 POST（见 api/routes/trip.py）。
 */
export function deleteTrips(ids: number[]): Promise<{ deleted: number }> {
  return http.post<{ deleted: number }>('/trip/delete-batch', { ids })
}

// ---------------------------------------------------------------- 流式

/** 发一句话给智能出行。这是唯一入口，不需要用户选「路线」还是「攻略」 */
export function askTrip(
  input: {
    query: string
    history: string[]
    chatId: number | null
    imageIds: number[]
  },
  handlers: StreamHandlers,
): () => void {
  const body: Record<string, unknown> = {
    query: input.query,
    history: input.history,
    image_ids: input.imageIds,
  }
  // 不传 = 新开一个出行会话
  if (input.chatId !== null) body.chat_id = input.chatId

  return streamRequest('/trip/chat', body, 'sse', handlers)
}

/** 路线停住等用户选方案 → 选完继续把对比、推荐、提醒写完 */
export function chooseRoute(
  input: { threadId: string; choiceId: string; chatId: number | null },
  handlers: StreamHandlers,
): () => void {
  const body: Record<string, unknown> = {
    thread_id: input.threadId,
    choice_id: input.choiceId,
  }
  if (input.chatId !== null) body.chat_id = input.chatId

  return streamRequest('/trip/route/choose', body, 'sse', handlers)
}

/** 地名认不准 → 用户从候选里挑一个，从原来的需求接着查 */
export function choosePlace(
  input: { threadId: string; place: string },
  handlers: StreamHandlers,
): () => void {
  return streamRequest(
    '/trip/route/place',
    { thread_id: input.threadId, place: input.place },
    'sse',
    handlers,
  )
}

/** 攻略停在勾景点 → 用户勾完继续排行程、写游玩建议 */
export function chooseSpots(
  input: { threadId: string; removed: string[]; added: string },
  handlers: StreamHandlers,
): () => void {
  return streamRequest(
    '/guide/spots',
    { thread_id: input.threadId, removed: input.removed, added: input.added },
    'sse',
    handlers,
  )
}
