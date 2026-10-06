// 资料浏览 API 封装

import { request } from './http'
import { getToken } from '@/utils/auth'

const BASE = '/api/resources'

export interface TreeNode {
  name: string
  path: string
  type: 'dir' | 'file'
  ext: string
  children: TreeNode[]
}

export interface MarkdownContent {
  type: 'markdown'
  name: string
  content: string
}

/** 获取 workspaces 完整目录树 */
export function fetchTree(): Promise<TreeNode> {
  return request(`${BASE}/tree`)
}

/** 读取 md/txt 内容 */
export function readMarkdown(path: string): Promise<MarkdownContent> {
  return request(`${BASE}/content?path=${encodeURIComponent(path)}`)
}

/**
 * 换取 PDF 预览的直连 URL（短时票据）。
 *
 * 为什么需要它：`<iframe src>` 没法带 Authorization 头。原来的做法是
 * fetch 带令牌 → 整份下载成 blob → createObjectURL，那会让浏览器 PDF 阅读器
 * 失去 HTTP Range 能力（必须等整份下完才渲染，且每次重下、内存常驻一份）。
 * 换成带票据的真实 URL 后，iframe 可以直接 Range 分页加载 + 命中浏览器缓存。
 */
export function fetchPdfUrl(path: string): Promise<{ url: string; expires_in: number }> {
  return request(`${BASE}/pdf-token?path=${encodeURIComponent(path)}`)
}

// ---------------------------------------------------------------------------
// 文件管理：下载 / 上传 / 删除 / 重命名 / 新建目录 / md 保存
// ---------------------------------------------------------------------------

/** 单文件下载 URL（走 Bearer 头，前端 fetchBlobUrl 取 blob 后触发保存） */
export function fileDownloadUrl(path: string): string {
  return `${BASE}/download?path=${encodeURIComponent(path)}`
}

/** 当前用户全部文件的 zip 打包下载 URL（GET，走 Bearer 头） */
export function userZipUrl(): string {
  return `${BASE}/zip`
}

/** 拖拽上传：一次可传多个文件到 dir（空串=根目录） */
export function uploadFiles(
  dir: string,
  files: File[],
): Promise<{
  ok: boolean
  uploaded: number
  overwritten: number
  total_size: string
  saved: { name: string; path: string; size: number; overwritten: boolean }[]
}> {
  const token = getToken()
  const form = new FormData()
  for (const f of files) form.append('files', f)
  const q = dir ? `?dir=${encodeURIComponent(dir)}` : ''
  return request(`${BASE}/upload${q}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
}

/** 删除文件或空目录 */
export function deleteItem(path: string): Promise<{ ok: boolean; deleted: string }> {
  return request(`${BASE}/item?path=${encodeURIComponent(path)}`, { method: 'DELETE' })
}

/** 重命名 / 移动 */
export function renameItem(
  path: string,
  newPath: string,
): Promise<{ ok: boolean; path: string }> {
  return request(`${BASE}/rename`, {
    method: 'POST',
    body: JSON.stringify({ path, new_path: newPath }),
  })
}

/** 新建目录 */
export function createFolder(path: string): Promise<{ ok: boolean; path: string }> {
  return request(`${BASE}/folder`, {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
}

/** 保存 md/txt 编辑内容 */
export function saveTextFile(
  path: string,
  content: string,
): Promise<{ ok: boolean; path: string; size: number; created: boolean }> {
  return request(`${BASE}/file`, {
    method: 'PUT',
    body: JSON.stringify({ path, content }),
  })
}

/** 上传前预检：哪些文件会被覆盖、哪些是新增 */
export function precheckUpload(
  dir: string,
  names: string[],
): Promise<{
  ok: boolean
  dir: string
  has_conflict: boolean
  conflicts: { name: string; size: number; is_dir: boolean; mtime: number }[]
  fresh: string[]
}> {
  const q = dir ? `?dir=${encodeURIComponent(dir)}` : ''
  return request(`${BASE}/upload/precheck${q}`, {
    method: 'POST',
    body: JSON.stringify({ names }),
  })
}
