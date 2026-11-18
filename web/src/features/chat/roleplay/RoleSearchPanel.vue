<script setup lang="ts">
/**
 * 「AI 帮我查」面板。
 *
 * 流程：
 *   用户说一句「想扮演谁」→ 点生成 → 后端联网搜资料 + 整理成档案（十几秒）
 *   → 生成完把内容交给 RoleFormPanel，让用户确认后保存
 *
 * 为什么单独一个面板而不是直接调接口：
 *   这一步要联网 + 调模型，十几秒。必须有明确的「在做什么」提示，
 *   否则用户会以为卡死了反复点。
 */
import { computed, ref } from 'vue'
import { roleplayStore } from './store'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  /** 生成完成，把草稿交给父组件去填表单 */
  done: []
}>()

const { state } = roleplayStore
const query = ref('')
const error = ref('')

const canGenerate = computed(
  () => query.value.trim().length > 0 && !state.drafting,
)

async function generate() {
  if (!canGenerate.value) return
  error.value = ''

  await roleplayStore.draftRole(query.value.trim())

  if (state.draftError) {
    error.value = state.draftError
    return
  }

  emit('done')
}

/** 关掉时清空，下次打开是干净的 */
function close() {
  if (state.drafting) return // 生成中不让关，避免用户以为没生效
  query.value = ''
  error.value = ''
  roleplayStore.clearDraft()
  emit('close')
}

/** 示例输入，点一下就能用 */
const EXAMPLES = ['林黛玉', '马斯克', '我的大学室友', '一个爱吐槽的健身房教练']
</script>

<template>
  <Transition name="panel">
    <div v-if="props.open" class="panel-mask" @click.self="close">
      <aside class="panel">
        <header class="panel-head">
          <div>
            <div class="panel-title">AI 帮我查</div>
            <div class="panel-sub">说一个名字或描述，AI 会联网搜资料整理成角色</div>
          </div>
          <button type="button" class="panel-close" :disabled="state.drafting" @click="close">
            ✕
          </button>
        </header>

        <div class="panel-body">
          <!-- 生成中 -->
          <div v-if="state.drafting" class="loading">
            <div class="spinner" />
            <div class="loading-title">正在搜集资料…</div>
            <p class="loading-desc">
              会联网搜索相关内容，再整理成性格、说话方式和开场白。<br />
              通常需要十几秒，请稍等。
            </p>
          </div>

          <!-- 输入 -->
          <template v-else>
            <div class="field">
              <label class="label">想扮演谁？</label>
              <input
                v-model="query"
                class="input"
                maxlength="60"
                placeholder="比如：林黛玉、马斯克、一个爱吐槽的室友"
                @keydown.enter="generate"
              />
            </div>

            <div class="examples">
              <span class="examples-label">试试：</span>
              <button
                v-for="item in EXAMPLES"
                :key="item"
                type="button"
                class="example"
                @click="query = item"
              >
                {{ item }}
              </button>
            </div>

            <div v-if="error" class="form-error">{{ error }}</div>

            <p class="note">
              生成的内容可以先改再保存。资料不全时 AI 会按人物常识整理，建议自己再润色一下。
            </p>
          </template>
        </div>

        <footer v-if="!state.drafting" class="panel-foot">
          <button type="button" class="ghost-btn" @click="close">取消</button>
          <button type="button" class="primary-btn" :disabled="!canGenerate" @click="generate">
            开始生成
          </button>
        </footer>
      </aside>
    </div>
  </Transition>
</template>

<style scoped>
.panel-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.18);
  z-index: var(--z-modal);
  display: flex;
  justify-content: flex-end;
}

.panel {
  width: min(460px, 94vw);
  height: 100%;
  background: var(--c-bg);
  display: flex;
  flex-direction: column;
  box-shadow: var(--sh-pop);
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: var(--s-4) var(--s-5);
  border-bottom: 1px solid var(--c-line);
  flex-shrink: 0;
}

.panel-title {
  font-size: var(--f-md);
  font-weight: 650;
}

.panel-sub {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  margin-top: 2px;
}

.panel-close {
  width: 28px;
  height: 28px;
  border-radius: var(--r-sm);
  color: var(--c-text-3);
  display: grid;
  place-items: center;
  font-size: 13px;
}

.panel-close:hover:not(:disabled) {
  background: var(--c-bg-hover);
  color: var(--c-text);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.label {
  font-size: var(--f-sm);
  font-weight: 600;
  color: var(--c-text-2);
}

.input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-md);
  background: var(--c-bg);
  font-size: var(--f-base);
  color: var(--c-text);
}

.input:focus {
  outline: none;
  border-color: var(--c-brand-line);
  box-shadow: 0 0 0 3px var(--c-brand-glow);
}

.input::placeholder {
  color: var(--c-text-3);
}

/* ---------- 示例 ---------- */
.examples {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
}

.examples-label {
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

.example {
  padding: 5px 12px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-pill);
  font-size: var(--f-sm);
  color: var(--c-text-2);
  background: var(--c-bg);
  transition:
    border-color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft);
}

.example:hover {
  border-color: var(--c-line-strong);
  background: var(--c-bg-soft);
}

/* ---------- 生成中 ---------- */
.loading {
  text-align: center;
  padding: var(--s-10) var(--s-4);
}

.spinner {
  width: 26px;
  height: 26px;
  margin: 0 auto var(--s-4);
  border: 2.5px solid var(--c-line-strong);
  border-top-color: var(--c-brand);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.loading-title {
  font-size: var(--f-base);
  font-weight: 600;
  color: var(--c-text);
}

.loading-desc {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
  margin-top: var(--s-2);
}

.note {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
}

.form-error {
  font-size: var(--f-sm);
  color: var(--c-danger);
  background: var(--c-danger-soft);
  border-radius: var(--r-sm);
  padding: 8px 12px;
}

/* ---------- 底部 ---------- */
.panel-foot {
  display: flex;
  gap: var(--s-2);
  justify-content: flex-end;
  padding: var(--s-4) var(--s-5);
  border-top: 1px solid var(--c-line);
  flex-shrink: 0;
}

.ghost-btn {
  padding: 8px 16px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-pill);
  background: var(--c-bg);
  font-size: var(--f-sm);
  color: var(--c-text-2);
}

.ghost-btn:hover {
  background: var(--c-bg-soft);
}

.primary-btn {
  padding: 8px 20px;
  border-radius: var(--r-pill);
  background: var(--c-brand);
  color: #fff;
  font-size: var(--f-sm);
  font-weight: 600;
}

.primary-btn:hover:not(:disabled) {
  background: var(--c-brand-deep);
}

.primary-btn:disabled {
  background: var(--c-bg-hover);
  color: var(--c-text-3);
  cursor: default;
}

/* ---------- 过渡 ---------- */
.panel-enter-active,
.panel-leave-active {
  transition: opacity var(--t-normal) var(--ease-soft);
}

.panel-enter-active .panel,
.panel-leave-active .panel {
  transition: transform var(--t-normal) var(--ease-soft);
}

.panel-enter-from,
.panel-leave-to {
  opacity: 0;
}

.panel-enter-from .panel,
.panel-leave-to .panel {
  transform: translateX(100%);
}
</style>
