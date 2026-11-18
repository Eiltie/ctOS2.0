<script setup lang="ts">
/**
 * 空状态：没有数据、还没开始用时显示。
 *
 * 好的空状态要说清楚「为什么是空的」和「下一步做什么」，
 * 而不是只放一个「暂无数据」。
 */
defineProps<{
  /** 大图标（emoji 即可） */
  icon?: string
  title: string
  description?: string
}>()
</script>

<template>
  <div class="empty">
    <div v-if="icon" class="empty-icon">{{ icon }}</div>
    <div class="empty-title">{{ title }}</div>
    <p v-if="description" class="empty-desc">{{ description }}</p>
    <slot />
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--s-8) var(--s-5);
  text-align: center;
}

.empty-icon {
  font-size: 30px;
  line-height: 1;
  opacity: 0.55;
  margin-bottom: var(--s-3);
}

.empty-title {
  font-size: var(--f-base);
  font-weight: 600;
  color: var(--c-text-2);
}

.empty-desc {
  margin-top: var(--s-1);
  font-size: var(--f-sm);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
  max-width: 32em;
}
</style>
