<script setup lang="ts">
/**
 * 待发图片的预览条。
 *
 * 显示在输入框上方：用户能看到「这条消息会带哪几张图」，
 * 每张都能单独删掉，上传中的显示占位。
 */
import type { UploadedImage } from '@/shared/types/api'
import AttachmentImage from './AttachmentImage.vue'

defineProps<{
  images: UploadedImage[]
  /** 还有几张在上传中 */
  uploading: number
}>()

const emit = defineEmits<{
  remove: [imageId: number]
}>()
</script>

<template>
  <div class="pending">
    <div v-for="img in images" :key="img.image_id" class="pending-item">
      <AttachmentImage :image-id="img.image_id" />

      <button
        type="button"
        class="pending-remove"
        title="移除这张图"
        @click="emit('remove', img.image_id)"
      >
        ✕
      </button>
    </div>

    <!-- 上传中的占位 -->
    <div v-for="n in uploading" :key="`uploading-${n}`" class="pending-item pending-item--loading">
      <div class="pending-spinner" />
    </div>
  </div>
</template>

<style scoped>
.pending {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}

.pending-item {
  position: relative;
  border-radius: var(--r-lg);
  /* overflow hidden 会把绝对的删除按钮裁掉，所以不设 hidden，
     交给子元素自己的圆角处理 */
  line-height: 0;
  /* 建立层叠上下文，保证删除按钮在上层 */
  isolation: isolate;
}

.pending-item :deep(.attachment),
.pending-item :deep(.attachment-img) {
  border-radius: var(--r-lg);
  overflow: hidden;
}

.pending-item--loading {
  width: 76px;
  height: 76px;
  display: grid;
  place-items: center;
  background: var(--c-bg-soft);
}

.pending-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--c-line-strong);
  border-top-color: var(--c-brand);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 删除按钮：悬停才明显，平时半透明 */
.pending-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  /* z-index 必须比图片高，否则被 <img> 盖住点不到 */
  z-index: 2;
  width: 20px;
  height: 20px;
  border-radius: var(--r-pill);
  background: rgba(16, 24, 40, 0.55);
  color: #fff;
  font-size: 11px;
  line-height: 1;
  display: grid;
  place-items: center;
  opacity: 0;
  transition: opacity var(--t-fast) var(--ease-soft);
}

.pending-item:hover .pending-remove {
  opacity: 1;
}

.pending-remove:hover {
  background: rgba(16, 24, 40, 0.8);
}

/* 小一点，别抢输入框的注意力 */
.pending-item :deep(.attachment-img) {
  max-width: 76px;
  max-height: 76px;
  width: auto;
  height: auto;
}

.pending-item :deep(.attachment-skeleton) {
  width: 76px;
  height: 76px;
}
</style>
