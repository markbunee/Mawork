// 日历文本格 API：每一天是一块可直接输入的文本方格

import { request } from './http'

const BASE = '/api/calday'

export type CalLineKind = 'text' | 'task'

export interface CalLine {
  id: number
  date: string
  sort: number
  kind: CalLineKind
  text: string
  done: boolean
  /** 前端稳定键：服务端每次保存会重建 id，故用客户端生成的 cid 作为 :key，避免输入中重渲染丢焦点 */
  cid?: string
}

export interface CalDayResult {
  date: string
  lines: CalLine[]
  synced: number
}

/** 取出区间内每一天的文本行 */
export function listCalDays(from: string, to: string): Promise<{ days: Record<string, CalLine[]> }> {
  return request(`${BASE}?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`)
}

/** 整段覆盖某一天的文本行，并同步任务行到该日期的日报 */
export function saveCalDay(date: string, lines: { kind: CalLineKind; text: string; done: boolean }[]) {
  return request<CalDayResult>(`${BASE}/${date}`, {
    method: 'PUT',
    body: JSON.stringify({ lines }),
  })
}

// ---------------------------------------------------------------------------
// 月度计划（按月，日历上方）与周计划（按周一，日历左侧列）
// ---------------------------------------------------------------------------
export interface MonthNote {
  month: string
  content: string
}

export interface WeekNote {
  week_start: string
  content: string
}

/** 取某月（YYYY-MM）的月度计划 */
export function getMonthNote(month: string): Promise<MonthNote> {
  return request(`${BASE}/month_note?month=${encodeURIComponent(month)}`)
}

/** 保存月度计划 */
export function saveMonthNote(month: string, content: string): Promise<MonthNote> {
  return request(`${BASE}/month_note`, {
    method: 'PUT',
    body: JSON.stringify({ month, content }),
  })
}

/** 取区间内各周一的周计划：{ '2026-09-01': '...' } */
export function listWeekNotes(from: string, to: string): Promise<{ notes: Record<string, string> }> {
  return request(
    `${BASE}/week_notes?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
  )
}

/** 保存某一周的周计划，weekStart 为该周周一 */
export function saveWeekNote(weekStart: string, content: string): Promise<WeekNote> {
  return request(`${BASE}/week_note`, {
    method: 'PUT',
    body: JSON.stringify({ week_start: weekStart, content }),
  })
}
