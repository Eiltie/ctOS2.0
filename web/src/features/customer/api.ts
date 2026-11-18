/**
 * 智能客服的接口调用。
 *
 * 只有一个接口：POST /customer/chat，返回 SSE 事件流。
 *
 * 和闲聊的关键区别：
 *   客服**不写数据库**。后端不存会话、不存消息，
 *   所以刷新页面上下文就没了 —— 界面上要明确告诉用户这一点。
 *
 * 上下文怎么保持：
 *   完全靠前端把最近的问答带上去（history 参数）。
 *   后端只取最近 3 轮（见 modules/customer/node.py 的 HISTORY_TURNS）。
 */
import { streamRequest, type StreamHandlers } from '@/shared/api/stream'
import type { CustomerEvent } from '@/shared/types/api'

/** 一问一答。后端 _format_history 读的字段就是 role 和 content */
export interface CustomerHistoryItem {
  role: 'user' | 'assistant'
  content: string
}

/**
 * 把最近几轮拼成 history 参数。
 *
 * 为什么在这里截断而不是全传：
 *   后端自己也会截到最近 3 轮，但传太多会让请求体变大。
 *   在前端先截一次，省点带宽。
 */
export function buildHistory(
  messages: { role: 'user' | 'assistant'; content: string }[],
  turns = 3,
): CustomerHistoryItem[] {
  return messages
    .filter((m) => m.content.trim().length > 0)
    .slice(-turns * 2)
    .map((m) => ({ role: m.role, content: m.content }))
}

/**
 * 发一个问题，流式接收回答。
 *
 * 返回中止函数，用户点「停止」时调用。
 */
export function askCustomer(
  query: string,
  history: CustomerHistoryItem[],
  handlers: StreamHandlers,
): () => void {
  return streamRequest('/customer/chat', { query, history }, 'sse', handlers)
}

/** 把后端来的原始事件收窄成具体类型（仅用于类型提示，运行时不做校验） */
export type { CustomerEvent }
