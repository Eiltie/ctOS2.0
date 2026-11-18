/**
 * 闲聊 / 角色扮演的接口调用。
 *
 * 只负责「发请求、拿数据」，不碰界面。页面通过它和 store 打交道，
 * 不会直接写 fetch —— 这样接口有变化时只改这一处。
 *
 * 图片相关的接口在 shared/attachments/api.ts（对话和出行共用），
 * 那个文件不属于任何一个模块。
 */
import { http } from '@/shared/api/http'
import type { ChatMessage, ChatSession } from '@/shared/types/api'

/** GET /sessions —— 本账号的全部会话（闲聊 + 角色，靠 role_id 区分） */
export function listSessions(): Promise<ChatSession[]> {
  return http.get<ChatSession[]>('/sessions')
}

/** GET /sessions/{id}/messages */
export function listMessages(sessionId: number): Promise<ChatMessage[]> {
  return http.get<ChatMessage[]>(`/sessions/${sessionId}/messages`)
}

/** DELETE /sessions/{id} */
export function deleteSession(sessionId: number): Promise<{ deleted: boolean }> {
  return http.delete<{ deleted: boolean }>(`/sessions/${sessionId}`)
}

/**
 * POST /sessions/delete-batch —— 批量删除会话。
 *
 * 为什么用 POST 而不是 DELETE：
 *   DELETE 带请求体不规范，后端也做成了 POST（和出行那边一致）。
 */
export function deleteSessions(ids: number[]): Promise<{ deleted: number }> {
  return http.post<{ deleted: number }>('/sessions/delete-batch', { ids })
}
