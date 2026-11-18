/**
 * 导航结构 —— 顶栏有哪些模块、每个模块有哪些玩法，都写在这里。
 *
 * 为什么单独一个文件：
 *   顶栏、左侧列表、玩法条都要知道这些信息。
 *   集中定义一处，以后加模块/加玩法只改这里，不用在三个组件里各找一遍。
 *
 * 加一个玩法（例如「语音陪练」）要改的：
 *   1. 这里 MODULES.chat.modes 加一项
 *   2. features/chat/ 下建对应的页面组件
 *   3. router.ts 加一条子路由
 */
import type { Component } from 'vue'

export interface ModeDef {
  /** 路由名，对应 router.ts 里 chat 的子路由 */
  route: string
  /** 玩法条上显示的名字 */
  label: string
  /** 玩法条上的图标 */
  icon: string
  /** 还没做出来时设为 true，界面上是灰的 */
  soon?: boolean
}

export interface ModuleDef {
  /** 路由前缀 */
  path: string
  label: string
  /** 顶栏图标 */
  icon: Component | string
  /** 这个模块下的玩法。空数组表示没有玩法概念（出行、客服就是这样） */
  modes: ModeDef[]
}

/**
 * 对话模块的玩法。
 *
 * 角色扮演是「对话」下面的一个玩法，不是独立模块——
 * 后端的角色会话也复用闲聊的会话表，关系是一致的。
 */
const CHAT_MODES: ModeDef[] = [
  { route: 'chat', label: '闲聊', icon: '💬' },
  { route: 'chat-roles', label: '角色扮演', icon: '🎭' },
]

/** 顶栏的三个模块 */
export const MODULES: ModuleDef[] = [
  {
    path: '/chat',
    label: '对话',
    icon: 'M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.8-.8L3 20.5l1.4-4.1A8.4 8.4 0 0 1 12 3.1a8.4 8.4 0 0 1 9 8.4z',
    modes: CHAT_MODES,
  },
  {
    path: '/trip',
    label: '出行',
    icon: 'M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11z',
    modes: [],
  },
  {
    path: '/customer',
    label: '客服',
    icon: 'M4 13a8 8 0 0 1 16 0v3.5a2.5 2.5 0 0 1-2.5 2.5H15',
    modes: [],
  },
]

/** 根据当前路由名，判断属于哪个模块 */
export function moduleOfRoute(routeName: string | symbol | undefined | null): ModuleDef {
  const name = String(routeName ?? '')

  if (name.startsWith('trip')) return MODULES[1]!
  if (name.startsWith('customer')) return MODULES[2]!
  return MODULES[0]! // 对话是默认
}
