<script setup lang="ts">
/**
 * 景点勾选面板。
 *
 * 什么时候出现：攻略跑完景点清单后停下来，等用户确认
 * （见 modules/trip/guide/stream.py 的 ASK_SPOTS）。
 *
 * 后端给的是 spot_names（景点名数组），
 * 完整的景点介绍在前面的「景点清单」卡片里，这里只做勾选。
 *
 * 后端的参数：
 *   removed  用户去掉的景点名
 *   added    用户额外加的一个景点
 * 所以这里默认全部勾上，取消勾选的就是 removed。
 */
import { computed, ref } from 'vue'

const props = defineProps<{
  ask: {
    threadId: string
    question: string
    spotNames: string[]
  }
}>()

const emit = defineEmits<{
  submit: [removed: string[], added: string]
}>()

/** 勾选状态：默认全选 */
const checked = ref<Set<string>>(new Set(props.ask.spotNames))

/** 用户额外想加的地方 */
const added = ref('')

const removedList = computed(() =>
  props.ask.spotNames.filter((name) => !checked.value.has(name)),
)

const keptCount = computed(() => checked.value.size)

function toggle(name: string) {
  const next = new Set(checked.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  checked.value = next
}

/** 全选 / 全不选 */
function toggleAll() {
  if (checked.value.size === props.ask.spotNames.length) {
    checked.value = new Set()
  } else {
    checked.value = new Set(props.ask.spotNames)
  }
}

/** 一条都不留还提交，没意义 —— 按钮禁用 */
const canSubmit = computed(() => keptCount.value > 0 || added.value.trim().length > 0)

function submit() {
  if (!canSubmit.value) return
  emit('submit', removedList.value, added.value.trim())
}
</script>

<template>
  <div class="ask-panel">
    <div class="ask-head">
      <div class="ask-question">{{ ask.question }}</div>
      <button type="button" class="toggle-all" @click="toggleAll">
        {{ keptCount === ask.spotNames.length ? '全部取消' : '全部选中' }}
      </button>
    </div>

    <!-- 景点胶囊 -->
    <div class="spots">
      <button
        v-for="name in ask.spotNames"
        :key="name"
        type="button"
        class="spot"
        :class="{ 'spot--on': checked.has(name) }"
        @click="toggle(name)"
      >
        {{ name }}
      </button>
    </div>

    <!-- 额外加一个 -->
    <div class="add-row">
      <input
        v-model="added"
        class="add-input"
        maxlength="40"
        placeholder="还想加一个别的地方（选填）"
        @keydown.enter="submit"
      />
    </div>

    <!-- 底部 -->
    <div class="ask-foot">
      <span class="foot-hint">
        保留 <strong>{{ keptCount }}</strong> 个景点
        <template v-if="removedList.length">，去掉 {{ removedList.length }} 个</template>
      </span>
      <button type="button" class="confirm-btn" :disabled="!canSubmit" @click="submit">
        按这个排行程
      </button>
    </div>
  </div>
</template>

<style scoped>
.ask-panel {
  border: 1.5px solid var(--c-warn-soft);
  border-radius: var(--r-lg);
  background: var(--c-bg);
  padding: var(--s-4);
  margin-top: var(--s-3);
}

.ask-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-3);
  margin-bottom: var(--s-3);
}

.ask-question {
  font-size: var(--f-base);
  font-weight: 600;
  color: var(--c-text);
}

.toggle-all {
  flex-shrink: 0;
  font-size: var(--f-xs);
  color: var(--c-text-3);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.toggle-all:hover {
  color: var(--c-text-2);
}

/* ---------- 景点胶囊 ---------- */
.spots {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}

.spot {
  padding: 7px 14px;
  border: 1.5px solid var(--c-line);
  border-radius: var(--r-pill);
  background: var(--c-bg);
  font-size: var(--f-sm);
  color: var(--c-text-2);
  transition:
    border-color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft),
    color var(--t-fast) var(--ease-soft);
}

.spot:hover {
  border-color: var(--c-line-hover);
}

/* 选中：有勾 + 变色 */
.spot--on {
  border-color: var(--c-brand);
  background: var(--c-brand-soft);
  color: var(--c-brand-deep);
}

.spot--on::before {
  content: '✓ ';
  font-weight: 700;
}

/* ---------- 额外加 ---------- */
.add-row {
  margin-top: var(--s-3);
}

.add-input {
  width: 100%;
  padding: 9px 12px;
  border: 1px dashed var(--c-line-strong);
  border-radius: var(--r-md);
  background: transparent;
  font-size: var(--f-sm);
  color: var(--c-text);
}

.add-input::placeholder {
  color: var(--c-text-3);
}

.add-input:focus {
  outline: none;
  border-style: solid;
  border-color: var(--c-brand-line);
}

/* ---------- 底部 ---------- */
.ask-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  margin-top: var(--s-4);
}

.foot-hint {
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

.foot-hint strong {
  color: var(--c-text);
  font-weight: 650;
}

.confirm-btn {
  padding: 8px 20px;
  border-radius: var(--r-pill);
  background: var(--c-brand);
  color: #fff;
  font-size: var(--f-sm);
  font-weight: 600;
  flex-shrink: 0;
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
