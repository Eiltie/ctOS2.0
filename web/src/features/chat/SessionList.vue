<script setup lang="ts">
/**
 * 左侧会话列表（对话模块用）。
 *
 * 和后端的关系：
 *   GET /sessions 返回的是**闲聊和角色共用**的会话表，
 *   每条带 role_id：有值说明是角色会话，用来显示「角色」标签。
 *
 * 和出行列表的区别（这一点容易搞混）：
 *   出行的会话在另一张表里，走 /trip/list，和这里的数据完全无关。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { chatStore } from './store'
import { authStore } from '@/shared/auth/authStore'
import type { ChatSession } from '@/shared/types/api'
import EmptyState from '@/shared/components/EmptyState.vue'

const { state } = chatStore

/** 当前是不是在批量选择 */
const selecting = ref(false)
const selected = ref<Set<number>>(new Set())

/**
 * 拿到身份之后再拉会话列表。
 *
 * main.ts 已经 await 了 authStore.boot() 才开始 mount，
 * 正常情况下挂载时 token 已经有了。这里再等一次是为了兜住
 * 「启动失败后又重试成功」这种情况，避免列表一直停在空的。
 */
onMounted(() => {
  if (authStore.state.user) {
    void chatStore.loadSessions()
  }
})

watch(
  () => authStore.state.user,
  (user) => {
    if (user) void chatStore.loadSessions()
  },
)

/**
 * 身份变了（登录 / 注册 / 退出）：换账号了，列表要重拉。
 * 这个必须做 —— 否则登录后左边还是访客的会话。
 */
const unsubscribe = authStore.onIdentityChanged(() => {
  selecting.value = false
  selected.value = new Set()
  chatStore.newChat()
  void chatStore.loadSessions()
})

onUnmounted(unsubscribe)

