<script setup lang="ts">
/**
 * 对话 · 闲聊。
 *
 * 这是「对话」模块的默认玩法。角色扮演是它的兄弟玩法（/chat/roles）。
 *
 * 布局：
 *   左侧会话列表（SessionList）+ 右侧对话区
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import ChatComposer from '@/shared/components/ChatComposer.vue'
import EmptyState from '@/shared/components/EmptyState.vue'
import MessageBubble from './MessageBubble.vue'
import SessionList from './SessionList.vue'
import PendingImages from '@/shared/attachments/PendingImages.vue'
import ImageLightbox from '@/shared/attachments/ImageLightbox.vue'
import { chatStore } from './store'
import { MAX_IMAGES_PER_MESSAGE } from '@/shared/attachments/api'
import { roleplayStore } from './roleplay/store'
import RoleProfilePanel from './roleplay/RoleProfilePanel.vue'
import RoleMemoryPanel from './roleplay/RoleMemoryPanel.vue'

const router = useRouter()
const { state, imageQueue: images } = chatStore

const draft = ref('')
const composer = ref<InstanceType<typeof ChatComposer> | null>(null)
const feed = ref<HTMLElement | null>(null)

/** 隐藏的文件选择框 */
const fileInput = ref<HTMLInputElement | null>(null)

/** 正在看大图的那张（null = 没开） */
const lightboxImage = ref<number | null>(null)

/** 当前是不是角色会话 */
const isRoleChat = computed(() => Boolean(state.activeRoleId))

/** 当前角色卡（拿名字和 emoji） */
const activeRole = computed(() =>
  roleplayStore.state.roles.find((role) => role.id === state.activeRoleId),
)

/** 标题：角色会话显示角色名，否则显示会话标题 */
const title = computed(() => {
  if (activeRole.value) return activeRole.value.name
  return chatStore.currentSession.value?.title ?? '新对话'
})

/** 消息条数（不含正在生成的那条空壳） */
const turnCount = computed(
  () => state.messages.filter((m) => !(m.streaming && !m.content)).length,
)

/** 副标题 */
const subtitle = computed(() => {
  const count = turnCount.value
  if (isRoleChat.value) {
    return count ? `角色扮演 · ${count} 条消息` : '角色扮演'
  }
  return count ? `闲聊 · ${count} 条消息` : '新对话'
})

/** 新消息进来时自动滚到底部 */
function scrollToBottom(smooth = true) {
  void nextTick(() => {
    const el = feed.value
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  })
}

watch(() => state.messages.length, () => scrollToBottom())

// 流式输出时，内容在长高，也要跟着滚
watch(
  () => state.messages.at(-1)?.content,
  () => {
    if (state.streaming) scrollToBottom(false)
  },
)

async function send() {
  const text = draft.value
  const hasImages = images.state.images.length > 0

  // 有图可以只发图；没图必须有文字
  if (state.streaming) return
  if (!text.trim() && !hasImages) return

  draft.value = ''
  await chatStore.send(text)
  composer.value?.focus()
}

function stop() {
  chatStore.stopStream()
}

// ---------------------------------------------------------------- 图片

/** 点相机按钮 → 打开系统文件选择 */
function pickImage() {
  if (images.state.images.length >= MAX_IMAGES_PER_MESSAGE) {
    images.state.error = `一条消息最多带 ${MAX_IMAGES_PER_MESSAGE} 张图片`
    return
  }
  fileInput.value?.click()
}

/** 选完文件 → 逐张上传 */
async function onFilesPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])

  // 清空，这样选同一张图也能再次触发 change
  input.value = ''

  const room = MAX_IMAGES_PER_MESSAGE - images.state.images.length
  for (const file of files.slice(0, room)) {
    await chatStore.addImage(file)
  }

  if (files.length > room) {
    images.state.error = `一条消息最多带 ${MAX_IMAGES_PER_MESSAGE} 张图片，多选的已忽略`
  }

  composer.value?.focus()
}

/** 拖拽进来的图片文件 */
async function onDrop(event: DragEvent) {
  const files = Array.from(event.dataTransfer?.files ?? []).filter((f) =>
    f.type.startsWith('image/'),
  )
  if (!files.length) return

  const room = MAX_IMAGES_PER_MESSAGE - images.state.images.length
  for (const file of files.slice(0, room)) {
    await chatStore.addImage(file)
  }
}

/** 离开角色会话，回到普通闲聊并回到角色选择页 */
function leaveRole() {
  roleplayStore.leaveRole()
  chatStore.setActiveRole(null)
  chatStore.newChat()
  void router.push({ name: 'chat-roles' })
}
</script>

