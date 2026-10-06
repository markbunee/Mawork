// 日程（计划表）API 封装

import { request } from './http'

const BASE = '/api/planpool'

export type Progress = '未完成' | '进行中' | '已完成'

export const progressOptions: Progress[] = ['未完成', '进行中', '已完成']

export interface Task {
  id: number
  level1: string
  title: string
  progress: Progress
  completion: number
  note: string
  start_date: string
  end_date: string
  created_at: string
  updated_at: string
  /** 自定义列的值：col_key -> value */
  fields?: Record<string, string>
}

/** 列定义（灵活列模型） */
export type ColumnType = 'text' | 'date' | 'number' | 'select' | 'check'
export interface Column {
  id: number
  key: string
  label: string
  ftype: ColumnType
  options: string[]
  position: number
  pinned: boolean
  builtin: boolean
  visible: boolean
}

export interface Template {
  id: number
  name: string
  columns: { label: string; ftype: ColumnType; options: string[] }[]
}

export interface TaskIn {
  level1: string
  title: string
  progress: Progress
  completion: number
  note: string
  start_date: string
  end_date: string
}

export interface Stats {
  total: number
  done: number
  todo: number
  doing: number
}

export interface Meta {
  progress_options: Progress[]
  default_progress: Progress
  default_completion: number
}

export function getMeta(): Promise<Meta> {
  return request(`${BASE}/meta`)
}

export function listTasks(month?: string): Promise<Task[]> {
  const q = month ? `?month=${encodeURIComponent(month)}` : ''
  return request(`${BASE}/tasks${q}`)
}

export function createTask(payload: TaskIn): Promise<Task> {
  return request(`${BASE}/tasks`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTask(id: number, payload: TaskIn): Promise<Task> {
  return request(`${BASE}/tasks/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteTask(id: number): Promise<{ ok: boolean }> {
  return request(`${BASE}/tasks/${id}`, { method: 'DELETE' })
}

export function getStats(month?: string): Promise<Stats> {
  const q = month ? `?month=${encodeURIComponent(month)}` : ''
  return request(`${BASE}/stats${q}`)
}

export const exportUrl = `${BASE}/export`

// ---------------------------------------------------------------------------
// 灵活列
// ---------------------------------------------------------------------------
export function listColumns(): Promise<Column[]> {
  return request(`${BASE}/columns`)
}

export function addColumn(label: string, ftype: ColumnType, options: string[] = []): Promise<Column> {
  return request(`${BASE}/columns`, {
    method: 'POST',
    body: JSON.stringify({ label, ftype, options }),
  })
}

export function updateColumn(
  id: number,
  patch: Partial<Pick<Column, 'label' | 'ftype' | 'options' | 'visible' | 'pinned'>>,
): Promise<Column> {
  return request(`${BASE}/columns/${id}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  })
}

export function deleteColumn(id: number): Promise<{ ok: boolean }> {
  return request(`${BASE}/columns/${id}`, { method: 'DELETE' })
}

export function setColumnsOrder(ids: number[]): Promise<Column[]> {
  return request(`${BASE}/columns/order`, {
    method: 'PUT',
    body: JSON.stringify({ ids }),
  })
}

export function upsertCells(id: number, fields: Record<string, string | number | boolean>): Promise<{ ok: boolean }> {
  return request(`${BASE}/tasks/${id}/cells`, {
    method: 'PUT',
    body: JSON.stringify({ fields }),
  })
}

// ---------------------------------------------------------------------------
// 预设模板
// ---------------------------------------------------------------------------
export function listTemplates(): Promise<Template[]> {
  return request(`${BASE}/templates`)
}

export function applyTemplate(name: string): Promise<Column[]> {
  return request(`${BASE}/templates/apply`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

/** 按列定义 JSON 重建自定义列（统一模板库 E3 的「任务表」模板走此接口） */
export function applyColumnsJson(
  columns: { label: string; ftype: ColumnType; options: string[] }[],
): Promise<Column[]> {
  return request(`${BASE}/templates/apply_json`, {
    method: 'POST',
    body: JSON.stringify({ columns }),
  })
}
