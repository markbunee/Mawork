// 统一 HTTP 封装：自动附加 Bearer 令牌、统一错误处理、401 自动跳登录页。
// 所有业务 API 文件共用此处的 request，避免逐个手写请求头。

import { clearAuth, getToken } from '@/utils/auth'

export interface RequestOptions extends RequestInit {
  /** 401 时是否自动清空登录态并跳转登录页（登录接口应设为 false） */
  noAuthRedirect?: boolean
  /** 是否附加 Authorization 头（默认 true） */
  withAuth?: boolean
}

/** 登录态失效：清空本地并跳转登录页 */
function handleUnauthorized(): void {
  clearAuth()
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

/** 解析错误响应体，尽量取后端返回的 detail 文案 */
async function parseError(res: Response): Promise<string> {
  const text = await res.text()
  if (!text) return `请求失败：${res.status}`
  try {
    const data = JSON.parse(text)
    if (typeof data?.detail === 'string') return data.detail
    if (Array.isArray(data?.detail) && data.detail[0]?.msg) return String(data.detail[0].msg)
  } catch {
    /* 非 JSON，直接用原文 */
  }
  return text
}

function buildHeaders(options: RequestOptions): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string> | undefined) ?? {}),
  }
  if (options.withAuth !== false) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

/** 发起 JSON 请求并返回解析后的数据 */
export async function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const { noAuthRedirect, withAuth, headers, ...rest } = options
  const res = await fetch(url, { ...rest, headers: buildHeaders({ noAuthRedirect, withAuth, headers }) })

  if (res.status === 401) {
    if (!noAuthRedirect) handleUnauthorized()
    throw new Error(await parseError(res))
  }
  if (!res.ok) {
    throw new Error(await parseError(res))
  }

  const text = await res.text()
  return (text ? JSON.parse(text) : null) as T
}

/** 从 Content-Disposition 解析文件名 */
function parseFilename(disposition: string | null): string {
  if (!disposition) return ''
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition)
  return m ? decodeURIComponent(m[1]) : ''
}

/** 带令牌下载二进制文件（xlsx / md 等），自动触发浏览器保存 */
export async function download(url: string, fallbackName = 'download'): Promise<void> {
  const token = getToken()
  const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (res.status === 401) {
    handleUnauthorized()
    throw new Error('登录已过期，请重新登录')
  }
  if (!res.ok) {
    throw new Error(await parseError(res))
  }
  const blob = await res.blob()
  const name = parseFilename(res.headers.get('Content-Disposition')) || fallbackName
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

/** 带令牌获取二进制内容并返回可嵌入的对象 URL（用于 PDF 预览等） */
export async function fetchBlobUrl(url: string): Promise<string> {
  const token = getToken()
  const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (res.status === 401) {
    handleUnauthorized()
    throw new Error('登录已过期，请重新登录')
  }
  if (!res.ok) {
    throw new Error(await parseError(res))
  }
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}
