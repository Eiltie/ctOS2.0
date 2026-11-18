<script setup lang="ts">
/**
 * AI 生成的图片。
 *
 * 和「用户上传的图」(AttachmentImage) 的区别：
 *   · 上传的图是用户自己发的，点开看看就行
 *   · 生成的图是 AI 给的成品，用户多半想存下来 —— 所以带一个下载按钮
 *
 * 取图和上传的图走同一条路（GET /chat/attachment/{id}，要鉴权），
 * 所以还是先 fetch 成 Blob 再转 objectURL。
 *
 * 下载也是拿同一个 Blob 存的 —— 再请求一次没必要，
 * 而且重复请求可能碰到浏览器缓存策略的差异。
 */
import { onBeforeUnmount, ref, watch } from 'vue'
import { fetchImage } from './api'

const props = defineProps<{
  imageId: number
}>()

const objectUrl = ref('')
const loading = ref(true)
const failed = ref(false)

/** 下载中的临时状态，避免连点 */
const saving = ref(false)

let currentUrl = ''

/** 释放上一次的 objectURL，避免内存泄漏 */
function release() {
  if (currentUrl) {
    URL.revokeObjectURL(currentUrl)
    currentUrl = ''
    objectUrl.value = ''
  }
}

async function load() {
  release()
  loading.value = true
  failed.value = false

  try {
    const blob = await fetchImage(props.imageId)
    currentUrl = URL.createObjectURL(blob)
    objectUrl.value = currentUrl
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

watch(() => props.imageId, load, { immediate: true })

onBeforeUnmount(release)

/** 下载：用已经拿到的 Blob，不再请求一次 */
async function download() {
  if (saving.value) return
  saving.value = true

  try {
    const blob = await fetchImage(props.imageId)

    // 从 blob 的 mime 推扩展名
    const ext = blob.type.includes('png')
      ? 'png'
      : blob.type.includes('webp')
        ? 'webp'
        : blob.type.includes('gif')
          ? 'gif'
          : 'jpg'

    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `ctOS-${props.imageId}.${ext}`
    document.body.appendChild(link)
    link.click()
    link.remove()

    // 给浏览器一点时间开始下载再释放
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch {
    failed.value = true
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="gen-image">
    <!-- 加载中 -->
    <div v-if="loading" class="gen-skeleton">
      <span class="gen-spinner" />
      <span class="gen-hint">加载图片…</span>
    </div>

    <!-- 失败 -->
    <div v-else-if="failed" class="gen-failed">
      <span>图片加载失败</span>
      <button type="button" class="gen-retry" @click="load">重试</button>
    </div>

    <!-- 正常 -->
    <template v-else>
      <img
        :src="objectUrl"
        class="gen-img"
        alt="生成的图片"
        loading="lazy"
        @click="download"
      />

      <div class="gen-bar">
        <span class="gen-tag">AI 生成</span>
        <button type="button" class="gen-download" :disabled="saving" @click="download">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M12 4v12" />
            <path d="m7 11 5 5 5-5" />
            <path d="M4 20h16" />
          </svg>
          {{ saving ? '保存中…' : '下载' }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.gen-image {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  max-width: 420px;
  margin-top: var(--s-3);
}

/* ---------- 图片 ---------- */
.gen-img {
  width: 100%;
  height: auto;
  border-radius: var(--r-lg);
  border: 1px solid var(--c-line);
  cursor: pointer;
  display: block;
  transition: border-color var(--t-fast) var(--ease-soft);
}

.gen-img:hover {
  border-color: var(--c-line-hover);
}

/* ---------- 底部条 ---------- */
.gen-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-2);
}

.gen-tag {
  font-size: var(--f-xs);
  color: var(--c-text-3);
}

.gen-download {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border-radius: var(--r-pill);
  border: 1px solid var(--c-line);
  background: var(--c-bg);
  font-size: var(--f-xs);
  color: var(--c-text-2);
  transition:
    border-color var(--t-fast) var(--ease-soft),
    background var(--t-fast) var(--ease-soft),
    color var(--t-fast) var(--ease-soft);
}

.gen-download:hover:not(:disabled) {
  border-color: var(--c-line-hover);
  background: var(--c-bg-soft);
  color: var(--c-text);
}

.gen-download:disabled {
  color: var(--c-text-3);
  cursor: default;
}

/* ---------- 骨架 ---------- */
.gen-skeleton,
.gen-failed {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 96px;
  padding: var(--s-4);
  border-radius: var(--r-lg);
  border: 1px dashed var(--c-line);
  background: var(--c-bg-soft);
  font-size: var(--f-sm);
  color: var(--c-text-3);
}

.gen-spinner {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--c-line-strong);
  border-top-color: var(--c-brand);
  animation: gen-spin 0.7s linear infinite;
}

@keyframes gen-spin {
  to {
    transform: rotate(360deg);
  }
}

.gen-retry {
  margin-left: auto;
  font-size: var(--f-xs);
  color: var(--c-brand-deep);
  text-decoration: underline;
}
</style>
