// AI 报告分析相关 API 封装

const BASE = '/api/analysis'

export interface TreeItem {
  name: string
  path: string
  type: 'dir' | 'file'
  children?: TreeItem[]
  size?: number
  mtime?: number
}

export interface AnalysisFile {
  path: string
  name: string
  content: string
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = `请求失败：${res.status}`
    try {
      const data = await res.json()
      if (data?.detail) detail = data.detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export function listYears(): Promise<{ years: string[] }> {
  return request(`${BASE}/years`)
}

export function getTree(year: string): Promise<{ year: string; tree: TreeItem[] }> {
  return request(`${BASE}/${year}/tree`)
}

export function readFile(year: string, path: string): Promise<AnalysisFile> {
  return request(`${BASE}/${year}/file?path=${encodeURIComponent(path)}`)
}

export function saveFile(year: string, path: string, content: string) {
  return request(`${BASE}/${year}/file?path=${encodeURIComponent(path)}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

export function createFolder(year: string, path: string) {
  return request(`${BASE}/${year}/folder`, {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
}

export function deleteItem(year: string, path: string) {
  return request(`${BASE}/${year}?path=${encodeURIComponent(path)}`, { method: 'DELETE' })
}