<template>
  <div class="chat-view">
    <aside class="chat-sidebar">
      <SessionList />
    </aside>

    <main class="chat-main">
      <!-- 标题栏。
           「新对话」只放在左侧列表那个「新建」按钮上，这里不再重复放一个，
           否则同一屏里两个按钮做同一件事，用户不知道该点哪个。 -->
      <div class="chat-head">
        <div class="chat-head-left">
          <div class="chat-title">
            <span v-if="activeRole" class="title-emoji">{{ activeRole.emoji }}</span>
            {{ title }}
          </div>
          <div class="chat-sub">{{ subtitle }}</div>
        </div>

        <!-- 角色会话才有这几个入口 -->
        <div v-if="isRoleChat && state.activeRoleId" class="chat-head-actions">
          <button
            type="button"
            class="ghost-btn"
            @click="roleplayStore.openProfile(state.activeRoleId)"
          >
            档案
          </button>
          <button
            type="button"
            class="ghost-btn"
            @click="roleplayStore.openMemory(state.activeRoleId)"
          >
            记忆
          </button>
          <button type="button" class="ghost-btn" @click="leaveRole">换个角色</button>
        </div>
      </div>

      <!-- 角色档案 / 记忆面板 -->
      <RoleProfilePanel />
      <RoleMemoryPanel />

      <!-- 消息区 -->
      <div ref="feed" class="chat-feed">
        <!--
          正在加载这个会话的消息：显示骨架，而不是空白。
          直接留白会让人以为「点进去什么都没有」，骨架能说明「正在取」。
        -->
        <div v-if="state.messagesLoading" class="chat-inner">
          <div v-for="n in 3" :key="n" class="skeleton-row">
            <div class="skeleton-avatar" />
            <div class="skeleton-lines">
              <div class="skeleton-line" />
              <div class="skeleton-line skeleton-line--short" />
            </div>
          </div>
        </div>

        <div v-else-if="!chatStore.hasMessages.value" class="chat-empty">
          <EmptyState
            icon="💬"
            title="开始一段对话"
            description="随便聊点什么，发第一句话就会自动建一个会话"
          />
        </div>

        <div v-else class="chat-inner">
          <MessageBubble
            v-for="message in state.messages"
            :key="message.uid"
            :message="message"
            @open-image="lightboxImage = $event"
          />
        </div>
      </div>

      <!-- 输入区 -->
      <div @drop.prevent="onDrop" @dragover.prevent>
        <!-- 隐藏的文件选择框：点相机按钮时触发 -->
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
          placeholder="说点什么…（也可以直接拖图片进来）"
          :disabled="state.streaming"
          allow-image
          :allow-empty="images.state.images.length > 0"
          @send="send"
          @stop="stop"
          @pick-image="pickImage"
        >
          <template v-if="images.state.images.length || images.state.uploading" #pending>
            <PendingImages
              :images="images.state.images"
              :uploading="images.state.uploading"
              @remove="chatStore.removeImage($event)"
            />
          </template>
        </ChatComposer>

        <!-- 上传错误 -->
        <div v-if="images.state.error" class="upload-error">
          {{ images.state.error }}
          <button type="button" class="upload-error-close" @click="images.state.error = ''">
            ✕
          </button>
        </div>
      </div>
    </main>

    <!-- 点开大图 -->
    <ImageLightbox :image-id="lightboxImage" @close="lightboxImage = null" />
  </div>
</template>

<style scoped>
.chat-view {
  flex: 1;
  display: flex;
  min-height: 0;
}

/* ---------- 左侧 ---------- */
.chat-sidebar {
  width: var(--w-sidebar);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--c-bg-sidebar);
  border-right: 1px solid var(--c-line);
  min-height: 0;
}

/* ---------- 右侧 ---------- */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.chat-head {
  height: var(--h-head);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  padding: 0 var(--s-5);
  border-bottom: 1px solid var(--c-line);
  flex-shrink: 0;
}

.chat-head-left {
  min-width: 0;
}

.chat-head-actions {
  display: flex;
  gap: var(--s-2);
  flex-shrink: 0;
}

.title-emoji {
  margin-right: 4px;
}

.chat-title {
  font-size: var(--f-md);
  font-weight: 650;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 46vw;
}

.chat-sub {
  font-size: var(--f-sm);
  color: var(--c-text-3);
  margin-top: 1px;
}

.ghost-btn {
  padding: 6px 11px;
  border: 1px solid var(--c-line);
  border-radius: var(--r-sm);
  background: var(--c-bg);
  font-size: var(--f-sm);
  color: var(--c-text-2);
  transition: background var(--t-fast) var(--ease);
}

.ghost-btn:hover {
  background: var(--c-bg-soft);
}

/* ---------- 消息区 ---------- */
.chat-feed {
  flex: 1;
  overflow-y: auto;
  /* 上下留白加大：内容不要贴着标题栏和输入框 */
  padding: var(--s-8) 0 var(--s-4);
  min-height: 0;
}

.chat-inner {
  /*
   * 内容列居中。
   *
   * 试过「左侧贴边」：左边空 64px、右边空 719px，
   * 整块对话明显偏左，右侧一大片空白反而更难看。
   * 居中至少在两边对称，看起来是「内容被放在中间」，而不是「内容跑偏了」。
   *
   * 真正的解法不是挪位置，而是让内容本身变宽（--w-content 已从 740 提到 860）。
   */
  max-width: var(--w-content);
  margin: 0 auto;
  padding: 0 var(--s-6);
}

.chat-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
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

/* ---------- 消息骨架 ----------
   只做很轻的呼吸动画，不做「从左到右扫光」那种夸张效果。 */
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

/* ---------- 窄屏 ---------- */
@media (max-width: 768px) {
  .chat-sidebar {
    display: none;
  }

  .chat-head {
    padding: 0 var(--s-4);
  }

  .chat-title {
    max-width: 60vw;
  }
}
</style>



