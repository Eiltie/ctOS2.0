<script setup lang="ts">
/**
 * 输入框 —— 对话类界面共用的那个底部输入区。
 *
 * 三个细节值得注意：
 *   1. 高度随内容自动变高（多行时不换行、不撑爆），最多到 max-height
 *   2. Enter 发送、Shift+Enter 换行
 *   3. 输入法（中文拼音）还在选字时按 Enter，不能当成发送
 */
import { nextTick, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    /** 正在生成回复时禁用发送 */
    disabled?: boolean
    /** 是否支持图片 */
    allowImage?: boolean
    /** 没有文字时也可以发（用于「只发图」） */
    allowEmpty?: boolean
    maxHeight?: number
  }>(),
  {
    placeholder: '说点什么…',
    disabled: false,
    allowImage: false,
    allowEmpty: false,
    maxHeight: 160,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
  pickImage: []
  stop: []
}>()

const textarea = ref<HTMLTextAreaElement | null>(null)

/** 输入法组合中：此时按 Enter 是选字，不是发送 */
let composing = false

/**
 * 能不能发。
 *
 * 平时要求有文字。
 * 但用户可能只想发一张图不打字（比如「看看这是什么」），
 * 这时 allowEmpty 为 true，只要有待发内容就允许发。
 */
const canSend = () =>
  !props.disabled && (props.modelValue.trim().length > 0 || props.allowEmpty)

function resize() {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, props.maxHeight)}px`
}

watch(
  () => props.modelValue,
  () => {
    void nextTick(resize)
  },
)

function onInput(event: Event) {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter') return
  if (event.shiftKey) return // Shift+Enter 换行，交给浏览器默认行为
  if (composing) return // 输入法选字中

  event.preventDefault()

  // 生成中按回车不发，但也不把焦点弄丢 —— 用户可以接着打下一句
  if (!canSend()) return

  emit('send')

  // 发送后把焦点还给输入框。
  //   为什么要显式做：虽然这里没有 disabled，但某些浏览器在
  //   内容被清空 / 按钮状态变化时会把焦点丢掉，用户还得再点一下才能继续打字。
  void nextTick(() => textarea.value?.focus())
}

function onCompositionStart() {
  composing = true
}

function onCompositionEnd() {
  composing = false
}

/** 从外部调用：发送后清空并让输入框回到单行高度 */
async function clear() {
  emit('update:modelValue', '')
  await nextTick()
  resize()
}

defineExpose({ clear, focus: () => textarea.value?.focus() })
</script>

<template>
  <div class="composer">
    <div class="composer-box">
      <!--
        待发图片：已经上传、还没发出去的。
        放在输入框上方，让用户看到「这条消息会带几张图」。
      -->
      <div v-if="$slots.pending" class="composer-pending">
        <slot name="pending" />
      </div>

      <div class="composer-row">
        <button
          v-if="allowImage"
          type="button"
          class="composer-icon"
          title="上传图片"
          :disabled="disabled"
          @click="emit('pickImage')"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect x="3" y="4.5" width="18" height="15" rx="3" />
            <circle cx="8.5" cy="10" r="1.6" />
            <path d="m4 17 5-4.5 4 3.5 3-2.5 4 3.5" />
          </svg>
        </button>

        <textarea
          ref="textarea"
          class="composer-input"
          rows="1"
          :value="modelValue"
          :placeholder="placeholder"
          @input="onInput"
          @keydown="onKeydown"
          @compositionstart="onCompositionStart"
          @compositionend="onCompositionEnd"
        />

        <!-- 生成中显示「停止」，否则显示「发送」 -->
        <button
          v-if="disabled"
          type="button"
          class="composer-send composer-send--stop"
          title="停止生成"
          @click="emit('stop')"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
        </button>
        <button
          v-else
          type="button"
          class="composer-send"
          :class="{ 'composer-send--off': !canSend() }"
          :disabled="!canSend()"
          title="发送（Enter）"
          @click="canSend() && emit('send')"
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.4"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M12 19V5" />
            <path d="m5.5 11.5 6.5-6.5 6.5 6.5" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.composer {
  padding: 12px var(--s-6) var(--s-5);
  flex-shrink: 0;
}

.composer-box {
  /* 和上面的消息列一样居中，保持同一条中线 */
  max-width: var(--w-content);
  margin: 0 auto;
  padding: 12px 12px 10px 16px;
  background: var(--c-bg);
  border: 1.5px solid var(--c-line);
  /* 输入框用很大的圆角，视觉上是个「胶囊」，比方形盒子柔和得多 */
  border-radius: var(--r-2xl);
  transition:
    border-color var(--t-normal) var(--ease-soft),
    box-shadow var(--t-normal) var(--ease-soft);
}

.composer-box:focus-within {
  border-color: var(--c-brand-line);
  box-shadow: 0 0 0 5px var(--c-brand-glow);
}

.composer-row {
  display: flex;
  align-items: flex-end;
  gap: var(--s-2);
}

/* 待发图片预览区 */
.composer-pending {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  padding: 0 0 var(--s-3) 0;
}

.composer-input {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  font-size: var(--f-md);
  line-height: var(--lh-normal);
  min-height: 24px;
  max-height: 160px;
  padding: 3px 0;
}

.composer-input::placeholder {
  color: var(--c-text-3);
}

.composer-icon,
.composer-send {
  width: 32px;
  height: 32px;
  border-radius: var(--r-pill); /* 圆形按钮 */
  display: grid;
  place-items: center;
  flex-shrink: 0;
  transition:
    background var(--t-fast) var(--ease-soft),
    color var(--t-fast) var(--ease-soft),
    opacity var(--t-fast) var(--ease-soft),
    transform var(--t-fast) var(--ease-soft);
}

.composer-icon {
  color: var(--c-text-3);
}

.composer-icon:hover:not(:disabled) {
  background: var(--c-bg-hover);
  color: var(--c-text-2);
}

.composer-send {
  /* 这是整个页面唯一保留彩色的主操作 —— 彩色只出现在「这里该点」的地方 */
  background: var(--c-brand);
  color: #fff;
}

.composer-send:hover:not(:disabled) {
  background: var(--c-brand-deep);
  transform: scale(1.06);
}

.composer-send:active:not(:disabled) {
  transform: scale(0.96);
}

/* 没输入内容时：退回灰，不抢注意力 */
.composer-send--off {
  background: var(--c-bg-hover);
  color: var(--c-text-3);
  cursor: default;
}

.composer-send--stop {
  background: var(--c-coffee);
}
</style>
