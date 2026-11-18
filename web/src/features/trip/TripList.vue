<script setup lang="ts">
/**
 * 出行记录列表（左侧）。
 *
 * 和对话的会话列表是**两套完全独立的数据**：
 *   对话   GET /sessions   （sessions 表）
 *   出行   GET /trip/list  （trip_chats 表）
 *
 * 为什么这里不标「路线 / 攻略」：
 *   后端每一轮单独判断走哪条子图，同一个会话里可以先后调路线、攻略、直接回答。
 *   标签只代表「最后一轮」，标在会话上会让人误以为整个会话都是那种类型。
 *   所以列表只显示标题和轮次，具体类型在右边每一轮的卡片上。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { tripStore } from './store'
import { authStore } from '@/shared/auth/authStore'

const { state } = tripStore

onMounted(() => {
  void tripStore.loadTrips()
})

/**
 * 身份变了（登录 / 注册 / 退出）：换账号了，记录要重拉。
 * 不做的话，登录后左边还是访客的记录。
 */
const unsubscribe = authStore.onIdentityChanged(() => {
  tripStore.newTrip()
  selecting.value = false
  selected.value = new Set()
  void tripStore.loadTrips()
})

onUnmounted(unsubscribe)

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

const sessionCount = computed(() => state.trips.length)

async function confirmDelete(id: number, event: Event) {
  event.stopPropagation()
  if (!confirm('删除这条出行记录？')) return
  await tripStore.removeTrip(id)
}

// ---------------------------------------------------------------- 多选

/** 是不是在多选模式 */
const selecting = ref(false)
/** 勾了哪些 */
const selected = ref<Set<number>>(new Set())
const deleting = ref(false)

const allSelected = computed(
  () => sessionCount.value > 0 && selected.value.size === sessionCount.value,
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
    selected.value = new Set(state.trips.map((t) => t.id))
  }
}

/** 点条目：多选时切换勾选，平时打开记录 */
function onItemClick(id: number, event: Event) {
  if (selecting.value) {
    event.preventDefault()
    toggleOne(id)
    return
  }
  void tripStore.openTrip(id)
}

/** 批量删除 */
async function deleteSelected() {
  if (!selected.value.size || deleting.value) return

  const count = selected.value.size
  if (!confirm(`删除选中的 ${count} 条出行记录？删了找不回来。`)) return

  deleting.value = true
  try {
    await tripStore.removeTrips([...selected.value])
    cancelSelecting()
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="trip-list">
    <div class="list-head">
      <span class="list-title">出行记录</span>
      <button type="button" class="new-btn" @click="tripStore.newTrip()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
        新建
      </button>
    </div>

    <div class="list-scroll">
      <!-- 只有首次加载才显示「加载中」，静默刷新不闪 -->
      <div v-if="state.tripsLoading && !sessionCount" class="list-loading">加载中…</div>

      <div v-else-if="state.tripsError && !sessionCount" class="list-error">
        {{ state.tripsError }}
        <button type="button" @click="tripStore.loadTrips()">重试</button>
      </div>

      <div v-else-if="!sessionCount" class="list-empty">
        <div class="empty-icon">🗺</div>
        <div class="empty-title">还没有出行记录</div>
        <p class="empty-desc">说一句想去哪儿，就会自动建一条</p>
      </div>

      <button
        v-for="trip in state.trips"
        :key="trip.id"
        type="button"
        class="trip-item"
        :class="{
          'trip-item--active': !selecting && trip.id === state.currentTripId,
          'trip-item--checked': selecting && selected.has(trip.id),
        }"
        @click="onItemClick(trip.id, $event)"
      >
        <!-- 多选模式：左边出现复选框 -->
        <span v-if="selecting" class="trip-check" aria-hidden="true">
          <span v-if="selected.has(trip.id)" class="trip-check-dot">✓</span>
        </span>

        <span class="trip-body">
          <span class="trip-top">
            <span class="trip-title">{{ trip.title }}</span>
            <span class="trip-time">{{ formatTime(trip.updated_at) }}</span>
          </span>
          <span class="trip-sub">{{ trip.turn_count }} 轮对话</span>
        </span>

        <span
          v-if="!selecting"
          class="trip-del"
          title="删除"
          @click="confirmDelete(trip.id, $event)"
        >
          ×
        </span>
      </button>
    </div>

    <!-- ---------- 底部：平时显示数量，多选时显示操作条 ---------- -->
    <div v-if="!selecting" class="list-foot">
      <span>共 {{ sessionCount }} 条记录</span>
      <button
        v-if="sessionCount > 0"
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
.trip-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* ---------- 标题 ---------- */
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
  border-radius: var(--r-pill);
  border: 1px solid var(--c-line);
  background: var(--c-bg);
  color: var(--c-text-2);
  font-size: var(--f-sm);
  transition:
    border-color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft);
}

.new-btn:hover {
  border-color: var(--c-line-hover);
  background: var(--c-bg-soft);
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

.list-empty {
  text-align: center;
  padding: var(--s-7) var(--s-4);
}

.empty-icon {
  font-size: 24px;
  opacity: 0.5;
}

.empty-title {
  font-size: var(--f-sm);
  font-weight: 600;
  color: var(--c-text-2);
  margin-top: var(--s-2);
}

.empty-desc {
  font-size: var(--f-xs);
  color: var(--c-text-3);
  margin-top: 2px;
}

/* ---------- 单条 ---------- */
.trip-item {
  position: relative;
  display: block;
  width: 100%;
  text-align: left;
  padding: 11px var(--s-3);
  border-radius: var(--r-md);
  margin-bottom: 3px;
  outline: 1px solid transparent;
  transition:
    background var(--t-fast) var(--ease-soft),
    outline-color var(--t-fast) var(--ease-soft),
    box-shadow var(--t-fast) var(--ease-soft);
}

.trip-item:hover {
  background: var(--c-bg-hover);
}

.trip-item--active {
  background: var(--c-bg);
  outline-color: var(--c-line);
  box-shadow: var(--sh-sm);
}

.trip-top {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
}

.trip-title {
  flex: 1;
  font-size: var(--f-base);
  font-weight: 550;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.trip-time {
  font-size: var(--f-xs);
  color: var(--c-text-3);
  flex-shrink: 0;
}

.trip-sub {
  display: block;
  margin-top: 3px;
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

.trip-del {
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
  transition: opacity var(--t-fast) var(--ease-soft);
}

.trip-item:hover .trip-del {
  opacity: 1;
}

.trip-del:hover {
  background: var(--c-danger-soft);
  color: var(--c-danger);
}

/* ---------- 底部 ---------- */
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
.trip-item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}

.trip-body {
  flex: 1;
  min-width: 0;
  display: block;
}

/* 复选框 */
.trip-check {
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

.trip-item--checked .trip-check {
  background: var(--c-brand);
  border-color: var(--c-brand);
}

.trip-check-dot {
  line-height: 1;
}

.trip-item--checked {
  background: var(--c-brand-soft);
}

.trip-item--checked .trip-title {
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
</style>

