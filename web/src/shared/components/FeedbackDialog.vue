<script setup lang="ts">
/**
 * 反馈弹窗。
 *
 * 后端（api/routes/feedback.py）的规则：
 *   · 不需要登录，未登录时 tenant_id 记为空
 *   · 评价和内容至少填一个
 *   · 同一 IP 每分钟最多 3 条（超了返回 429）
 *
 * 评价值必须是后端 VALID_RATINGS 里的四个之一，
 * page 必须是 chat / trip / customer / login 之一，否则后端会当没填。
 */
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { http } from '@/shared/api/http'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const route = useRoute()
const submitting = ref(false)
const done = ref(false)
const error = ref('')

/** 和后端 VALID_RATINGS 一致 */
const RATINGS = [
  { value: '很满意', emoji: '😍' },
  { value: '满意', emoji: '🙂' },
  { value: '一般', emoji: '😐' },
  { value: '不太满意', emoji: '🙁' },
] as const

const form = reactive({
  rating: '' as string,
  content: '',
  contact: '',
})

/** 当前在哪个页面：把路由名映射成后端认识的 page 值 */
const page = computed(() => {
  const name = String(route.name ?? '')
  if (name.startsWith('trip')) return 'trip'
  if (name.startsWith('customer')) return 'customer'
  if (name.startsWith('chat')) return 'chat'
  return ''
})

/** 至少选了评价或写了内容 */
const canSubmit = computed(
  () => (form.rating !== '' || form.content.trim() !== '') && !submitting.value,
)

watch(
  () => props.open,
  (open) => {
    if (!open) return
    form.rating = ''
    form.content = ''
    form.contact = ''
    error.value = ''
    done.value = false
  },
)

async function submit() {
  if (!canSubmit.value) return

  submitting.value = true
  error.value = ''

  try {
    await http.post('/feedback', {
      rating: form.rating || null,
      content: form.content.trim(),
      contact: form.contact.trim(),
      page: page.value,
    })
    done.value = true
  } catch (e) {
    const message = e instanceof Error ? e.message : '提交失败'
    // 429 是后端限流，文案已经是中文了
    error.value = message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Transition name="modal">
    <div v-if="open" class="mask" @click.self="emit('close')">
      <div class="dialog" role="dialog" aria-modal="true">
        <button type="button" class="dialog-close" @click="emit('close')">✕</button>

        <!-- 提交成功 -->
        <template v-if="done">
          <div class="done">
            <div class="done-icon">🙏</div>
            <h2>谢谢你的反馈</h2>
            <p>我看到会认真处理。如果留了联系方式，可能会联系你。</p>
            <button type="button" class="primary" @click="emit('close')">好的</button>
          </div>
        </template>

        <!-- 表单 -->
        <template v-else>
          <div class="dialog-head">
            <h2>说说你的想法</h2>
            <p class="sub">用着哪里别扭、想要什么功能，都可以说</p>
          </div>

          <div class="dialog-body">
            <!-- 评价 -->
            <div class="field">
              <span class="label">整体感觉（可选）</span>
              <div class="ratings">
                <button
                  v-for="item in RATINGS"
                  :key="item.value"
                  type="button"
                  class="rating"
                  :class="{ 'rating--on': form.rating === item.value }"
                  @click="form.rating = form.rating === item.value ? '' : item.value"
                >
                  <span class="rating-emoji">{{ item.emoji }}</span>
                  <span class="rating-label">{{ item.value }}</span>
                </button>
              </div>
            </div>

            <!-- 内容 -->
            <label class="field">
              <span class="label">具体说说</span>
              <textarea
                v-model="form.content"
                class="input textarea"
                rows="4"
                maxlength="500"
                placeholder="遇到了什么问题？或者希望加什么功能？"
              />
              <span class="counter">{{ form.content.length }}/500</span>
            </label>

            <!-- 联系方式 -->
            <label class="field">
              <span class="label">联系方式（选填）</span>
              <input
                v-model="form.contact"
                class="input"
                maxlength="100"
                placeholder="邮箱或其他，方便我回复你"
              />
            </label>

            <p v-if="error" class="error">{{ error }}</p>
          </div>

          <div class="dialog-foot">
            <button type="button" class="primary" :disabled="!canSubmit" @click="submit">
              {{ submitting ? '提交中…' : '提交' }}
            </button>
            <p class="foot-hint">至少选一个评价或写点内容</p>
          </div>
        </template>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  background: rgba(16, 24, 40, 0.28);
  display: grid;
  place-items: center;
  padding: var(--s-5);
}

.dialog {
  position: relative;
  width: min(440px, 100%);
  background: var(--c-bg);
  border-radius: var(--r-2xl);
  box-shadow: var(--sh-pop);
  padding: var(--s-6);
}

.dialog-close {
  position: absolute;
  top: var(--s-4);
  right: var(--s-4);
  width: 28px;
  height: 28px;
  border-radius: var(--r-sm);
  color: var(--c-text-3);
  display: grid;
  place-items: center;
  font-size: 13px;
}

.dialog-close:hover {
  background: var(--c-bg-hover);
  color: var(--c-text);
}

/* ---------- 头部 ---------- */
.dialog-head {
  margin-bottom: var(--s-5);
}

.dialog-head h2 {
  font-size: var(--f-xl);
  font-weight: 650;
  color: var(--c-text);
}

.sub {
  margin-top: var(--s-1);
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

/* ---------- 表单 ---------- */
.dialog-body {
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

/* 评价按钮 */
.ratings {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--s-2);
}

.rating {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 10px 4px;
  border: 1.5px solid var(--c-line);
  border-radius: var(--r-md);
  background: var(--c-bg);
  transition:
    border-color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft);
}

.rating:hover {
  border-color: var(--c-line-hover);
  background: var(--c-bg-soft);
}

.rating--on {
  border-color: var(--c-brand);
  background: var(--c-brand-soft);
}

.rating-emoji {
  font-size: 20px;
  line-height: 1;
}

.rating-label {
  font-size: var(--f-xs);
  color: var(--c-text-3);
}

.rating--on .rating-label {
  color: var(--c-brand-deep);
  font-weight: 600;
}

/* 输入 */
.input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-md);
  background: var(--c-bg);
  font-size: var(--f-base);
  color: var(--c-text);
  font-family: inherit;
  transition:
    border-color var(--t-fast) var(--ease-soft),
    box-shadow var(--t-fast) var(--ease-soft);
}

