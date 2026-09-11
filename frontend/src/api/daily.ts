// 日报相关 API 封装（日报库：daily.db，正文为整篇 Markdown）

const BASE = '/api/daily'

export interface DailyGroup {
  title: string
  dates: string[]
}

export interface CalTask {
  id: number
  text: string
  done: boolean
  source: string
}

export interface DailyContent {
  date: string
  year: string
  exists: boolean
  heading: string
  body: string
  calTasks: CalTask[]
}

export interface DailySaveResult {
  date: string
  ok: boolean
  plan_synced: number
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `请求失败：${res.status}`)
  }
  return res.json() as Promise<T>
}

/** 列出某年日报日期（按月份分组的树结构） */
export function listDaily(year: string): Promise<{ year: string; groups: DailyGroup[] }> {
  return request(`${BASE}/${year}`)
}

/** 列出已有日报的年份 */
export function listYears(): Promise<{ years: string[] }> {
  return request(`${BASE}/years`)
}

/** 获取某天日报（含当日日历任务行，用于页面顶部展示） */
export function getDaily(year: string, date: string): Promise<DailyContent> {
  return request(`${BASE}/${year}/${date}`)
}

/** 新建或更新某天日报；保存时「三、明日工作计划」自动写入次日日历 */
export function upsertDaily(year: string, date: string, body: string): Promise<DailySaveResult> {
  return request(`${BASE}/${year}/${date}`, {
    method: 'PUT',
    body: JSON.stringify({ body }),
  })
}

/** 导出某年全部日报为 Markdown 文件（含日历任务注入） */
export function exportDailyUrl(year: string): string {
  return `${BASE}/export?year=${encodeURIComponent(year)}`
}
