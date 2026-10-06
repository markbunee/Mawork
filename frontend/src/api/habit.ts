// 习惯培养 API 封装（数据在 planpool.db）

import { request } from './http'

const BASE = '/api/habit'

export type FreqType = 'daily' | 'weekdays' | 'custom'

export interface Habit {
  id: number
  name: string
  reason: string
  emoji: string
  freq_type: FreqType
  freq_days: string
  start_date: string
  archived: number
  created_at: string
}

export interface HabitStats {
  habit_id: number
  total_checkins: number
  expected_total: number
  done_expected: number
  completion_rate: number
  current_streak: number
  longest_streak: number
  last_checkin: string
  checked_today: boolean
}

export type BoardHabit = Habit & HabitStats

export interface BoardStats {
  today_checked: number
  today_total: number
  total_checkins: number
  longest_overall: number
  habits: BoardHabit[]
}

export interface HabitLog {
  id: number
  habit_id: number
  log_date: string
  note: string
  created_at: string
}

export interface HabitForDate {
  habit: Habit
  done: boolean
  expected: boolean
}

export interface CalendarHabitCell {
  total: number
  done: number
}

export interface HabitIn {
  name: string
  reason?: string
  emoji?: string
  freq_type?: FreqType
  freq_days?: string
  start_date?: string
}

export function listHabits(archived = false): Promise<{ habits: Habit[] }> {
  return request(`${BASE}/habits?archived=${archived ? 'true' : 'false'}`)
}

export function createHabit(p: HabitIn): Promise<Habit> {
  return request(`${BASE}/habits`, {
    method: 'POST',
    body: JSON.stringify(p),
  })
}

export function updateHabit(id: number, p: HabitIn): Promise<Habit> {
  return request(`${BASE}/habits/${id}`, {
    method: 'PUT',
    body: JSON.stringify(p),
  })
}

export function archiveHabit(id: number): Promise<{ ok: boolean }> {
  return request(`${BASE}/habits/${id}`, { method: 'DELETE' })
}

export function habitLogs(id: number): Promise<{ habit_id: number; dates: string[] }> {
  return request(`${BASE}/habits/${id}/logs`)
}

export function checkin(id: number, date?: string): Promise<{ log: HabitLog; stats: HabitStats }> {
  const q = date ? `?date=${encodeURIComponent(date)}` : ''
  return request(`${BASE}/habits/${id}/checkin${q}`, { method: 'POST' })
}

export function uncheck(id: number, date: string): Promise<{ ok: boolean }> {
  return request(`${BASE}/habits/${id}/checkin/${date}`, { method: 'DELETE' })
}

export function getStats(): Promise<BoardStats> {
  return request(`${BASE}/stats`)
}

export function getByDate(date: string): Promise<{ date: string; habits: HabitForDate[] }> {
  return request(`${BASE}/by_date?date=${encodeURIComponent(date)}`)
}

export function getCalendar(
  from: string,
  to: string,
): Promise<{ map: Record<string, CalendarHabitCell> }> {
  return request(`${BASE}/calendar?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`)
}
