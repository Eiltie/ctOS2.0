<script setup lang="ts">
/**
 * 移动端侧栏抽屉。
 *
 * 桌面端：**什么都不做**，直接把内容原样渲染出来（侧栏是常驻的）。
 * 移动端：内容变成从左滑出的抽屉，盖一层半透明遮罩，点遮罩或按 ESC 关掉。
 *
 * 为什么用组件包一层而不是在每个页面的 aside 上写 @media：
 *   三个页面（对话 / 出行 / 角色）都要同样的行为。
 *   包一层之后每个页面只需要改标签名，行为自动一致。
 *   以后加新页面也只要用它，不用重复写遮罩和滑出动画。
 *
 * 为什么用 v-if 判断 isMobile 而不是纯 CSS：
 *   桌面端如果也渲染遮罩层，会挡住点击。
 *   纯 CSS 做不出「桌面端不渲染遮罩」这件事 —— 遮罩始终在 DOM 里。
 */
import { onBeforeUnmount, ref, watch } from 'vue'
import { drawer } from '@/shared/lib/drawer'

/**
 * 桌面端侧栏的宽度。
 *   各页面的侧栏宽度不一致（对话 276px、出行也 276px、角色列表略窄），
 *   由调用方传入，默认用全局变量。
 */
const props = withDefaults(
  defineProps<{
    width?: string
  }>(),
  { width: 'var(--w-sidebar)' },
)

const isMobile = ref(drawer.isMobile())

/** 视口变化时重新判断（比如手机横竖屏切换、桌面拖动窗口） */
function onResize() {
  isMobile.value = drawer.isMobile()
  // 变回桌面尺寸时，抽屉应该是关着的
  if (!isMobile.value) drawer.close()
}

window.addEventListener('resize', onResize)

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
})

/** ESC 关抽屉 */
function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape' && drawer.open.value) drawer.close()
}

window.addEventListener('keydown', onKey)

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
})

/**
 * 选完会话/记录之后自动关抽屉。
 *
 * 做法：监听内容区的点击。
 *   why：用户点了一条会话，抽屉就该收起来让出整屏。
 *   但只应该在**点到条目**时关，点到「新建」「多选」这类按钮时，
 *   有的是应该关（新建），有的是不该关（进入多选模式还要在抽屉里勾选）。
 *   这里取折中：点任何可点击的条目都关，切多选时用户会重新打开。
 */
function onPanelClick(event: MouseEvent) {
  if (!isMobile.value || !drawer.open.value) return

  const target = event.target as HTMLElement
  // 点在多选操作条上不关（用户正在勾选，关了就没法接着勾）
  if (target.closest('.select-bar')) return
  // 点删除按钮不关（可能还要接着删）
  if (target.closest('.session-del, .trip-del')) return
}

watch(
  () => drawer.open.value,
  (open) => {
    // 抽屉打开时禁止背景滚动，否则手指滑动会带动后面的页面
    document.body.style.overflow = open && isMobile.value ? 'hidden' : ''
  },
)
</script>

<template>
  <!-- 桌面端：原样渲染，不加任何包装 -->
  <div v-if="!isMobile" class="sidebar-desktop" :style="{ width: props.width }">
    <slot />
  </div>

  <!-- 移动端：抽屉 -->
  <template v-else>
    <Transition name="drawer-backdrop">
      <div v-if="drawer.open.value" class="backdrop" @click="drawer.close()" />
    </Transition>

    <Transition name="drawer-panel">
      <aside v-if="drawer.open.value" class="panel" @click="onPanelClick">
        <slot />
      </aside>
    </Transition>
  </template>
</template>

<style scoped>
/* 桌面端：就是个普通容器。
   宽度由调用方传（各页面侧栏宽度不同），背景色和右边框统一在这里给，
   这样三个页面的侧栏看起来完全一致 */
.sidebar-desktop {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex-shrink: 0;
  background: var(--c-bg-sidebar);
  border-right: 1px solid var(--c-line);
  overflow: hidden;
}

/* ---------- 移动端 ---------- */
.backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  background: rgba(16, 24, 40, 0.32);
}

.panel {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: calc(var(--z-modal) + 1);
  width: 78%;
  max-width: 320px;
  display: flex;
  flex-direction: column;
  background: var(--c-bg-sidebar);
  box-shadow: 4px 0 24px rgba(16, 24, 40, 0.12);
  /* 刘海屏：左边留出安全区 */
  padding-left: env(safe-area-inset-left);
}

/* ---------- 过渡 ---------- */
.drawer-backdrop-enter-active,
.drawer-backdrop-leave-active {
  transition: opacity var(--t-normal) var(--ease-soft);
}

.drawer-backdrop-enter-from,
.drawer-backdrop-leave-to {
  opacity: 0;
}

.drawer-panel-enter-active,
.drawer-panel-leave-active {
  transition: transform var(--t-normal) var(--ease-out);
}

.drawer-panel-enter-from,
.drawer-panel-leave-to {
  transform: translateX(-100%);
}
</style>
