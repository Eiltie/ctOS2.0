<script setup lang="ts">
/**
 * 一张角色卡。
 *
 * 只负责显示和发出事件，不碰接口 —— 点哪张卡、删不删都由父组件决定。
 */
import type { RoleCard } from '@/shared/types/api'

const props = defineProps<{
  role: RoleCard
  /** 是不是我自己创建的角色（决定要不要显示删除） */
  mine?: boolean
}>()

const emit = defineEmits<{
  pick: [role: RoleCard]
  remove: []
}>()

function onRemove(event: Event) {
  event.stopPropagation()
  if (!confirm(`删除角色「${props.role.name}」？它所有的聊天记录和记忆都会一起删掉。`)) {
    return
  }
  emit('remove')
}
</script>

<template>
  <button type="button" class="role-card" @click="emit('pick', role)">
    <span class="role-emoji">{{ role.emoji || '🎭' }}</span>

    <span class="role-name">{{ role.name }}</span>

    <span v-if="role.tagline" class="role-tagline">{{ role.tagline }}</span>

    <span v-if="mine" class="role-mine">我的</span>

    <span v-if="mine" class="role-del" title="删除角色" @click="onRemove">×</span>
  </button>
</template>

<style scoped>
.role-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
  padding: var(--s-4);
  min-height: 132px;
  border: 1.5px solid var(--c-line);
  border-radius: var(--r-xl);
  background: var(--c-bg);
  cursor: pointer;
  transition:
    border-color var(--t-normal) var(--ease-soft),
    transform var(--t-normal) var(--ease-soft),
    box-shadow var(--t-normal) var(--ease-soft);
}

.role-card:hover {
  border-color: var(--c-line-hover);
  transform: translateY(-3px);
  box-shadow: var(--sh-lg);
}

.role-emoji {
  font-size: 26px;
  line-height: 1;
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: var(--r-lg);
  background: var(--c-bg-soft);
}

.role-name {
  font-size: var(--f-base);
  font-weight: 650;
  color: var(--c-text);
  margin-top: var(--s-3);
}

.role-tagline {
  font-size: var(--f-xs);
  color: var(--c-text-3);
  margin-top: 3px;
}

.role-mine {
  position: absolute;
  top: var(--s-3);
  right: var(--s-3);
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--r-pill);
  background: var(--c-bg-soft);
  color: var(--c-text-3);
}

/* 删除按钮：悬停才出现，平时不干扰视线 */
.role-del {
  position: absolute;
  bottom: var(--s-3);
  right: var(--s-3);
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: var(--r-sm);
  font-size: 15px;
  line-height: 1;
  color: var(--c-text-3);
  opacity: 0;
  transition:
    opacity var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft);
}

.role-card:hover .role-del {
  opacity: 1;
}

.role-del:hover {
  background: var(--c-danger-soft);
  color: var(--c-danger);
}
</style>
