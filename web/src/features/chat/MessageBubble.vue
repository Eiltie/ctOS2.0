<script setup lang="ts">
/**
 * 一条消息气泡。
 *
 * 样式：用户和 AI 各有一块浅灰底，左/右对齐区分谁在说话。
 * 曾尝试过「无容器纯文字流」（参考 Claude / 豆包那种排版），
 * 空状态下更干净，但对话一多，气泡的左右结构更好扫读，所以保留气泡。
 *
 * 朝向说话人的那一角收小，让气泡有方向感；
 * 流式输出时会显示一个闪烁光标。
 */
import { computed } from 'vue'
import type { UiMessage } from './store'
import AttachmentImage from '@/shared/attachments/AttachmentImage.vue'
import GeneratedImage from '@/shared/attachments/GeneratedImage.vue'

const props = defineProps<{
  message: UiMessage
}>()

const emit = defineEmits<{
  /** 点开大图 */
  openImage: [imageId: number]
}>()

const isUser = computed(() => props.message.role === 'user')
const isStreaming = computed(() => props.message.streaming === true)

/**
 * 从回复里拆出「生成的图」和「纯文字」。
 *
 * 后端在生图成功时会在流末尾追加一行 `[IMAGE:123]`。
 * 这里把它剥出来单独渲染成图片（带下载），剩下的才是正文。
 *
 * 为什么不在后端直接发结构化事件：
 *   /chat 返回的是纯文本流，加事件要改接口格式。
 *   在文本里放标记，接口形态不变，前端解析一下就行。
 */
const IMAGE_MARK_RE = /\s*\[IMAGE:(\d+)\]\s*/g

const parsed = computed(() => {
  const raw = props.message.content || ''

  const ids: number[] = []
  const text = raw.replace(IMAGE_MARK_RE, (_match, id: string) => {
    ids.push(Number(id))
    return '\n'
  })

  return {
    text: text.replace(/\n{3,}/g, '\n\n').trim(),
    imageIds: ids,
  }
})

/** 正文（可能带流式光标） */
const bodyText = computed(() => parsed.value.text)

/** 生成的图（后端追加标记的那些） */
const generatedImages = computed(() => parsed.value.imageIds)

/** 用户上传的图（走 message.images） */
const uploadedImages = computed(() => props.message.images)

const isEmptyStreaming = computed(
  () => isStreaming.value && !bodyText.value && generatedImages.value.length === 0,
)

/**
 * 把回复按空行拆成段落。
 *
 * 为什么需要：
 *   模型的长回复里，段落之间是一个空行。如果整段文字用 pre-wrap 渲染，
 *   两个段落会紧贴在一起，读起来很累。
 *   拆成独立的 <p> 之后，段落间距可以单独控制，
 *   而且流式输出时新段落也会自然出现（内容是增量更新的，computed 会跟着重算）。
 */
const paragraphs = computed(() => {
  const raw = bodyText.value
  if (!raw) return []

  return raw
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
})
</script>

<template>
  <div class="msg" :class="isUser ? 'msg--me' : 'msg--ai'">
    <div class="msg-avatar">{{ isUser ? 'V' : 'ct' }}</div>

    <div class="msg-body">
      <!-- 用户上传的图片附件：真的把图取出来显示，而不是只显示 id -->
      <div v-if="uploadedImages.length" class="msg-images">
        <AttachmentImage
          v-for="id in uploadedImages"
          :key="id"
          :image-id="id"
          clickable
          @open="emit('openImage', id)"
        />
      </div>

      <!-- 正在等第一个字 -->
      <div v-if="isEmptyStreaming" class="msg-bubble msg-bubble--typing">
        <span class="dot" />
        <span class="dot" />
        <span class="dot" />
      </div>

      <!-- 正文：按段落渲染，长回复的段落之间才有呼吸空间 -->
      <div v-else class="msg-bubble">
        <p v-for="(para, index) in paragraphs" :key="index" class="msg-para">
          {{ para }}
        </p>
        <span v-if="isStreaming" class="cursor" aria-hidden="true" />
      </div>

      <!-- AI 生成的图：后端在流末尾追加 [IMAGE:id]，这里渲成图并给下载 -->
      <div v-if="generatedImages.length" class="msg-generated">
        <GeneratedImage
          v-for="id in generatedImages"
          :key="id"
          :image-id="id"
        />
      </div>

      <!-- 出错 -->
      <div v-if="message.error" class="msg-error">{{ message.error }}</div>
    </div>
  </div>
