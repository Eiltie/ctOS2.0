<script setup lang="ts">
/**
 * 地点歧义选择面板。
 *
 * 什么时候出现：
 *   用户说「去长城」这种一查出来好几个地方的地名时，
 *   后端停下来让用户指认具体是哪个（见 route/stream.py 的 can_ask_place）。
 *
 * 数据比路线简单：每个候选只有一个 label（地址）和 note（级别）。
 */
import type { PlaceOption } from '@/shared/types/api'

defineProps<{
  ask: {
    threadId: string
    question: string
    name: string
    options: PlaceOption[]
  }
}>()

const emit = defineEmits<{
  pick: [place: string]
}>()
</script>

<template>
  <div class="ask-panel">
    <div class="ask-question">{{ ask.question }}</div>

    <div class="options">
      <button
        v-for="option in ask.options"
        :key="option.id"
        type="button"
        class="option"
        @click="emit('pick', option.label)"
      >
        <span class="option-idx">{{ option.id }}</span>
        <span class="option-main">
          <span class="option-label">{{ option.label }}</span>
          <span v-if="option.note" class="option-note">{{ option.note }}</span>
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.ask-panel {
  border: 1.5px solid var(--c-brand-line);
  border-radius: var(--r-lg);
  background: var(--c-bg);
  padding: var(--s-4);
  margin-top: var(--s-3);
}

.ask-question {
  font-size: var(--f-base);
  font-weight: 600;
  color: var(--c-text);
  margin-bottom: var(--s-3);
}

.options {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.option {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  width: 100%;
  text-align: left;
  padding: 10px var(--s-3);
  border: 1.5px solid var(--c-line);
  border-radius: var(--r-md);
  background: var(--c-bg);
  transition:
    border-color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft);
}

.option:hover {
  border-color: var(--c-line-hover);
  background: var(--c-bg-soft);
}

.option-idx {
  width: 20px;
  height: 20px;
  border-radius: var(--r-sm);
  background: var(--c-bg-soft);
  color: var(--c-text-3);
  font-size: var(--f-xs);
  font-weight: 600;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.option-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.option-label {
  font-size: var(--f-sm);
  color: var(--c-text);
  word-break: break-word;
}

.option-note {
  font-size: var(--f-xs);
  color: var(--c-text-3);
}
</style>
