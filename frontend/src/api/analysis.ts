// AI 报告分析相关 API 封装

import { request } from './http'

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

export function getTree(): Promise<{ tree: TreeItem[] }> {
  return request(`${BASE}/tree`)
}

export function readFile(path: string): Promise<AnalysisFile> {
  return request(`${BASE}/file?path=${encodeURIComponent(path)}`)
}

export function saveFile(path: string, content: string) {
  return request(`${BASE}/file?path=${encodeURIComponent(path)}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

export function createFolder(path: string) {
  return request(`${BASE}/folder`, {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
}

export function deleteItem(path: string) {
  return request(`${BASE}/item?path=${encodeURIComponent(path)}`, { method: 'DELETE' })
}
