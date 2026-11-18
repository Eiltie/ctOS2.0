/**
 * 附件（图片）的接口调用 —— 对话和出行共用。
 *
 * 为什么放在 shared：
 *   两个模块都要传图、取图，接口完全一样。
 *   放在任何一边，另一边就得跨模块引用（ESLint 会拦）。
 *
 * 后端的限制（modules/chat/attachments.py）：
 *   单张 8 MiB、一条消息最多 3 张、支持 JPEG / PNG / GIF / WebP
 */
import { http, request } from '@/shared/api/http'
import type { UploadedImage } from '@/shared/types/api'

/** 后端允许的图片类型 */
export const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']

/** 后端的大小上限：8 MiB */
export const MAX_IMAGE_BYTES = 8 * 1024 * 1024

/** 一条消息最多带几张 */
export const MAX_IMAGES_PER_MESSAGE = 3

/**
 * 取图片像素。
 *
 * 为什么不能用 <img src="/chat/attachment/1">：
 *   这个接口要求带 Authorization 头，而 <img> 没法加请求头。
 *   所以要先 fetch 成 Blob，再转成 objectURL 给 <img> 用。
 *   用完记得 revokeObjectURL，否则内存不回收。
 */
export function fetchImage(imageId: number, signal?: AbortSignal): Promise<Blob> {
  return http.blob(`/chat/attachment/${imageId}`, signal)
}

/**
 * 上传一张图片。
 *
 * 后端按文件真实内容判断格式（不信扩展名），
 * 所以用户把 PNG 改名成 .jpg 也能正常上传，不用前端纠正。
 *
 * 本地先校验一遍：类型不对或太大就当场拒绝，
 * 免得传完几 MB 才收到 400。
 */
export async function uploadImage(file: File): Promise<UploadedImage> {
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
    throw new Error('只支持 JPEG、PNG、GIF、WebP 格式的图片')
  }
  if (file.size > MAX_IMAGE_BYTES) {
    throw new Error(`图片太大了（上限 ${MAX_IMAGE_BYTES / 1024 / 1024} MB）`)
  }

  const form = new FormData()
  form.append('file', file)

  // multipart 不能手动设 Content-Type，浏览器会自己加 boundary
  return request<UploadedImage>('/chat/attachment', {
    method: 'POST',
    body: form,
  })
}
