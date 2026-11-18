/**
 * 路由表。
 *
 * 分两层：
 *   第一层  AppShell         —— 外框：顶栏 + 左侧列表 + 内容区
 *   第二层  各模块的页面      —— 只负责自己那块内容
 *
 * 这样布局只写一次，以后加模块只要在第一层下面挂一个新的页面。
 *
 * 模块与玩法：
 *   /chat           对话 · 闲聊（默认）
 *   /chat/roles     对话 · 角色扮演
 *   /trip           出行（没有玩法概念，整个模块就是一件事）
 *   /customer       客服（没有玩法概念）
 *
 * 为什么角色扮演是 /chat/roles 而不是 /roleplay：
 *   它不是一个独立模块，是对话下面的一个玩法。路由结构跟着这个从属关系走，
 *   以后加新玩法就是 /chat/xxx，不会和顶层模块混在一起。
 */
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  /**
   * 基路径是 `/`，不是 `/static/dist/`。
   *
   * 这两件事容易混：
   *   Vite 的 base（/static/dist/）只决定**静态资源**从哪取
   *   — 那是由 /static/dist/index.html 里的 script 标签决定的
   *   浏览器的地址栏起始位置是 `/`，因为用户访问的是 http://站点/
   *   （后端 api/routes/system.py 的 index() 把 / 指向了产物里的 index.html）
   *
   * 所以页面内的路由是 /chat、/trip，不是 /static/dist/chat。
   */
  history: createWebHistory('/'),

  routes: [
    {
      path: '/',
      component: () => import('@/AppShell.vue'),
      children: [
        { path: '', redirect: '/chat' },

        // ---------- 对话 ----------
        {
          path: 'chat',
          name: 'chat',
          component: () => import('@/features/chat/ChatView.vue'),
        },
        {
          path: 'chat/roles',
          name: 'chat-roles',
          component: () => import('@/features/chat/roleplay/RolePickerView.vue'),
        },

        // ---------- 出行 ----------
        {
          path: 'trip',
          name: 'trip',
          component: () => import('@/features/trip/TripView.vue'),
        },

        // ---------- 客服 ----------
        {
          path: 'customer',
          name: 'customer',
          component: () => import('@/features/customer/CustomerView.vue'),
        },
      ],
    },

    // 未知路径回对话
    { path: '/:pathMatch(.*)*', redirect: '/chat' },
  ],
})

export default router
