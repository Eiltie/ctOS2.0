<script setup lang="ts">
/**
 * 大图查看。
 *
 * 点击消息里的图片打开，点背景、按 Esc、点关闭都能关。
 */
import { onBeforeUnmount, watch } from 'vue'
import { fetchImage } from './api'
import { ref } from 'vue'

const props = defineProps<{
  imageId: number | null
}>()

const emit = defineEmits<{
  close: []
}>()

const url = ref('')
let currentUrl = ''

function revoke() {
  if (currentUrl) {
    URL.revokeObjectURL(currentUrl)
    currentUrl = ''
  }
}

async function load(id: number) {
  revoke()
  url.value = ''
  try {
    const blob = await fetchImage(id)
    currentUrl = URL.createObjectURL(blob)
    url.value = currentUrl
  } catch {
    url.value = ''
  }
}

watch(
  () => props.imageId,
  (id) => {
    if (id === null) {
      revoke()
      url.value = ''
      return
    }
    void load(id)
  },
)

/** Esc 关闭 */
function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

watch(
  () => props.imageId,
  (id) => {
    if (id !== null) {
      window.addEventListener('keydown', onKey)
    } else {
      window.removeEventListener('keydown', onKey)
    }
  },
)

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  revoke()
})
</script>

<template>
  <Transition name="lightbox">
    <div v-if="imageId !== null" class="lightbox" @click.self="emit('close')">
      <button type="button" class="lightbox-close" @click="emit('close')">✕</button>
      <img v-if="url" :src="url" class="lightbox-img" alt="图片" />
      <div v-else class="lightbox-loading">加载中…</div>
    </div>
  </Transition>
</template>

<style scoped>
.lightbox {
  position: fixed;
  inset: 0;
  z-index: var(--z-toast);
  background: rgba(16, 24, 40, 0.82);
  display: grid;
  place-items: center;
  padding: var(--s-8);
}

.lightbox-img {
  max-width: 100%;
  max-height: 100%;
  border-radius: var(--r-md);
  box-shadow: var(--sh-pop);
}

.lightbox-loading {
  color: rgba(255, 255, 255, 0.8);
  font-size: var(--f-base);
}

.lightbox-close {
  position: absolute;
  top: var(--s-5);
  right: var(--s-5);
  width: 34px;
  height: 34px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  font-size: 14px;
  display: grid;
  place-items: center;
  transition: background var(--t-fast) var(--ease-soft);
}

.lightbox-close:hover {
  background: rgba(255, 255, 255, 0.26);
}

.lightbox-enter-active,
.lightbox-leave-active {
  transition: opacity var(--t-normal) var(--ease-soft);
}

.lightbox-enter-from,
.lightbox-leave-to {
  opacity: 0;
}
</style>

