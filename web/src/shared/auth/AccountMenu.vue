<script setup lang="ts">
/**
 * 账号菜单。
 *
 * 顶栏右侧那个头像点开就是这个。
 *
 * 访客状态：
 *   显示「访客」，给一个「登录 / 注册」入口。
 *   这是**唯一**能把访客记录升级成正式账号的地方，不能藏起来。
 *
 * 已登录：
 *   显示邮箱，可以退出（退出后自动回到访客身份）。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { authStore } from './authStore'

const emit = defineEmits<{
  openAuth: []
  openFeedback: []
}>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const user = computed(() => authStore.state.user)
const isGuest = computed(() => authStore.state.isGuest)

/** 头像里显示什么：昵称首字，没有就用邮箱首字 */
const initial = computed(() => {
  const name = authStore.displayName.value
  return (name || '?').slice(0, 1).toUpperCase()
})

/** 点外面关掉 */
function onDocClick(event: MouseEvent) {
  if (!open.value) return
  if (root.value && !root.value.contains(event.target as Node)) {
    open.value = false
  }
}

function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
})

function openAuthDialog() {
  open.value = false
  emit('openAuth')
}

function openFeedback() {
  open.value = false
  emit('openFeedback')
}

async function logout() {
  open.value = false
  if (!confirm('退出登录？记录会留在账号里，下次登录还能看到。')) return
  await authStore.logout()
}
</script>

<template>
  <div ref="root" class="account">
    <button type="button" class="account-btn" @click.stop="open = !open">
      <span class="who">{{ isGuest ? '访客' : authStore.displayName.value }}</span>
      <span class="avatar">{{ initial }}</span>
    </button>

    <Transition name="menu">
      <div v-if="open" class="menu">
        <!-- 身份信息 -->
        <div class="menu-head">
          <div class="menu-avatar">{{ initial }}</div>
          <div class="menu-info">
            <div class="menu-name">
              {{ isGuest ? '访客模式' : authStore.displayName.value }}
            </div>
            <div class="menu-email">{{ user?.email ?? '' }}</div>
          </div>
        </div>

        <div v-if="isGuest" class="menu-note">
          访客记录只存在当前浏览器，换设备就没有了。
        </div>

        <!-- 访客：登录入口 -->
        <button v-if="isGuest" type="button" class="menu-item menu-item--primary" @click="openAuthDialog">
          登录 / 注册
        </button>

        <!-- 已登录：退出 -->
        <button v-else type="button" class="menu-item" @click="logout">退出登录</button>

        <!-- 反馈：谁都能提 -->
        <button type="button" class="menu-item menu-item--muted" @click="openFeedback">
          意见反馈
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.account {
  position: relative;
}

.account-btn {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-1) var(--s-1) var(--s-1) var(--s-2);
  border-radius: var(--r-pill);
  transition: background var(--t-fast) var(--ease-soft);
}

.account-btn:hover {
  background: var(--c-bg-soft);
}

.who {
  font-size: var(--f-sm);
  color: var(--c-text-2);
  max-width: 120px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--c-bg-hover);
  color: var(--c-text-2);
  display: grid;
  place-items: center;
  font-size: var(--f-sm);
  font-weight: 600;
  flex-shrink: 0;
}

/* ---------- 下拉菜单 ---------- */
.menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 250px;
  background: var(--c-bg);
  border: 1px solid var(--c-line);
  border-radius: var(--r-lg);
  box-shadow: var(--sh-pop);
  padding: var(--s-2);
  z-index: var(--z-dropdown);
}

.menu-head {
  display: flex;
  gap: var(--s-3);
  align-items: center;
  padding: var(--s-2);
}

.menu-avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--c-bg-hover);
  color: var(--c-text-2);
  display: grid;
  place-items: center;
  font-size: var(--f-base);
  font-weight: 600;
  flex-shrink: 0;
}

.menu-info {
  min-width: 0;
}

.menu-name {
  font-size: var(--f-base);
  font-weight: 650;
  color: var(--c-text);
}

.menu-email {
  font-size: var(--f-xs);
  color: var(--c-text-3);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.menu-note {
  margin: var(--s-1) var(--s-2) var(--s-2);
  padding: 8px 10px;
  border-radius: var(--r-sm);
  background: var(--c-bg-soft);
  font-size: var(--f-xs);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
}

.menu-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 9px 10px;
  border-radius: var(--r-md);
  font-size: var(--f-sm);
  color: var(--c-text-2);
  transition: background var(--t-fast) var(--ease-soft);
}

.menu-item:hover {
  background: var(--c-bg-soft);
  color: var(--c-text);
}

.menu-item--primary {
  background: var(--c-brand);
  color: #fff;
  font-weight: 600;
  text-align: center;
}

.menu-item--primary:hover {
  background: var(--c-brand-deep);
  color: #fff;
}

/* 反馈：比主操作弱一级，但还是要能看见 */
.menu-item--muted {
  margin-top: 2px;
  border-top: 1px solid var(--c-line);
  border-radius: 0 0 var(--r-md) var(--r-md);
  color: var(--c-text-3);
}

/* ---------- 过渡 ---------- */
.menu-enter-active,
.menu-leave-active {
  transition:
    opacity var(--t-fast) var(--ease-soft),
    transform var(--t-fast) var(--ease-soft);
}

.menu-enter-from,
.menu-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}
</style>
