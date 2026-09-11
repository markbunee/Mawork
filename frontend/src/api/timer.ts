// 计时器 API 封装

const BASE = '/api/timer'

export type TimerType = 'countdown' | 'countup' | 'countdown_days' | 'countup_days'
export type TimerStatus = 'active' | 'paused' | 'finished'

export interface Timer {
  id: number
  type: TimerType
  title: string
  note: string
  target_at: string
  start_at: string
  status: TimerStatus
  running_since: string
  accumulated_sec: number
  created_at: string
  updated_at: string
}

export interface TimerIn {
  type: TimerType
  title: string
  note: string
  target_at: string
  start_at: string
  status: TimerStatus
}

export interface Bucket {
  key: string
  total_sec: number
  sessions: number
}

export interface TaskStat {
  title: string
  total_sec: number
  sessions: number
}

export interface Stats {
  granularity: string
  buckets: Bucket[]
  top_tasks: TaskStat[]
  total_sec: number
}

export interface Meta {
  types: TimerType[]
  type_labels: Record<TimerType, string>
  status_options: TimerStatus[]
  default_type: TimerType
  default_status: TimerStatus
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

export function getMeta(): Promise<Meta> {
  return request(`${BASE}/meta`)
}

export function listTimers(type?: string): Promise<Timer[]> {
  const q = type ? `?type=${encodeURIComponent(type)}` : ''
  return request(`${BASE}/timers${q}`)
}

export function createTimer(payload: TimerIn): Promise<Timer> {
  return request(`${BASE}/timers`, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateTimer(id: number, payload: TimerIn): Promise<Timer> {
  return request(`${BASE}/timers/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteTimer(id: number): Promise<{ ok: boolean }> {
  return request(`${BASE}/timers/${id}`, { method: 'DELETE' })
}

export function startTimer(id: number): Promise<Timer> {
  return request(`${BASE}/timers/${id}/start`, { method: 'POST' })
}

export function stopTimer(id: number): Promise<Timer> {
  return request(`${BASE}/timers/${id}/stop`, { method: 'POST' })
}

export function resetTimer(id: number): Promise<Timer> {
  return request(`${BASE}/timers/${id}/reset`, { method: 'POST' })
}

export function getStats(granularity: 'day' | 'week' | 'month'): Promise<Stats> {
  return request(`${BASE}/stats?granularity=${granularity}`)
}