</template>

<style scoped>
.msg {
  display: flex;
  /* 头像和文字之间留够距离：AI 去了气泡底，这个 gap 就成了唯一的分隔 */
  gap: var(--s-4);
  align-items: flex-start;
  /* 消息之间留空大一些：留白是「不廉价」最直接的来源 */
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

/* ---------- 头像 ---------- */
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

/* ---------- 气泡 ---------- */
.msg-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}

/*
 * AI 回复占满整列宽度。
 *
 * 之前 AI 和用户都用 82%，结果是：内容列明明有富余，
 * 气泡却只占八成，右侧又空出一截，看起来「窄列里套着更窄的气泡」。
 * 让 AI 占满，用户收窄，一宽一窄的对比反而让对话结构更清楚。
 */
.msg--ai .msg-body {
  flex: 1;
  max-width: 100%;
}

/* 用户消息：自己说的话通常短，给个上限就够，右对齐 */
.msg--me .msg-body {
  align-items: flex-end;
  max-width: 72%;
}

.msg-bubble {
  padding: 12px 16px;
  border-radius: var(--r-xl);
  font-size: var(--f-md);
  line-height: var(--lh-relaxed);
  color: var(--c-text);
  word-break: break-word;
  transition: background var(--t-fast) var(--ease-soft);
}

/*
 * AI 回复：没有底色，像正文一样直接排在页面上。
 *
 * 为什么去掉气泡底：
 *   一屏里好几块浅灰，看着像蒙了一层，读长文本也显得闷。
 *   去掉之后 AI 的话就是「页面上的文字」，干净、也不抢视线。
 *   左右位置和头像足以说明这是谁说的，不需要靠底色框起来。
 *
 * 内边距：
 *   上下保留（和用户气泡行高一致，换行时不会突然变紧），
 *   左右去掉——否则文字会比容器缩进一截，看着没对齐。
 *   和头像之间靠 .msg 的 gap 留出距离。
 */
.msg--ai .msg-bubble {
  background: transparent;
  padding-left: 0;
  padding-right: 0;
}

/*
 * 用户消息：保留一层极浅的底，用来区分「你说过的话」和 AI 的回复。
 * 右上角收小，指向自己的头像。
 *
 * 为什么用户有底、AI 没有：
 *   用户说的话短、数量少，给个底一眼能认出来；
 *   AI 的话才是阅读的重点，不框起来更干净。
 */
.msg--me .msg-bubble {
  background: var(--c-bubble-me);
  border-top-right-radius: var(--r-sm);
}

/* 段落：长回复靠这个间距分出层次 */
.msg-para {
  margin: 0;
  /* 段落内部保留换行（比如列表、分行的话） */
  white-space: pre-wrap;
}

.msg-para + .msg-para {
  margin-top: 0.9em;
}

/* 流式光标 */
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

/* ---------- 等待中的三个点 ---------- */
.msg-bubble--typing {
  display: inline-flex;
  gap: 4px;
  padding: 14px 16px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-text-3);
  animation: bounce 1.2s infinite;
}

.dot:nth-child(2) {
  animation-delay: 0.15s;
}

.dot:nth-child(3) {
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

/* ---------- 图片 ---------- */
.msg-images {
  display: flex;
  gap: var(--s-2);
  flex-wrap: wrap;
  margin-bottom: 2px;
}

/* AI 生成的图：跟在正文下面，不并排 */
.msg-generated {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

/* ---------- 错误 ---------- */
.msg-error {
  font-size: var(--f-sm);
  color: var(--c-danger);
  background: var(--c-danger-soft);
  border-radius: var(--r-sm);
  padding: 5px 10px;
}
</style>

