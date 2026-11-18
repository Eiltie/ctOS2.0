/**
 * 待发图片 —— 对话和出行共用。
 *
 * 为什么抽出来：
 *   两个模块的「选图 → 预览 → 删图 → 发出去」完全一样，
 *   只有最后的发送接口不同。放一份在这里，两边共用，
 *   以后改图片逻辑只改一处。
 *
 * 注意这是**每次会话一份**的状态，不是全局的：
 *   对话和出行各有各的待发图片，切模块不会串。
 *   用 createImageQueue() 各建一个实例。
 */
import { computed, reactive, type ComputedRef } from 'vue'
import type { UploadedImage } from '@/shared/types/api'
import { MAX_IMAGES_PER_MESSAGE, uploadImage } from '@/shared/attachments/api'

export interface ImageQueue {
  state: {
    images: UploadedImage[]
    uploading: number
    error: string
  }
  /** 已上传几张 */
  count: ComputedRef<number>
  /** 有没有待发图片 */
  hasAny: ComputedRef<boolean>
  /** 所有待发图片的 id */
  ids: ComputedRef<number[]>
  add: (file: File) => Promise<void>
  remove: (imageId: number) => void
  clear: () => void
  clearError: () => void
}

/** 新建一个待发图片队列 */
export function createImageQueue(): ImageQueue {
  const state = reactive({
    images: [] as UploadedImage[],
    uploading: 0,
    error: '',
  })

  /** 上传一张（类型/大小在 api.ts 里已经校验过） */
  async function add(file: File) {
    if (state.images.length >= MAX_IMAGES_PER_MESSAGE) {
      state.error = `一条消息最多带 ${MAX_IMAGES_PER_MESSAGE} 张图片`
      return
    }

    state.error = ''
    state.uploading += 1

    try {
      const uploaded = await uploadImage(file)
      state.images.push(uploaded)
    } catch (error) {
      state.error = error instanceof Error ? error.message : '图片上传失败'
    } finally {
      state.uploading -= 1
    }
  }

  function remove(imageId: number) {
    state.images = state.images.filter((img) => img.image_id !== imageId)
    state.error = ''
  }

  function clear() {
    state.images = []
    state.uploading = 0
    state.error = ''
  }

  function clearError() {
    state.error = ''
  }

  return {
    state,
    count: computed(() => state.images.length),
    hasAny: computed(() => state.images.length > 0),
    ids: computed(() => state.images.map((img) => img.image_id)),
    add,
    remove,
    clear,
    clearError,
  }
}

