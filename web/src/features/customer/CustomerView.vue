<script setup lang="ts">
/**
 * 智能客服。
 *
 * 和对话模块的区别：
 *   · 没有左侧列表 —— 后端不存会话，没有历史可列
 *   · 界面上明确写「刷新后对话不保留」
 *   · 上下文全靠前端带着（只带最近 3 轮）
 *
 * 布局参考了常见客服的样子：中间一列，空状态时居中放引导问题。
 */
import { computed, nextTick, ref, watch } from 'vue'
import ChatComposer from '@/shared/components/ChatComposer.vue'
import { customerStore } from './store'

const { state } = customerStore

const draft = ref('')
const feed = ref<HTMLElement | null>(null)
const composer = ref<InstanceType<typeof ChatComposer> | null>(null)

/** 引导问题：点一下直接问 */
const SUGGESTIONS = [
  '这个项目有哪些模块？',
  '客服是怎么检索的？',
  '出行是怎么规划的？',
  '怎么部署到服务器？',
]

const hasMessages = computed(() => state.messages.length > 0)

function scrollToBottom(smooth = true) {
  void nextTick(() => {
    const el = feed.value
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  })
}

watch(() => state.messages.length, () => scrollToBottom())

watch(
  () => state.messages.at(-1)?.content,
  () => {
    if (state.asking) scrollToBottom(false)
  },
)

function send(text?: string) {
  const content = text ?? draft.value
  if (!content.trim() || state.asking) return

  draft.value = ''
  customerStore.ask(content)
}

function stop() {
  customerStore.stop()
}

function clear() {
  customerStore.clear()
}

function pickSuggestion(text: string) {
  send(text)
  composer.value?.focus()
}
</script>

<template>
  <div class="customer-view">
    <div class="customer-head">
      <div>
        <div class="customer-title">智能客服</div>
        <div class="customer-sub">基于项目文档回答</div>
      </div>
      <button
        v-if="hasMessages"
        type="button"
        class="ghost-btn"
        @click="clear"
      >
        清空对话
      </button>
    </div>

    <div ref="feed" class="customer-feed">
      <!-- 空状态：大标题 + 引导问题 -->
      <div v-if="!hasMessages" class="customer-hero">
        <h2>有什么可以帮你的？</h2>
        <p>我只回答关于 ctOS 2.0 这个项目本身的问题</p>

        <div class="suggestions">
          <button
            v-for="item in SUGGESTIONS"
            :key="item"
            type="button"
            class="suggestion"
            @click="pickSuggestion(item)"
          >
            {{ item }}
          </button>
        </div>

        <p class="hero-note">
          客服不保存对话记录，刷新页面后需要重新问。
        </p>
      </div>

      <!-- 消息 -->
      <div v-else class="customer-inner">
        <div
          v-for="message in state.messages"
          :key="message.uid"
          class="msg"
          :class="message.role === 'user' ? 'msg--me' : 'msg--ai'"
        >
          <div class="msg-avatar">{{ message.role === 'user' ? 'V' : '客' }}</div>

          <div class="msg-body">
            <!-- 还没收到第一个字 -->
            <div
              v-if="message.streaming && !message.content"
              class="msg-content msg-typing"
            >
              <span class="phase">{{ state.phase || '正在思考…' }}</span>
              <span class="dot" />
              <span class="dot" />
              <span class="dot" />
            </div>

            <div v-else class="msg-content">
              {{ message.content
              }}<span v-if="message.streaming" class="cursor" aria-hidden="true" />
            </div>

            <div v-if="message.error" class="msg-error">{{ message.error }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="customer-composer">
      <ChatComposer
        ref="composer"
        v-model="draft"
        placeholder="问点关于这个项目的问题…"
        :disabled="state.asking"
        @send="send()"
        @stop="stop"
      />
      <p class="composer-note">刷新后对话不保留</p>
    </div>
  </div>
</template>

<style scoped>
.customer-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* ---------- 标题 ---------- */
.customer-head {
  height: var(--h-head);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  padding: 0 var(--s-5);
  border-bottom: 1px solid var(--c-line);
  flex-shrink: 0;
}

.customer-title {
  font-size: var(--f-md);
  font-weight: 650;
}

.customer-sub {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  margin-top: 1px;
}

.ghost-btn {
  padding: 6px 11px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-pill);
  background: var(--c-bg);
  font-size: var(--f-sm);
  color: var(--c-text-2);
  transition: background var(--t-fast) var(--ease-soft);
}

