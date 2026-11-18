<script setup lang="ts">
/**
 * 路线方案选择面板。
 *
 * 后端在 ASK 事件里给了两条信息：
 *   options[].card  结构化的方案信息（用时、费用、距离、路况、换乘）
 *   recommended_*   后端推荐哪个
 *
 * 这里直接把 card 画成卡片，用户点哪条就走哪条。
 *
 * 为什么不用表格：
 *   表格适合「一眼横向比较」，但这里是让用户「挑一个」，
 *   而且每条的信息量不一样（打车显示路况，公交显示换乘线路）。
 *   卡片能按每条的实际情况排布，比强行塞进固定列更好读。
 */
import { computed, ref } from 'vue'
import type { RouteOption } from '@/shared/types/api'

const props = defineProps<{
  ask: {
    threadId: string
    question: string
    options: RouteOption[]
    recommendedId: string
    recommendedText: string
  }
}>()

const emit = defineEmits<{
  pick: [choiceId: string]
}>()

/** 用户点中的那条（点完之后按钮变「继续」，避免误触） */
const selected = ref('')

const options = computed(() => props.ask.options ?? [])

/** 每种交通方式用一个 emoji，比纯文字好认 */
const MODE_ICONS: Record<string, string> = {
  drive: '🚕',
  taxi: '🚕',
  transit: '🚇',
  subway: '🚇',
  bus: '🚌',
  walk: '🚶',
  bike: '🚲',
  ride: '🚲',
}

function iconOf(mode: string): string {
  return MODE_ICONS[mode] ?? '🚏'
}

/** 推荐的那条用高亮边框 */
function isRecommended(option: RouteOption): boolean {
  return option.id === props.ask.recommendedId || option.recommended === true
}

function pick(option: RouteOption) {
  selected.value = option.id
}

function confirm() {
  if (selected.value) emit('pick', selected.value)
}
</script>

<template>
  <div class="ask-panel">
    <div class="ask-head">
      <div class="ask-question">{{ ask.question }}</div>
      <div v-if="ask.recommendedText" class="ask-recommendation">
        {{ ask.recommendedText }}
      </div>
    </div>

    <div class="options">
      <button
        v-for="option in options"
        :key="option.id"
        type="button"
        class="option"
        :class="{
          'option--recommended': isRecommended(option),
          'option--selected': selected === option.id,
        }"
        @click="pick(option)"
      >
        <span class="option-radio" aria-hidden="true" />

        <span class="option-main">
          <span class="option-top">
            <span class="option-icon">{{ iconOf(option.card?.mode ?? '') }}</span>
            <span class="option-name">{{ option.name }}</span>
            <span v-if="isRecommended(option)" class="option-badge">推荐</span>
          </span>

          <span class="option-desc">{{ option.card?.desc || option.note }}</span>

          <!-- 关键数字：用时 / 费用 / 距离 -->
          <span v-if="option.card" class="option-stats">
            <span class="stat">
              <span class="stat-num">{{ option.card.minutes }}</span>
              <span class="stat-unit">分钟</span>
            </span>
            <span class="stat">
              <span class="stat-num">{{ option.card.cost }}</span>
              <span class="stat-unit">元</span>
            </span>
            <span class="stat">
              <span class="stat-num">{{ option.card.distance }}</span>
              <span class="stat-unit">公里</span>
            </span>
          </span>

          <!-- 换乘线路 -->
          <span v-if="option.card?.lines" class="option-lines">
            {{ option.card.lines }}
          </span>

          <!-- 补充信息 -->
          <span v-if="option.card?.facts?.length" class="option-facts">
            <span v-for="(fact, i) in option.card.facts" :key="i" class="fact">
              {{ fact }}
            </span>
          </span>
        </span>
      </button>
    </div>

    <div class="ask-foot">
      <button type="button" class="confirm-btn" :disabled="!selected" @click="confirm">
        {{ selected ? '按这个方案继续' : '选一个方案' }}
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

.ask-head {
  margin-bottom: var(--s-3);
}

.ask-question {
  font-size: var(--f-base);
  font-weight: 600;
  color: var(--c-text);
}

.ask-recommendation {
  margin-top: var(--s-1);
  font-size: var(--f-sm);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
}

/* ---------- 选项 ---------- */
.options {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.option {
  display: flex;
  gap: var(--s-3);
  align-items: flex-start;
  width: 100%;
  text-align: left;
  padding: var(--s-3) var(--s-4);
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

.option--recommended {
  border-color: var(--c-brand-line);
}

.option--selected {
  border-color: var(--c-brand);
  background: var(--c-brand-soft);
}

/* 单选圆点 */
.option-radio {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1.5px solid var(--c-line-strong);
  flex-shrink: 0;
  margin-top: 3px;
  transition: all var(--t-fast) var(--ease-soft);
}

.option--selected .option-radio {
  border-color: var(--c-brand);
  background: radial-gradient(circle, var(--c-brand) 0 4px, transparent 4.5px);
}

.option-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.option-top {
  display: flex;
  align-items: center;
  gap: var(--s-1);
}

.option-icon {
  font-size: var(--f-md);
}

.option-name {
  font-size: var(--f-sm);
  font-weight: 650;
  color: var(--c-text);
}

.option-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--r-pill);
  background: var(--c-brand);
  color: #fff;
}

.option-desc {
  font-size: var(--f-sm);
  color: var(--c-text-2);
}

/* 三个数字 */
.option-stats {
  display: flex;
  gap: var(--s-4);
  margin-top: 2px;
}

.stat {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.stat-num {
  font-size: var(--f-lg);
  font-weight: 650;
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
}

.stat-unit {
  font-size: var(--f-xs);
  color: var(--c-text-3);
}

/* 换乘线路 */
.option-lines {
  font-size: var(--f-sm);
  color: var(--c-text-2);
  padding: 5px 9px;
  background: var(--c-bg-soft);
  border-radius: var(--r-sm);
}

/* 补充信息 */
.option-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1) var(--s-3);
  margin-top: 1px;
}

.fact {
  font-size: var(--f-xs);
  color: var(--c-text-3);
}

/* ---------- 底部 ---------- */
.ask-foot {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--s-3);
}

.confirm-btn {
  padding: 8px 20px;
  border-radius: var(--r-pill);
  background: var(--c-brand);
  color: #fff;
  font-size: var(--f-sm);
  font-weight: 600;
  transition: background var(--t-fast) var(--ease-soft);
}

.confirm-btn:hover:not(:disabled) {
  background: var(--c-brand-deep);
}

.confirm-btn:disabled {
  background: var(--c-bg-hover);
  color: var(--c-text-3);
  cursor: default;
}
</style>
