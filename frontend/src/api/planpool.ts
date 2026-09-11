// 日程（计划表）API 封装

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
