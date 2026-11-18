<script setup lang="ts">
/**
 * 智能出行。
 *
 * 布局和对话模块一致：
 *   左边一列出行记录，右边一列对话（由若干个 TripTurn 组成）。
 *
 * 和后端的设计对应：
 *   用户不需要选「我要路线还是攻略」，说一句话，
 *   Agent 自己判断走哪条子图。所以界面上也没有「模式切换」。
 *   每一轮的形态由事件决定，界面跟着画。
 */
import { computed, nextTick, ref, watch } from 'vue'
import ChatComposer from '@/shared/components/ChatComposer.vue'
import TripList from './TripList.vue'
import SidebarDrawer from '@/shared/components/SidebarDrawer.vue'
import TripTurnCard from './TripTurnCard.vue'
import PendingImages from '@/shared/attachments/PendingImages.vue'
import { MAX_IMAGES_PER_MESSAGE } from '@/shared/attachments/api'
import { tripStore } from './store'

const { state, imageQueue: images } = tripStore

const draft = ref('')
const feed = ref<HTMLElement | null>(null)
const composer = ref<InstanceType<typeof ChatComposer> | null>(null)

/** 隐藏的文件选择框 */
const fileInput = ref<HTMLInputElement | null>(null)

/** 空状态下的示例问题 */
const EXAMPLES = [
  '下周去杭州玩三天，带老人，少走路',
  '从杭州东站到灵隐寺怎么走',
  '北京有什么好玩的',
]

const hasTurns = computed(() => state.turns.length > 0)

/** 标题：有当前记录就显示标题，否则「新出行」 */
const title = computed(() => {
  if (state.currentTripId === null) return '新出行'
  const found = state.trips.find((t) => t.id === state.currentTripId)
  return found?.title ?? '出行'
})

/** 有没有在某处等用户操作 */
const waiting = computed(() => state.turns.some((t) => t.pending !== null))

function scrollToBottom(smooth = true) {
  void nextTick(() => {
    const el = feed.value
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  })
}

watch(() => state.turns.length, () => scrollToBottom())

// 流式输出时内容在长高，跟着滚
watch(
  () => {
    const last = state.turns.at(-1)
    if (!last) return ''
    return (
      last.chatReply +
      Object.values(last.sections).join('') +
      last.phase +
      (last.pending ? '1' : '')
    )
  },
  () => {
    if (state.running) scrollToBottom(false)
  },
)

function send(text?: string) {
  const content = text ?? draft.value
  if (state.running) return
  // 有图可以只发图
  if (!content.trim() && !images.hasAny.value) return

  draft.value = ''
  tripStore.ask(content)
  scrollToBottom()
}

function stop() {
  tripStore.stop()
}

// ---------------------------------------------------------------- 图片

/** 点相机按钮 → 打开文件选择 */
function pickImage() {
  if (images.count.value >= MAX_IMAGES_PER_MESSAGE) {
    images.state.error = `一条消息最多带 ${MAX_IMAGES_PER_MESSAGE} 张图片`
    return
  }
  fileInput.value?.click()
}

/** 选完文件 → 逐张上传 */
async function onFilesPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''

  const room = MAX_IMAGES_PER_MESSAGE - images.count.value
  for (const file of files.slice(0, room)) {
    await images.add(file)
  }

  if (files.length > room) {
    images.state.error = `一条消息最多带 ${MAX_IMAGES_PER_MESSAGE} 张图片，多选的已忽略`
  }

  composer.value?.focus()
}

/** 拖拽进来的图片 */
async function onDrop(event: DragEvent) {
  const files = Array.from(event.dataTransfer?.files ?? []).filter((f) =>
    f.type.startsWith('image/'),
  )
  if (!files.length) return

  const room = MAX_IMAGES_PER_MESSAGE - images.count.value
  for (const file of files.slice(0, room)) {
    await images.add(file)
  }
}

function pickExample(text: string) {
  send(text)
  composer.value?.focus()
}
</script>