/** 时间显示成「14:32」或「昨天」或「11-15」 */
function formatTime(iso: string): string {
  if (!iso) return ''

  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''

  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()

  if (sameDay) {
    return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  }

  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const isYesterday =
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate()

  if (isYesterday) return '昨天'

  return `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

async function confirmDelete(id: number, event: Event) {
  event.stopPropagation()
  if (!confirm('删除这个会话？聊天记录也会一起删掉。')) return
  await chatStore.removeSession(id)
}

/**
 * 每条会话的副标题。
 *
 * 为什么不用「会话 #61」：
 *   那是数据库 id，对用户没有意义，还占掉一行正文字宽。
 *
 * 改成一个真正能帮人区分的线索：
 *   角色会话 → 「第 N 次对话」（同一角色开了好几个时靠它分）
 *   普通会话 → 「闲聊」
 */
function describe(session: ChatSession): string {
  if (session.role_id) {
    // 同名角色可能有好几个会话，按最近顺序给个序号
    const sameRole = state.sessions.filter(
      (item) => item.role_id === session.role_id,
    )
    if (sameRole.length <= 1) return '角色对话'

    // 列表按更新时间倒序，越靠前越新
    const index = sameRole.indexOf(session)
    return index === 0 ? '最近一次' : `第 ${sameRole.length - index} 次对话`
  }

  return '闲聊'
}

// ---------------------------------------------------------------- 多选

/** 勾了哪些（selecting / selected 在上面已声明） */
const deleting = ref(false)

const allSelected = computed(
  () =>
    state.sessions.length > 0 && selected.value.size === state.sessions.length,
)

function startSelecting() {
  selecting.value = true
  selected.value = new Set()
}

function cancelSelecting() {
  selecting.value = false
  selected.value = new Set()
}

function toggleOne(id: number) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function toggleAll() {
  if (allSelected.value) {
    selected.value = new Set()
  } else {
    selected.value = new Set(state.sessions.map((s) => s.id))
  }
}

/** 点条目：多选时切换勾选，平时打开会话 */
function onItemClick(id: number, event: Event) {
  if (selecting.value) {
    // 多选模式下点条目不进入会话
    event.preventDefault()
    toggleOne(id)
    return
  }
  void chatStore.openSession(id)
}

/** 批量删除 */
async function deleteSelected() {
  if (!selected.value.size || deleting.value) return

  const count = selected.value.size
  if (!confirm(`删除选中的 ${count} 个会话？聊天记录也会一起删掉。`)) return

  deleting.value = true
  try {
    await chatStore.removeSessions([...selected.value])
    cancelSelecting()
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="session-list">
    <div class="list-head">
      <span class="list-title">最近对话</span>
      <button type="button" class="new-btn" @click="chatStore.newChat()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
        新建
      </button>
    </div>

    <div class="list-scroll">
      <!--
        只有「手上一条数据都没有」时才显示加载中。
        已经有列表的情况下刷新（比如切换会话带来的静默刷新），
        继续显示旧的列表，不要整块闪成「加载中…」。
      -->
      <div v-if="state.sessionsLoading && !state.sessions.length" class="list-loading">
        加载中…
      </div>

      <div v-else-if="state.sessionsError && !state.sessions.length" class="list-error">
        {{ state.sessionsError }}
        <button type="button" @click="chatStore.loadSessions()">重试</button>
      </div>

      <EmptyState
        v-else-if="!state.sessions.length"
        icon="💬"
        title="还没有会话"
        description="发第一句话就会自动创建"
      />

      <button
        v-for="session in state.sessions"
        :key="session.id"
        type="button"
        class="session-item"
        :class="{
          'session-item--active': !selecting && session.id === state.currentSessionId,
          'session-item--checked': selecting && selected.has(session.id),
        }"
        @click="onItemClick(session.id, $event)"
      >
        <!-- 多选模式：左边出现复选框 -->
        <span v-if="selecting" class="session-check" aria-hidden="true">
          <span v-if="selected.has(session.id)">✓</span>
        </span>

        <span class="session-body">
          <div class="session-top">
            <span class="session-title">{{ session.title }}</span>
            <span class="session-time">{{ formatTime(session.updated_at) }}</span>
          </div>
          <div class="session-sub">
            <span v-if="session.role_id" class="badge-role">角色</span>
            <span class="session-hint">{{ describe(session) }}</span>
          </div>
        </span>

        <span
          v-if="!selecting"
          class="session-del"
          title="删除会话"
          @click="confirmDelete(session.id, $event)"
        >
          ×
        </span>
      </button>
    </div>

    <!-- 底部：平时显示数量，多选时变成操作条 -->
    <div v-if="!selecting" class="list-foot">
      <span>共 {{ state.sessions.length }} 个会话</span>
      <button
        v-if="state.sessions.length > 0"
        type="button"
        class="foot-action"
        @click="startSelecting"
      >
        多选
      </button>
    </div>

    <div v-else class="select-bar">
      <button type="button" class="bar-btn" @click="toggleAll">
        {{ allSelected ? '取消全选' : '全选' }}
      </button>
      <span class="bar-count">已选 {{ selected.size }}</span>
      <button type="button" class="bar-btn" @click="cancelSelecting">取消</button>
      <button
        type="button"
        class="bar-btn bar-btn--danger"
        :disabled="!selected.size || deleting"
        @click="deleteSelected"
      >
        {{ deleting ? '删除中…' : '删除' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.session-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* ---------- 标题区 ---------- */
.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-4) var(--s-4) var(--s-2);
  flex-shrink: 0;
}

.list-title {
  font-size: var(--f-base);
  font-weight: 650;
}

.new-btn {
  display: flex;
  align-items: center;
  gap: var(--s-1);
  height: 28px;
  padding: 0 11px;
  border-radius: var(--r-pill); /* 胶囊按钮 */
  border: 1px solid var(--c-line);
  background: var(--c-bg);
  color: var(--c-text-2);
  font-size: var(--f-sm);
  transition:
    border-color var(--t-fast) var(--ease-soft),
    color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft),
    transform var(--t-fast) var(--ease-soft);
}

.new-btn:hover {
  border-color: var(--c-line-hover);
  color: var(--c-text);
  background: var(--c-bg-soft);
  transform: translateY(-1px);
}

/* ---------- 列表 ---------- */
.list-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 2px var(--s-2) var(--s-3);
  min-height: 0;
}

.list-loading,
.list-error {
  padding: var(--s-4);
  font-size: var(--f-sm);
  color: var(--c-text-3);
  text-align: center;
}

.list-error {
  color: var(--c-danger);
}

.list-error button {
  display: block;
  margin: var(--s-2) auto 0;
  font-size: var(--f-sm);
  color: var(--c-brand-deep);
  text-decoration: underline;
}

/* ---------- 单条会话 ---------- */
.session-item {
  position: relative;
  display: block;
  width: 100%;
  text-align: left;
  padding: 11px var(--s-3);
  border-radius: var(--r-md);
  margin-bottom: 3px;
  /* 选中态用描边 + 阴影，而不是硬边框，过渡更顺 */
  outline: 1px solid transparent;
  transition:
    background var(--t-fast) var(--ease-soft),
    outline-color var(--t-fast) var(--ease-soft),
    box-shadow var(--t-fast) var(--ease-soft),
    transform var(--t-fast) var(--ease-soft);
}

.session-item:hover {
  background: var(--c-bg-hover);
}

.session-item--active {
  background: var(--c-bg);
  outline-color: var(--c-line);
  box-shadow: var(--sh-sm);
}

.session-item--active:hover {
  transform: none;
}

.session-item--active .session-title {
  color: var(--c-text);
}

.session-top {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
}

.session-title {
  flex: 1;
  font-size: var(--f-base);
  font-weight: 550;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-time {
  font-size: var(--f-xs);
  color: var(--c-text-3);
  flex-shrink: 0;
}

.session-sub {
  display: flex;
  align-items: center;
  gap: var(--s-1);
  margin-top: 3px;
}

.badge-role {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: var(--r-sm);
  background: var(--c-warn-soft);
  color: var(--c-warn);
}

.session-hint {
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

/* 删除按钮：悬停才出现，避免列表太花 */
.session-del {
  position: absolute;
  right: 6px;
  bottom: 6px;
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: var(--r-sm);
  font-size: 14px;
  line-height: 1;
  color: var(--c-text-3);
  opacity: 0;
  transition: opacity var(--t-fast) var(--ease);
}

.session-item:hover .session-del {
  opacity: 1;
}

.session-del:hover {
  background: var(--c-danger-soft);
  color: var(--c-danger);
}

/* ---------- 底部计数 ---------- */
.list-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px var(--s-4);
  border-top: 1px solid var(--c-line);
  font-size: var(--f-xs);
  color: var(--c-text-3);
  flex-shrink: 0;
}

.foot-action {
  font-size: var(--f-xs);
  color: var(--c-text-2);
}

.foot-action:hover {
  color: var(--c-text);
  text-decoration: underline;
}

/* ---------- 多选模式 ---------- */
.session-item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}

.session-body {
  flex: 1;
  min-width: 0;
  display: block;
}

/* 复选框 */
.session-check {
  width: 17px;
  height: 17px;
  border-radius: var(--r-sm);
  border: 1.5px solid var(--c-line-strong);
  flex-shrink: 0;
  display: grid;
  place-items: center;
  font-size: 10px;
  color: #fff;
  transition: all var(--t-fast) var(--ease-soft);
}

.session-item--checked .session-check {
  background: var(--c-brand);
  border-color: var(--c-brand);
}

.session-item--checked {
  background: var(--c-brand-soft);
}

.session-item--checked .session-title {
  color: var(--c-brand-deep);
}

/* 底部操作条 */
.select-bar {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: 10px var(--s-3);
  border-top: 1px solid var(--c-line);
  background: var(--c-bg);
  flex-shrink: 0;
}

.bar-btn {
  font-size: var(--f-xs);
  color: var(--c-text-2);
  padding: 4px 8px;
  border-radius: var(--r-sm);
  transition: background var(--t-fast) var(--ease-soft);
}

.bar-btn:hover:not(:disabled) {
  background: var(--c-bg-soft);
}

.bar-btn--danger {
  margin-left: auto;
  color: var(--c-danger);
  font-weight: 600;
}

.bar-btn--danger:hover:not(:disabled) {
  background: var(--c-danger-soft);
}

.bar-btn:disabled {
  color: var(--c-text-3);
  cursor: default;
}

.bar-count {
  font-size: var(--f-xs);
  color: var(--c-text-3);
}

/* ---------- 空/加载占位 ---------- */
:deep(.empty) {
  padding: var(--s-7) var(--s-4);
}

/* ---------- 窄屏（≤ 768px）----------
   侧栏在手机上变成抽屉，条目要更好点（手指比鼠标粗） */
@media (max-width: 768px) {
  .list-head {
    padding: 12px 12px 8px;
  }

  .list-scroll {
    padding: 2px 8px 12px;
  }

  /* 条目加大触摸区：手指比鼠标粗，但要比特意留白更紧凑 */
  .trip-item,
  .session-item {
    padding: 9px 10px;
  }

  /* 删除按钮在手机上一直显示（没有 hover） */
  .trip-del,
  .session-del {
    opacity: 1;
  }

  .list-foot {
    padding: 10px 12px;
    padding-bottom: calc(10px + env(safe-area-inset-bottom));
  }

  .select-bar {
    padding: 10px 10px;
    padding-bottom: calc(10px + env(safe-area-inset-bottom));
  }

  .bar-btn {
    padding: 8px 10px;
    font-size: var(--f-sm);
  }
}</style>




