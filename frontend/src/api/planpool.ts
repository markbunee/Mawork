// 日程任务 API 封装

const BASE = '/api/planpool'

export type Progress = '完成' | '未完成' | '进行中' | '搁置'

export interface Task {
  id: number
  level1: string
  level2: string
  progress: Progress
  display_progress: Progress
  note: string
  start_date: string
  end_date: string
  created_at: string
  updated_at: string
  checkins: string[]
  completion: number | null
}

export interface TaskIn {
  level1: string
  level2: string
  progress: Progress
  note: string
  start_date: string
  end_date: string
}

export interface Stats {
  total: number
  done: number
  todo: number
  doing: number
  on_hold: number
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

export function checkin(id: number, date: string): Promise<Task> {
  return request(`${BASE}/tasks/${id}/checkin?date=${encodeURIComponent(date)}`, {
    method: 'POST',
  })
}

export function uncheckin(id: number, date: string): Promise<Task> {
  return request(`${BASE}/tasks/${id}/checkin?date=${encodeURIComponent(date)}`, {
    method: 'DELETE',
  })
}

export const exportUrl = `${BASE}/export`