<template>
  <div class="trip-view">
    <SidebarDrawer>
      <TripList />
    </SidebarDrawer>

    <main class="trip-main">
      <div class="trip-head">
        <div>
          <div class="trip-title">{{ title }}</div>
          <div class="trip-sub">
            <template v-if="waiting">有一步需要你确认</template>
            <template v-else-if="state.running">正在处理…</template>
            <template v-else-if="state.currentTripId !== null">
              {{ state.turns.length }} 轮对话
            </template>
            <template v-else>一句话说需求，它自己判断该干嘛</template>
          </div>
        </div>
      </div>

      <div ref="feed" class="trip-feed">
        <!-- 加载历史 -->
        <div v-if="state.turnsLoading" class="trip-inner">
          <div v-for="n in 2" :key="n" class="skeleton-row">
            <div class="skeleton-avatar" />
            <div class="skeleton-lines">
              <div class="skeleton-line" />
              <div class="skeleton-line skeleton-line--short" />
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-else-if="!hasTurns" class="trip-hero">
          <h2>想去哪儿？</h2>
          <p>说一句话就行。路线规划和旅游攻略是它内部的能力，你不用选。</p>

          <div class="examples">
            <button
              v-for="item in EXAMPLES"
              :key="item"
              type="button"
              class="example"
              @click="pickExample(item)"
            >
              {{ item }}
            </button>
          </div>
        </div>

        <!-- 对话 -->
        <div v-else class="trip-inner">
          <TripTurnCard
            v-for="(turn, index) in state.turns"
            :key="turn.uid"
            :turn="turn"
            :is-last="index === state.turns.length - 1"
          />
        </div>
      </div>

      <div @drop.prevent="onDrop" @dragover.prevent>
        <!-- 隐藏的文件选择框 -->
        <input
          ref="fileInput"
          type="file"
          accept="image/jpeg,image/png,image/gif,image/webp"
          multiple
          class="file-input"
          @change="onFilesPicked"
        />

        <ChatComposer
          ref="composer"
          v-model="draft"
          :placeholder="
            waiting
              ? '上面有一步需要先确认，也可以直接补充说明…'
              : '说说想去哪儿…（也可以发张图，比如景点照片）'
          "
          :disabled="state.running"
          allow-image
          :allow-empty="images.hasAny.value"
          @send="send()"
          @stop="stop"
          @pick-image="pickImage"
        >
          <template v-if="images.count.value || images.state.uploading" #pending>
            <PendingImages
              :images="images.state.images"
              :uploading="images.state.uploading"
              @remove="images.remove($event)"
            />
          </template>
        </ChatComposer>

        <div v-if="images.state.error" class="upload-error">
          {{ images.state.error }}
          <button type="button" class="upload-error-close" @click="images.clearError()">
            ✕
          </button>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.trip-view {
  flex: 1;
  display: flex;
  min-height: 0;
}

/* ---------- 左侧 ---------- */
.trip-sidebar {
  width: var(--w-sidebar);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--c-bg-sidebar);
  border-right: 1px solid var(--c-line);
  min-height: 0;
}

/* ---------- 右侧 ---------- */
.trip-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.trip-head {
  height: var(--h-head);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--s-5);
  border-bottom: 1px solid var(--c-line);
  flex-shrink: 0;
}

.trip-title {
  font-size: var(--f-md);
  font-weight: 650;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 60vw;
}

.trip-sub {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  margin-top: 1px;
}

/* ---------- 消息区 ---------- */
.trip-feed {
  flex: 1;
  overflow-y: auto;
  padding: var(--s-7) 0 var(--s-4);
  min-height: 0;
}

.trip-inner {
  max-width: var(--w-content);
  margin: 0 auto;
  padding: 0 var(--s-6);
}

/* ---------- 空状态 ---------- */
.trip-hero {
  max-width: 560px;
  margin: 0 auto;
  padding: var(--s-10) var(--s-6) 0;
  text-align: center;
}

.trip-hero h2 {
  font-size: 22px;
  font-weight: 650;
  color: var(--c-text);
}

.trip-hero p {
  font-size: var(--f-base);
  color: var(--c-text-3);
  margin-top: var(--s-2);
  line-height: var(--lh-normal);
}

.examples {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-top: var(--s-6);
}

.example {
  padding: 11px 16px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-lg);
  background: var(--c-bg);
  font-size: var(--f-base);
  color: var(--c-text-2);
  text-align: left;
  transition:
    border-color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft),
    color var(--t-fast) var(--ease-soft);
}

.example:hover {
  border-color: var(--c-line-hover);
  background: var(--c-bg-soft);
  color: var(--c-text);
}

/* ---------- 图片上传 ---------- */
.file-input {
  display: none;
}

.upload-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-2);
  max-width: var(--w-content);
  margin: var(--s-2) auto 0;
  padding: 7px 12px;
  border-radius: var(--r-md);
  background: var(--c-danger-soft);
  color: var(--c-danger);
  font-size: var(--f-sm);
}

.upload-error-close {
  color: var(--c-danger);
  font-size: 12px;
  line-height: 1;
  opacity: 0.7;
}

.upload-error-close:hover {
  opacity: 1;
}

/* ---------- 骨架 ---------- */
.skeleton-row {
  display: flex;
  gap: var(--s-4);
  margin-bottom: var(--s-7);
}

.skeleton-avatar {
  width: 30px;
  height: 30px;
  border-radius: var(--r-pill);
  background: var(--c-bg-soft);
  flex-shrink: 0;
  animation: pulse 1.4s ease-in-out infinite;
}

.skeleton-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding-top: 6px;
}

.skeleton-line {
  height: 12px;
  border-radius: var(--r-sm);
  background: var(--c-bg-soft);
  animation: pulse 1.4s ease-in-out infinite;
}

.skeleton-line--short {
  width: 55%;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.55;
  }
  50% {
    opacity: 1;
  }
}

/* ---------- 窄屏（≤ 768px）----------
   侧栏已经收进抽屉（SidebarDrawer），这里只管内容区 */
@media (max-width: 768px) {
  .trip-head {
    padding: 0 var(--m-pad);
  }

  .trip-title {
    max-width: 62vw;
  }

  .trip-inner {
    padding: 0 var(--m-pad);
  }

  .trip-feed {
    padding-top: var(--s-5);
  }

  .trip-hero {
    padding: var(--s-8) var(--m-pad) 0;
  }

  .trip-hero h2 {
    font-size: 19px;
  }

  /* 示例问题卡片：手机上文字要能换行 */
  .example {
    padding: 10px 13px;
    font-size: var(--f-sm);
    line-height: var(--lh-normal);
  }
}</style>



