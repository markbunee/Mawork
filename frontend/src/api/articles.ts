// 文章 API 封装（DB 存储：每篇一条记录，含 year/date/title/content）

import { request } from './http'

const BASE = '/api/articles'

export interface ArticleItem {
  id?: number
  year: string
  date: string
  title: string
  updated_at?: string
}

export interface ArticleContent {
  id: number
  year: string
  date: string
  title: string
  content: string
  created_at?: string
  updated_at?: string
}

export interface ArticlePayload {
  title: string
  content: string
  date: string
}

function enc(s: string) {
  return encodeURIComponent(s)
}

/** 列出某年全部文章 */
export function listArticles(
  year: string,
): Promise<{ year: string; articles: ArticleItem[] }> {
  return request(`${BASE}/${year}`)
}

/** 获取某篇 */
export function getArticle(year: string, title: string): Promise<ArticleContent> {
  return request(`${BASE}/${year}/${enc(title)}`)
}

/** 新建或更新某篇（payload.title 与路径不同则改名） */
export function upsertArticle(year: string, title: string, payload: ArticlePayload) {
  return request(`${BASE}/${year}/${enc(title)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

/** 新建一篇 */
export function createArticle(year: string, payload: ArticlePayload) {
  return request(`${BASE}/${year}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 删除一篇 */
export function deleteArticle(year: string, title: string) {
  return request(`${BASE}/${year}/${enc(title)}`, { method: 'DELETE' })
}
