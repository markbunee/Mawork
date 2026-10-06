// 全局搜索 API 封装（横切能力 E1）：跨模块一处检索。

import { request } from './http'

const BASE = '/api/search'

export interface SearchItem {
  id: string
  title: string
  subtitle: string
  snippet: string
  /** 前端路由，点击结果后跳转 */
  route: string
  /** 跳转时附带的 query（如 { date } / { year, title } / { path }） */
  query: Record<string, string>
}

export interface SearchGroup {
  module: string
  label: string
  items: SearchItem[]
}

export interface SearchResult {
  q: string
  total: number
  groups: SearchGroup[]
}

/** 跨日报 / 文章 / 记账 / 日程 / 计时 / 资料 检索 */
export function globalSearch(q: string, limit = 10): Promise<SearchResult> {
  return request(`${BASE}?q=${encodeURIComponent(q)}&limit=${limit}`)
}
