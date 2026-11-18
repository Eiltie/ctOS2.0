<script setup lang="ts">
/**
 * 带鉴权的图片。
 *
 * 为什么不能直接用 <img src="/chat/attachment/1">：
 *   那个接口要求 Authorization 头，<img> 加不了头，会拿到 401。
 *   所以这里先 fetch 成 Blob，再转成 objectURL 交给 <img>。
 *
 * 内存：
 *   objectURL 不会自动回收，必须手动 revoke —— 消息一多不回收会吃满内存。
 *   组件卸载时、图片 id 变化时都要清。
 */
import { onBeforeUnmount, ref, watch } from 'vue'
import { fetchImage } from './api'

const props = defineProps<{
  imageId: number
  /** 点击图片时打开大图 */
  clickable?: boolean
}>()

const emit = defineEmits<{
  open: [imageId: number]
}>()

const url = ref('')
const loading = ref(true)
const failed = ref(false)

let currentUrl = ''

function revoke() {
  if (currentUrl) {
    URL.revokeObjectURL(currentUrl)
    currentUrl = ''
  }
}

async function load() {
  loading.value = true
  failed.value = false
  revoke()

  try {
    const blob = await fetchImage(props.imageId)
    currentUrl = URL.createObjectURL(blob)
    url.value = currentUrl
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

watch(() => props.imageId, load, { immediate: true })

onBeforeUnmount(revoke)

function onClick() {
  if (props.clickable && url.value) emit('open', props.imageId)
}
</script>

<template>
  <div class="attachment" :class="{ 'attachment--clickable': clickable }">
    <div v-if="loading" class="attachment-skeleton" />
    <div v-else-if="failed" class="attachment-failed">图片加载失败</div>
    <img
      v-else
      :src="url"
      class="attachment-img"
      alt="图片"
      @click="onClick"
    />
  </div>
</template>

<style scoped>
.attachment {
  display: inline-block;
  border-radius: var(--r-lg);
  overflow: hidden;
  background: var(--c-bg-soft);
  line-height: 0;
}

.attachment--clickable {
  cursor: zoom-in;
}

.attachment-img {
  display: block;
  max-width: 240px;
  max-height: 240px;
  width: auto;
  height: auto;
}

.attachment-skeleton {
  width: 120px;
  height: 90px;
  background: var(--c-bg-hover);
  animation: pulse 1.4s ease-in-out infinite;
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

.attachment-failed {
  width: 120px;
  height: 90px;
  display: grid;
  place-items: center;
  font-size: var(--f-xs);
  color: var(--c-text-3);
  line-height: 1.4;
  text-align: center;
}
</style>

