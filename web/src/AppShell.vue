<script setup lang="ts">
/**
 * 壳层：顶栏 + 玩法条，是所有模块共同的部分。
 *
 * 结构：
 *   ┌──────────────────────────────────────────────┐
 *   │ 顶栏：品牌 · 对话 / 出行 / 客服               │
 *   ├──────────────────────────────────────────────┤
 *   │ 玩法条（只有有玩法的模块才有：对话）           │
 *   ├──────────────────────────────────────────────┤
 *   │ 页面内容（各页面自己决定要不要左侧列表）        │
 *   └──────────────────────────────────────────────┘
 *
 * 为什么左侧列表不放在这里：
 *   三个模块的列表长得完全不一样（会话 / 出行记录 / 没有），
 *   强行抽到这里会变成一堆 if。让它留在各自页面里更清楚。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import TopBar from '@/shared/components/TopBar.vue'
import ModeBar from '@/shared/components/ModeBar.vue'
import { moduleOfRoute } from '@/shared/lib/navigation'

const route = useRoute()

const currentModule = computed(() => moduleOfRoute(route.name))

/** 有玩法的模块（当前只有对话）才显示玩法条 */
const hasModeBar = computed(() => currentModule.value.modes.length > 0)
</script>

<template>
  <div class="shell">
    <TopBar />

    <ModeBar v-if="hasModeBar" :modes="currentModule.modes" />

    <div class="shell-body">
      <!-- 页面自己决定内容区怎么排（含左侧列表） -->
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.shell-body {
  flex: 1;
  display: flex;
  min-height: 0; /* 关键：否则内部滚动区会被撑高，滚不动 */
}
</style>
