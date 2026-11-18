<script setup lang="ts">
/**
 * 玩法条 —— 模块内部的玩法切换。
 *
 * 为什么要有这一条：
 *   玩法放在顶栏里，玩法一多就把顶栏挤乱了。
 *   单独一条横栏之后，加玩法只是在数组里追加一项，
 *   横向会自动排开（窄屏可以滑动），顶栏和页面布局都不用动。
 */
import { useRoute, useRouter } from 'vue-router'
import type { ModeDef } from '@/shared/lib/navigation'

const props = defineProps<{
  modes: ModeDef[]
}>()

const route = useRoute()
const router = useRouter()

function isActive(mode: ModeDef): boolean {
  return route.name === mode.route
}

function pick(mode: ModeDef) {
  if (mode.soon) return
  if (isActive(mode)) return
  void router.push({ name: mode.route })
}
</script>

<template>
  <div class="modebar" role="tablist" aria-label="玩法">
    <span class="modebar-label">玩法</span>

    <button
      v-for="mode in props.modes"
      :key="mode.route"
      type="button"
      role="tab"
      class="mode"
      :class="{
        'mode--active': isActive(mode),
        'mode--soon': mode.soon,
      }"
      :aria-selected="isActive(mode)"
      :disabled="mode.soon"
      @click="pick(mode)"
    >
      <span class="mode-icon">{{ mode.icon }}</span>
      <span>{{ mode.label }}</span>
      <span v-if="mode.soon" class="mode-soon">待上线</span>
    </button>

    <span class="modebar-hint">新玩法会加在这里</span>
  </div>
</template>

<style scoped>
.modebar {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: 10px var(--s-6);
  background: var(--c-bg-sidebar);
  border-bottom: 1px solid var(--c-line);
  flex-shrink: 0;

  /* 玩法多的时候横向滚动，不换行、不撑破布局 */
  overflow-x: auto;
  scrollbar-width: none;
}

.modebar::-webkit-scrollbar {
  display: none;
}

.modebar-label {
  font-size: var(--f-sm);
  font-weight: 650;
  color: var(--c-text-3);
  letter-spacing: 0.3px;
  flex-shrink: 0;
  margin-right: 2px;
}

.mode {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px var(--s-3);
  border: 1.5px solid var(--c-line);
  /* 玩法做成胶囊，比方块更柔 */
  border-radius: var(--r-pill);
  background: var(--c-bg);
  font-size: var(--f-base);
  color: var(--c-text-2);
  flex-shrink: 0;
  transition:
    border-color var(--t-fast) var(--ease-soft),
    color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft),
    transform var(--t-fast) var(--ease-soft);
}

.mode:hover:not(.mode--active):not(.mode--soon) {
  border-color: var(--c-line-hover);
  color: var(--c-text);
  transform: translateY(-1px);
}

.mode--active {
  border-color: var(--c-line-strong);
  background: var(--c-bg-soft);
  color: var(--c-text);
  font-weight: 600;
}

.mode--soon {
  opacity: 0.55;
  cursor: default;
}

.mode-icon {
  font-size: var(--f-md);
  line-height: 1;
}

.mode-soon {
  font-size: 10px;
  color: var(--c-text-3);
  background: var(--c-bg-soft);
  border-radius: var(--r-pill);
  padding: 1px 6px;
  margin-left: 1px;
}

.modebar-hint {
  margin-left: auto;
  padding-left: var(--s-3);
  font-size: var(--f-xs);
  color: var(--c-text-3);
  flex-shrink: 0;
}

/* ---------- 窄屏（≤ 768px）----------
   玩法条要横向滚动而不是换行。
   以后加更多玩法也不会把这一行撑成两行 */
@media (max-width: 768px) {
  .modebar {
    padding: 6px var(--m-pad);
    gap: var(--s-2);
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-width: none;
  }

  .modebar::-webkit-scrollbar {
    display: none;
  }

  /* 右边那句「新玩法会加在这里」在手机上没位置，藏掉 */
  .modebar-hint {
    display: none;
  }

  /* 「玩法」这个前置标签也藏掉，省地方 */
  .modebar-label {
    display: none;
  }

  .mode {
    padding: 5px 11px;
    font-size: var(--f-xs);
    white-space: nowrap;
    flex-shrink: 0;
    gap: 4px;
    /* 手机上不要那个大圆角阴影，显得笨重 */
    box-shadow: none;
    border: 1px solid var(--c-line);
  }

  /* 选中的那个也要有清晰的边界，不然分不清哪个是当前玩法 */
  .mode--active {
    border-color: var(--c-line-strong);
  }

  .mode-icon {
    font-size: var(--f-sm);
  }
}</style>


