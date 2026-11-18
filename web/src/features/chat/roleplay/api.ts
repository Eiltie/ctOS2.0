/**
 * 角色扮演的接口调用。
 *
 * 和后端 api/routes/roleplay.py 一一对应。
 * 角色扮演不是独立模块 —— 它复用闲聊的会话表，
 * 所以这里只负责「角色」相关的事，发消息仍然走 chat/api.ts 的 /chat。
 */
import { http } from '@/shared/api/http'
import type {
  RoleCard,
  RoleProfile,
  RoleSearchResult,
  RoleSessionInfo,
  RoleStartResult,
} from '@/shared/types/api'

/** GET /roleplay/roles —— 预设角色 + 我创建的角色 */
export async function listRoles(): Promise<RoleCard[]> {
  const data = await http.get<{ roles: RoleCard[] }>('/roleplay/roles')
  return data.roles ?? []
}

/** GET /roleplay/roles/{id} —— 完整档案（性格、事迹、背景这些） */
export async function getRoleProfile(roleId: string): Promise<RoleProfile> {
  const data = await http.get<{ role: RoleProfile }>(
    `/roleplay/roles/${encodeURIComponent(roleId)}`,
  )
  return data.role
}

/**
 * 新建自定义角色。
 *
 * 后端可以直接创建，也可以传 AI 查出来的草稿（source=ai_search）。
 * 注意：开场白可以写在 extra 里（格式「开场白：xxx」），
 * 没写的话后端会让模型生成一句。
 */
export async function createRole(input: {
  name: string
  age?: string
  gender?: string
  personality?: string
  deeds?: string
  background?: string
  extra?: string
  emoji?: string
  tagline?: string
  speaking?: string
  source?: 'custom' | 'ai_search'
}): Promise<RoleCard> {
  const data = await http.post<{ role: RoleCard }>('/roleplay/roles', input)
  return data.role
}

/** DELETE /roleplay/roles/{id} —— 只能删自己创建的（custom_ 开头的 id） */
export async function deleteRole(roleId: string): Promise<void> {
  await http.delete(`/roleplay/roles/${encodeURIComponent(roleId)}`)
}

/**
 * POST /roleplay/roles/search —— 「AI 帮我查」
 *
 * 后端会联网搜资料再整理成档案草稿，比较慢（十几秒），
 * 所以界面上要有明确的等待提示。
 */
export function searchRole(query: string): Promise<RoleSearchResult> {
  return http.post<RoleSearchResult>('/roleplay/roles/search', { query })
}

/** POST /roleplay/start —— 选一个角色开始聊，后端会建会话并写入开场白 */
export function startRole(roleId: string): Promise<RoleStartResult> {
  return http.post<RoleStartResult>('/roleplay/start', { role_id: roleId })
}

/** GET /roleplay/session/{id} —— 这个会话是哪个角色（role 为 null 就是普通闲聊） */
export function getSessionRole(sessionId: number): Promise<RoleSessionInfo> {
  return http.get<RoleSessionInfo>(`/roleplay/session/${sessionId}`)
}

/** GET /roleplay/memory/{id} —— 这个角色记住了什么 */
export async function getMemory(roleId: string): Promise<string> {
  const data = await http.get<{ role_id: string; memory: string }>(
    `/roleplay/memory/${encodeURIComponent(roleId)}`,
  )
  return data.memory ?? ''
}

/** POST /roleplay/memory/clear —— 清空记忆 */
export function clearMemory(roleId: string): Promise<{ ok: boolean }> {
  return http.post<{ ok: boolean }>('/roleplay/memory/clear', { role_id: roleId })
}
