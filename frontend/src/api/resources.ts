// 资料浏览 API 封装

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

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`请求失败：${res.status}`)
  }
  return res.json() as Promise<T>
}

/** 获取 workspaces 完整目录树 */
export function fetchTree(): Promise<TreeNode> {
  return request(`${BASE}/tree`)
}

/** 读取 md/txt 内容 */
export function readMarkdown(path: string): Promise<MarkdownContent> {
  return request(`${BASE}/content?path=${encodeURIComponent(path)}`)
}

/** 生成 pdf 预览 URL（相对后端，经 vite proxy） */
export function pdfUrl(path: string): string {
  return `${BASE}/content?path=${encodeURIComponent(path)}`
}
