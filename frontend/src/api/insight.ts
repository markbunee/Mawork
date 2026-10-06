// 洞察（复盘中心）API：跨模块统计 Dashboard、目标 KPI、自动复盘

import { request } from './http'

const BASE = '/api/insight'

// ---------------------------------------------------------------------------
// 通用类型
// ---------------------------------------------------------------------------
export type ReviewScope = 'week' | 'month' | 'quarter' | 'year'

export interface NameAmount {
  category: string
  amount: number
}

export interface DayVV {
  total: number
  done: number
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export interface DashboardRange {
  from: string
  to: string
  days: number
  label: string
}

export interface BudgetLite {
  period: string
  total: { category: string; limit: number; spent: number; remaining: number; over: boolean; pct: number }
  by_category: NameAmount[]
}

export interface FinanceBlock {
  income: number
  expense: number
  reimburse: number
  /** 未收回垫付（截至区间末的滚动余额：累计垫付 − 累计到账） */
  unreimbursed: number
  net: number
  top_expense: NameAmount[]
  top_income: NameAmount[]
  /** 'YYYY-MM-DD' -> 当日净额（收入 - 支出） */
  by_day: Record<string, number>
  budget: BudgetLite | null
  accounts_total: number
}

export interface FocusItem {
  title: string
  total_sec: number
  sessions: number
}

export interface FocusBlock {
  total_sec: number
  sessions: number
  by_day: Record<string, number>
  top_tasks: FocusItem[]
}

export interface TasksBlock {
  total: number
  done: number
  doing: number
  todo: number
  done_rate: number
  avg_completion: number
  /** 'YYYY-MM-DD' -> 当日完成数（按任务结束日期归集） */
  by_day: Record<string, number>
}

export interface HabitItem {
  id: number
  name: string
  emoji: string
  expected: number
  done: number
  rate: number
  streak: number
  longest: number
}

export interface HabitsBlock {
  expected: number
  done: number
  rate: number
  by_day: Record<string, DayVV>
  items: HabitItem[]
}

export interface TagCount {
  tag: string
  count: number
}

export interface WritingBlock {
  days: number
  elapsed: number
  coverage: number
  total_chars: number
  avg_chars: number
  streak: number
  complete_days: number
  complete_rate: number
  by_day: Record<string, number>
  tags: TagCount[]
}

export interface Goal {
  id: number
  title: string
  category: string
  metric: string
  start_value: number
  target: number
  current: number
  deadline: string
  note: string
  archived: number
  /** 以下为后端算出的进度字段 */
  remaining: number
  pct: number
  done: boolean
}

export interface Dashboard {
  range: DashboardRange
  finance: FinanceBlock
  focus: FocusBlock
  tasks: TasksBlock
  habits: HabitsBlock
  writing: WritingBlock
  goals: Goal[]
}

export function getDashboard(from: string, to: string): Promise<Dashboard> {
  return request(`${BASE}/dashboard?from=${from}&to=${to}`)
}

// ---------------------------------------------------------------------------
// 目标 KPI
// ---------------------------------------------------------------------------
export interface GoalIn {
  title?: string
  category?: string
  metric?: string
  start_value?: number
  target?: number
  current?: number
  deadline?: string
  note?: string
  archived?: boolean
}

export interface GoalLog {
  id: number
  goal_id: number
  log_date: string
  delta: number
  value: number
  note: string
}

export function listGoals(archived = false): Promise<{ goals: Goal[] }> {
  return request(`${BASE}/goals?archived=${archived ? 'true' : 'false'}`)
}

export function createGoal(payload: GoalIn): Promise<Goal> {
  return request(`${BASE}/goals`, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateGoal(id: number, payload: GoalIn): Promise<Goal> {
  return request(`${BASE}/goals/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteGoal(id: number): Promise<{ ok: boolean }> {
  return request(`${BASE}/goals/${id}`, { method: 'DELETE' })
}

// ---------------------------------------------------------------------------
// 关键结果 KR（横切能力 E7）
// ---------------------------------------------------------------------------
export interface KeyResult {
  id: number
  goal_id: number
  title: string
  metric: string
  start_value: number
  target: number
  current: number
  /** 权重，用于加权汇总为目标进度 */
  weight: number
  /** 周计划联动：YYYY-Www */
  week: string
  deadline: string
  note: string
  /** 后端算出的进度字段 */
  remaining: number
  pct: number
  done: boolean
  /** 仅 by_week 接口返回：所属目标名与分类 */
  goal_title?: string
  goal_category?: string
}

export interface KeyResultIn {
  title?: string
  metric?: string
  start_value?: number
  target?: number
  current?: number
  weight?: number
  week?: string
  deadline?: string
  note?: string
}

export interface GoalRollup {
  goal_id: number
  kr_count: number
  /** 无 KR 时为 null */
  pct: number | null
  krs: KeyResult[]
}

/** 某目标的关键结果 + 加权汇总进度 */
export function listKeyResults(goalId: number): Promise<GoalRollup> {
  return request(`${BASE}/goals/${goalId}/key_results`)
}

export function createKeyResult(goalId: number, payload: KeyResultIn): Promise<KeyResult> {
  return request(`${BASE}/goals/${goalId}/key_results`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateKeyResult(id: number, payload: KeyResultIn): Promise<KeyResult> {
  return request(`${BASE}/key_results/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteKeyResult(id: number): Promise<{ ok: boolean }> {
  return request(`${BASE}/key_results/${id}`, { method: 'DELETE' })
}

/** 周计划联动：某周挂载的关键结果 */
export function keyResultsByWeek(week = ''): Promise<{ week: string; items: KeyResult[] }> {
  const q = week ? `?week=${encodeURIComponent(week)}` : ''
  return request(`${BASE}/key_results/by_week${q}`)
}

export function checkinGoal(
  id: number,
  payload: { delta: number; note?: string; log_date?: string },
): Promise<Goal> {
  return request(`${BASE}/goals/${id}/checkin`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function listGoalLogs(id: number, limit = 200): Promise<{ goal_id: number; logs: GoalLog[] }> {
  return request(`${BASE}/goals/${id}/logs?limit=${limit}`)
}

// ---------------------------------------------------------------------------
// 自动复盘
// ---------------------------------------------------------------------------
export interface ReviewResult {
  scope: ReviewScope
  anchor: string
  from: string
  to: string
  title: string
  folder: string
  filename: string
  content: string
}

export function getReview(scope: ReviewScope, anchor: string): Promise<ReviewResult> {
  return request(`${BASE}/review?scope=${scope}&anchor=${anchor}`)
}

// ---------------------------------------------------------------------------
// 常用目标分类与单位（表单下拉，非强校验）
// ---------------------------------------------------------------------------
export const goalCategoryHints = ['存钱', '读书', '减重', '专注', '写作', '运动', '学习', '其他']

// ---------------------------------------------------------------------------
// 展示辅助
// ---------------------------------------------------------------------------
/** 秒 → 「3 小时 20 分」/「25 分」 */
export function fmtSec(sec: number): string {
  const m = Math.round((sec || 0) / 60)
  if (m < 60) return `${m} 分`
  const h = Math.floor(m / 60)
  const rest = m % 60
  return rest ? `${h} 小时 ${rest} 分` : `${h} 小时`
}

/** 金额：带正负与两位小数 */
export function fmtMoney(v: number): string {
  const n = Number(v || 0)
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}`
}
