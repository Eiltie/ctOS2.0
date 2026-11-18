<script setup lang="ts">
/**
 * 出行里的一轮。
 *
 * 三种形态：
 *   CHAT   —— 一个普通气泡（Agent 直接回答）
 *   ROUTE  —— 四段卡片：需求确认 / 路线对比 / 推荐方案 / 出发提醒
 *   TRAVEL —— 四段卡片：天气 / 景点清单 / 行程安排 / 游玩建议
 *
 * 每一段都可能还在流式输出，所以卡片表头显示「生成中」或「完成」。
 * 停下来等用户操作时，下面挂对应的面板。
 */
import { computed } from 'vue'
import type { TripTurn } from './events'
import { GUIDE_SECTIONS, ROUTE_SECTIONS, SECTION_LABELS } from './events'
import RouteAskPanel from './RouteAskPanel.vue'
import PlaceAskPanel from './PlaceAskPanel.vue'
import SpotsAskPanel from './SpotsAskPanel.vue'
import AttachmentImage from '@/shared/attachments/AttachmentImage.vue'
import GeneratedImage from '@/shared/attachments/GeneratedImage.vue'
import { tripStore } from './store'

const props = defineProps<{
  turn: TripTurn
  /** 这一轮之后还有没有别的轮（用来决定要不要留间隔） */
  isLast: boolean
}>()

/** 这一轮该显示哪些段落（按形态） */
const sectionKeys = computed(() => {
  if (props.turn.kind === 'ROUTE') return ROUTE_SECTIONS
  if (props.turn.kind === 'TRAVEL') return GUIDE_SECTIONS
  return []
})

/** 已经出现过内容的段（按出现顺序） */
const visibleSections = computed(() =>
  props.turn.sectionStates.filter((s) => props.turn.sections[s.key]?.length),
)

const kindLabel = computed(() => {
  if (props.turn.kind === 'ROUTE') return '路线'
  if (props.turn.kind === 'TRAVEL') return '攻略'
  return ''
})

/** 进度：第几段 / 共几段 */
const progressText = computed(() => {
  if (!sectionKeys.value.length) return ''
  const done = props.turn.sectionStates.filter((s) => s.done).length
  return `${done}/${sectionKeys.value.length}`
})
</script>

<template>
  <div class="turn">
    <!-- 用户提问 -->
    <div class="msg msg--me">
      <div class="msg-avatar">V</div>
      <div class="msg-body">
        <!-- 这一轮带的图片 -->
        <div v-if="turn.images.length" class="msg-images">
          <AttachmentImage v-for="id in turn.images" :key="id" :image-id="id" />
        </div>
        <div class="msg-bubble">{{ turn.query }}</div>
      </div>
    </div>

    <!-- ==================== CHAT：直接回答 ==================== -->
    <div v-if="turn.kind === 'CHAT' && (turn.chatReply || turn.streaming)" class="msg msg--ai">
      <div class="msg-avatar">ct</div>
      <div class="msg-body">
        <div v-if="turn.streaming && !turn.chatReply" class="msg-bubble msg-bubble--typing">
          {{ turn.phase || '正在思考…' }}
          <span class="dot" /><span class="dot" /><span class="dot" />
        </div>
        <div v-else class="msg-bubble-plain">{{ turn.chatReply }}</div>

        <!-- AI 生成的图（路线示意图 / 行程海报） -->
        <div v-if="turn.imageIds.length" class="msg-generated">
          <GeneratedImage v-for="id in turn.imageIds" :key="id" :image-id="id" />
        </div>
      </div>
    </div>

    <!-- ==================== ROUTE / TRAVEL：四段卡片 ==================== -->
    <div v-if="turn.kind !== 'CHAT'" class="turn-body">
      <!-- 形态标签 + 进度 -->
      <div class="turn-head">
        <span class="kind-badge" :class="`kind-badge--${turn.kind.toLowerCase()}`">
          {{ turn.kind === 'ROUTE' ? '🛣' : '🗺' }} {{ kindLabel }}
        </span>
        <span v-if="turn.streaming && turn.phase" class="turn-phase">{{ turn.phase }}</span>
        <span v-else-if="progressText" class="turn-progress">{{ progressText }} 段完成</span>
      </div>

      <!-- 各段卡片 -->
      <div
        v-for="section in visibleSections"
        :key="section.key"
        class="section-card"
        :class="{ 'section-card--active': section.streaming }"
      >
        <div class="section-head">
          <span class="section-title">{{ SECTION_LABELS[section.key] ?? section.key }}</span>
          <span v-if="section.streaming" class="section-state section-state--doing">
            <span class="mini-dot" /> 生成中
          </span>
          <span v-else-if="section.done" class="section-state section-state--done">✓ 完成</span>
        </div>
        <div class="section-body">{{ turn.sections[section.key] }}</div>
      </div>

      <!-- 等用户操作的三个面板 -->
      <RouteAskPanel
        v-if="turn.pending?.kind === 'route'"
        :ask="turn.pending"
        @pick="(id) => tripStore.pickRouteOption(turn, id)"
      />
      <PlaceAskPanel
        v-else-if="turn.pending?.kind === 'place'"
        :ask="turn.pending"
        @pick="(place) => tripStore.pickPlaceOption(turn, place)"
      />
      <SpotsAskPanel
        v-else-if="turn.pending?.kind === 'spots'"
        :ask="turn.pending"
        @submit="(removed, added) => tripStore.submitSpots(turn, removed, added)"
      />

      <!-- 跑完后的补充说明（比如「要不要生成一张图」） -->
      <div v-if="turn.closingNote" class="turn-note">
        {{ turn.closingNote }}
      </div>

      <!-- AI 生成的图（路线示意图 / 行程海报） -->
      <div v-if="turn.imageIds.length" class="turn-images">
        <GeneratedImage v-for="id in turn.imageIds" :key="id" :image-id="id" />
      </div>

      <!-- 流式结束后什么都没有（比如模型空回复） -->
      <div
        v-if="!turn.streaming && !visibleSections.length && !turn.pending && !turn.error"
        class="turn-empty"
      >
        这次没有产出内容，换个说法再试
      </div>
    </div>

    <!-- 错误 -->
    <div v-if="turn.error" class="turn-error">{{ turn.error }}</div>

    <!-- 这一轮之后的间隔 -->
    <div v-if="!isLast" class="turn-divider" />
  </div>
