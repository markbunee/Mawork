// 文章 API 封装

const BASE = '/api/articles'

export interface ArticleItem {
  title: string
}

export interface ArticleContent {
  title: string
  heading: string
  body: string
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

function enc(s: string) {
  return encodeURIComponent(s)
}

/** 列出某年全部文章标题 */
export function listArticles(year: string): Promise<{ year: string; articles: ArticleItem[] }> {
  return request(`${BASE}/${year}`)
}

/** 获取某篇 */
export function getArticle(year: string, title: string): Promise<ArticleContent> {
  return request(`${BASE}/${year}/${enc(title)}`)
}

/** 新建或更新某篇（标题已存在则改正文） */
export function upsertArticle(year: string, title: string, body: string) {
  return request(`${BASE}/${year}/${enc(title)}`, {
    method: 'PUT',
    body: JSON.stringify({ title, body }),
  })
}

/** 新建一篇（追加） */
export function createArticle(year: string, title: string, body: string) {
  return request(`${BASE}/${year}`, {
    method: 'POST',
    body: JSON.stringify({ title, body }),
  })
}

/** 删除一篇 */
export function deleteArticle(year: string, title: string) {
  return request(`${BASE}/${year}/${enc(title)}`, { method: 'DELETE' })
}