.ghost-btn:hover {
  background: var(--c-bg-soft);
}

/* ---------- 消息区 ---------- */
.customer-feed {
  flex: 1;
  overflow-y: auto;
  padding: var(--s-6) 0 var(--s-4);
  min-height: 0;
}

/* ---------- 空状态 ---------- */
.customer-hero {
  max-width: var(--w-content);
  margin: 0 auto;
  padding: var(--s-10) var(--s-6) 0;
  text-align: center;
}

.customer-hero h2 {
  font-size: 22px;
  font-weight: 650;
  color: var(--c-text);
  letter-spacing: -0.2px;
}

.customer-hero p {
  font-size: var(--f-base);
  color: var(--c-text-3);
  margin-top: var(--s-2);
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  justify-content: center;
  margin-top: var(--s-6);
}

.suggestion {
  padding: 8px 16px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-pill);
  background: var(--c-bg);
  font-size: var(--f-base);
  color: var(--c-text-2);
  transition:
    border-color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft),
    color var(--t-fast) var(--ease-soft);
}

.suggestion:hover {
  border-color: var(--c-line-strong);
  background: var(--c-bg-soft);
  color: var(--c-text);
}

.hero-note {
  margin-top: var(--s-8);
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

/* ---------- 消息 ---------- */
.customer-inner {
  max-width: var(--w-content);
  margin: 0 auto;
  padding: 0 var(--s-6);
}

.msg {
  display: flex;
  gap: var(--s-3);
  align-items: flex-start;
  margin-bottom: var(--s-7);
  animation: msg-in var(--t-slow) var(--ease-out) both;
}

@keyframes msg-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.msg--me {
  flex-direction: row-reverse;
}

.msg-avatar {
  width: 30px;
  height: 30px;
  border-radius: var(--r-pill);
  display: grid;
  place-items: center;
  font-size: var(--f-sm);
  flex-shrink: 0;
  background: var(--c-bg-hover);
  color: var(--c-text-2);
}

.msg--me .msg-avatar {
  font-weight: 600;
}

.msg-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

/* AI 占满，用户收窄右对齐（和对话模块一致） */
.msg--ai .msg-body {
  flex: 1;
  max-width: 100%;
}

.msg--me .msg-body {
  align-items: flex-end;
  max-width: 72%;
}

.msg-content {
  font-size: var(--f-md);
  line-height: var(--lh-relaxed);
  color: var(--c-text);
  white-space: pre-wrap;
  word-break: break-word;
}

/* AI 无底色，像正文 */
.msg--ai .msg-content {
  /* 客服的回答常带列表，保留换行 */
  white-space: pre-wrap;
}

/* 用户有浅底 */
.msg--me .msg-content {
  background: var(--c-bubble-me);
  padding: 12px 16px;
  border-radius: var(--r-xl);
  border-top-right-radius: var(--r-sm);
}

/* 光标 */
.cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -2px;
  background: var(--c-text-2);
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

/* 「正在检索」 */
.msg-typing {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 0;
}

.phase {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  margin-right: 2px;
}

.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--c-text-3);
  animation: bounce 1.2s infinite;
}

.dot:nth-child(3) {
  animation-delay: 0.15s;
}

.dot:nth-child(4) {
  animation-delay: 0.3s;
}

@keyframes bounce {
  0%,
  60%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

.msg-error {
  font-size: var(--f-sm);
  color: var(--c-danger);
  background: var(--c-danger-soft);
  border-radius: var(--r-sm);
  padding: 5px 10px;
}

/* ---------- 输入区 ---------- */
.customer-composer {
  flex-shrink: 0;
}

.composer-note {
  max-width: var(--w-content);
  margin: calc(-1 * var(--s-3)) auto var(--s-4);
  text-align: center;
  font-size: var(--f-xs);
  color: var(--c-text-3);
}

/* ---------- 窄屏（≤ 768px）---------- */
@media (max-width: 768px) {
  .customer-head {
    padding: 0 var(--m-pad);
  }

  .customer-inner {
    padding: 0 var(--m-pad);
  }

  .customer-feed {
    padding-top: var(--s-5);
  }

  .customer-hero {
    padding: var(--s-8) var(--m-pad) 0;
  }

  .customer-hero h2 {
    font-size: 19px;
  }

  /* 引导问题卡片 */
  .suggestion {
    padding: 10px 13px;
    font-size: var(--f-sm);
  }
}</style>