</template>

<style scoped>
.turn {
  margin-bottom: var(--s-8);
}

/* ---------- 用户提问 ---------- */
.msg {
  display: flex;
  gap: var(--s-4);
  align-items: flex-start;
  margin-bottom: var(--s-5);
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
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.msg--me .msg-body {
  align-items: flex-end;
  max-width: 72%;
}

.msg--ai .msg-body {
  flex: 1;
}

.msg-bubble {
  padding: 12px 16px;
  border-radius: var(--r-xl);
  border-top-right-radius: var(--r-sm);
  background: var(--c-bubble-me);
  font-size: var(--f-md);
  line-height: var(--lh-relaxed);
  white-space: pre-wrap;
  word-break: break-word;
}

/* 用户消息里的图片 */
.msg-images {
  display: flex;
  gap: var(--s-2);
  flex-wrap: wrap;
  margin-bottom: var(--s-1);
}

/* AI 生成的图（路线示意图 / 行程海报） */
.msg-generated {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.msg-bubble-plain {
  font-size: var(--f-md);
  line-height: var(--lh-relaxed);
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--c-text);
}

.msg-bubble--typing {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: transparent;
  padding: 4px 0;
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

.dot {
  width: 4px;
  height: 4px;
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
  }
  30% {
    opacity: 1;
  }
}

/* ---------- 轮次头部 ---------- */
.turn-body {
  padding-left: 44px;
}

.turn-head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-bottom: var(--s-3);
}

.kind-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--f-xs);
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--r-pill);
}

.kind-badge--route {
  background: var(--c-brand-soft);
  color: var(--c-brand-deep);
}

.kind-badge--travel {
  background: var(--c-warn-soft);
  color: var(--c-warn);
}

.turn-phase {
  font-size: var(--f-xs);
  color: var(--c-text-3);
}

.turn-progress {
  font-size: var(--f-xs);
  color: var(--c-text-3);
}

/* ---------- 段落卡片 ---------- */
.section-card {
  border: 1px solid var(--c-line);
  border-radius: var(--r-lg);
  background: var(--c-bg);
  margin-bottom: var(--s-3);
  overflow: hidden;
  transition: border-color var(--t-normal) var(--ease-soft);
}

.section-card--active {
  border-color: var(--c-line-strong);
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 14px;
  background: var(--c-bg-soft);
  border-bottom: 1px solid var(--c-line);
}

.section-title {
  font-size: var(--f-sm);
  font-weight: 650;
  color: var(--c-text-2);
}

.section-state {
  font-size: var(--f-xs);
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.section-state--doing {
  color: var(--c-text-3);
}

.section-state--done {
  color: var(--c-brand);
}

.mini-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--c-brand);
  animation: bounce 1.2s infinite;
}

.section-body {
  padding: 12px 14px;
  font-size: var(--f-base);
  line-height: var(--lh-relaxed);
  color: var(--c-text-2);
  white-space: pre-wrap;
  word-break: break-word;
}

/* 跑完后的补充说明 */
.turn-note {
  margin-top: var(--s-2);
  padding: 10px 14px;
  border-radius: var(--r-md);
  background: var(--c-bg-soft);
  font-size: var(--f-sm);
  line-height: var(--lh-normal);
  color: var(--c-text-2);
}

/* 生成的图 */
.turn-images {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin-top: var(--s-3);
}

/* ---------- 空/错误 ---------- */
.turn-empty {
  padding: var(--s-3) 0;
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

.turn-error {
  margin-left: 44px;
  padding: 8px 12px;
  border-radius: var(--r-md);
  background: var(--c-danger-soft);
  color: var(--c-danger);
  font-size: var(--f-sm);
}

.turn-divider {
  height: 1px;
  margin: var(--s-6) 0;
  background: var(--c-line);
}
</style>


