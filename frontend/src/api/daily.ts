// 日报相关 API 封装

const BASE = '/api/daily'

export interface DailyGroup {
  title: string
  dates: string[]
}

export interface DailyContent {
  date: string
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

/** 列出某年全部日期（按一级标题分组的树结构） */
export function listDaily(year: string): Promise<{ year: string; groups: DailyGroup[] }> {
  return request(`${BASE}/${year}`)
}

/** 列出含日报文件的年份 */
export function listYears(): Promise<{ years: string[] }> {
  return request(`${BASE}/years`)
}

/** 获取某天日报 */
export function getDaily(year: string, date: string): Promise<DailyContent> {
  return request(`${BASE}/${year}/${date}`)
}

/** 新建或更新某天日报 */
export function upsertDaily(year: string, date: string, body: string) {
  return request(`${BASE}/${year}/${date}`, {
    method: 'PUT',
    body: JSON.stringify({ body }),
  })
}
