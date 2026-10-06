// 标签中台 API（横切能力 E6）

import { request } from './http'

export interface TagStat {
  tag: string
  count: number
  modules: Record<string, number>
}

export interface TagListResult {
  total: number
  occurrences: number
  tags: TagStat[]
}

export interface TagItem {
  tag: string
  module: string
  module_label: string
  title: string
  subtitle: string
  route: string
  query: Record<string, string>
}

export interface TagGroup {
  module: string
  module_label: string
  items: TagItem[]
}

export interface TagItemsResult {
  tag: string
  total: number
  groups: TagGroup[]
}

export function listAllTags(): Promise<TagListResult> {
  return request('/api/tag/list')
}

export function getTagItems(tag: string): Promise<TagItemsResult> {
  return request(`/api/tag/items?tag=${encodeURIComponent(tag)}`)
}