.input::placeholder {
  color: var(--c-text-3);
}

.input:focus {
  outline: none;
  border-color: var(--c-brand-line);
  box-shadow: 0 0 0 3px var(--c-brand-glow);
}

.textarea {
  resize: vertical;
  line-height: var(--lh-normal);
}

.counter {
  align-self: flex-end;
  font-size: 10px;
  color: var(--c-text-3);
  margin-top: -2px;
}

.error {
  font-size: var(--f-sm);
  color: var(--c-danger);
  background: var(--c-danger-soft);
  border-radius: var(--r-sm);
  padding: 8px 12px;
}

/* ---------- 底部 ---------- */
.dialog-foot {
  margin-top: var(--s-5);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-2);
}

.primary {
  width: 100%;
  padding: 11px;
  border-radius: var(--r-pill);
  background: var(--c-brand);
  color: #fff;
  font-size: var(--f-base);
  font-weight: 600;
  transition: background var(--t-fast) var(--ease-soft);
}

.primary:hover:not(:disabled) {
  background: var(--c-brand-deep);
}

.primary:disabled {
  background: var(--c-bg-hover);
  color: var(--c-text-3);
  cursor: default;
}

.foot-hint {
  font-size: var(--f-xs);
  color: var(--c-text-3);
}

/* ---------- 成功 ---------- */
.done {
  text-align: center;
  padding: var(--s-4) 0;
}

.done-icon {
  font-size: 34px;
  line-height: 1;
  margin-bottom: var(--s-3);
}

.done h2 {
  font-size: var(--f-xl);
  font-weight: 650;
  color: var(--c-text);
}

.done p {
  margin: var(--s-2) 0 var(--s-5);
  font-size: var(--f-sm);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
}

/* ---------- 过渡 ---------- */
.modal-enter-active,
.modal-leave-active {
  transition: opacity var(--t-normal) var(--ease-soft);
}

.modal-enter-active .dialog,
.modal-leave-active .dialog {
  transition: transform var(--t-normal) var(--ease-soft);
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .dialog,
.modal-leave-to .dialog {
  transform: scale(0.96) translateY(8px);
}
</style>
