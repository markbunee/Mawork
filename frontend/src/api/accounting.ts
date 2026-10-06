// 记账 API 封装

import { request } from './http'

const BASE = '/api/accounting'

export type Kind = 'expense' | 'income' | 'reimburse'

export interface KindMeta {
  value: Kind
  label: string
  categories: string[]
  /** 一级分类 → 二级分类列表 */
  category2: Record<string, string[]>
}

export interface Meta {
  kinds: KindMeta[]
}

export interface Transaction {
  id: number
  kind: Kind
  category: string
  category2: string
  amount: number
  note: string
  date: string
  created_at: string
  /** 报销账目：已报销到账总额 / 剩余待报销 */
  reimbursed?: number
  remaining?: number
}

export interface TransactionIn {
  kind: Kind
  category: string
  category2: string
  amount: number
  note: string
  date: string
}

// ---------------------------------------------------------------------------
// 资产账户
// ---------------------------------------------------------------------------
export type AccountType = 'cash' | 'bank' | 'alipay' | 'wechat' | 'other'

export interface Account {
  id: number
  name: string
  type: AccountType
  balance: number
}

export function listAccounts(): Promise<Account[]> {
  return request(`${BASE}/accounts`)
}

export function createAccount(payload: { name: string; type: AccountType; balance: number }): Promise<Account> {
  return request(`${BASE}/accounts`, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateAccount(id: number, payload: { name: string; type: AccountType; balance: number }): Promise<Account> {
  return request(`${BASE}/accounts/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteAccount(id: number): Promise<{ ok: boolean }> {
  return request(`${BASE}/accounts/${id}`, { method: 'DELETE' })
}

// ---------------------------------------------------------------------------
// 预算
// ---------------------------------------------------------------------------
export interface Budget {
  id: number
  period: string
  scope: 'total' | 'category'
  category: string
  limit: number
}

export interface BudgetStatusItem {
  id?: number
  category: string
  limit: number
  spent: number
  remaining: number
  over: boolean
  pct: number
}

export interface BudgetTotalStatus extends BudgetStatusItem {
  /** spent 的构成：已花的支出部分 */
  expense: number
  /** spent 的构成：已垫付的报销部分（同样计入总预算） */
  reimburse: number
}

export interface BudgetStatus {
  period: string
  total: BudgetTotalStatus
  by_category: BudgetStatusItem[]
}

export function listBudgets(period: string): Promise<Budget[]> {
  return request(`${BASE}/budgets?period=${encodeURIComponent(period)}`)
}

export function createBudget(payload: { period: string; scope: string; category: string; limit: number }): Promise<Budget> {
  return request(`${BASE}/budgets`, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateBudget(id: number, limit: number): Promise<Budget> {
  return request(`${BASE}/budgets/${id}`, { method: 'PUT', body: JSON.stringify({ limit }) })
}

export function deleteBudget(id: number): Promise<{ ok: boolean }> {
  return request(`${BASE}/budgets/${id}`, { method: 'DELETE' })
}

export function getBudgetStatus(period: string): Promise<BudgetStatus> {
  return request(`${BASE}/budgets/status?period=${encodeURIComponent(period)}`)
}

// ---------------------------------------------------------------------------
// 周期账
// ---------------------------------------------------------------------------
export interface Recurring {
  id: number
  kind: Kind
  category: string
  category2: string
  amount: number | null
  note: string
  freq: 'monthly' | 'weekly'
  day_of_month: number
  account: string
  active: boolean
  last_applied: string
}

export function listRecurring(): Promise<Recurring[]> {
  return request(`${BASE}/recurring`)
}

export function createRecurring(payload: Partial<Recurring>): Promise<Recurring> {
  return request(`${BASE}/recurring`, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateRecurring(id: number, payload: Partial<Recurring>): Promise<Recurring> {
  return request(`${BASE}/recurring/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteRecurring(id: number): Promise<{ ok: boolean }> {
  return request(`${BASE}/recurring/${id}`, { method: 'DELETE' })
}

export function applyRecurring(period: string): Promise<{ created: number; skipped: number }> {
  return request(`${BASE}/recurring/apply?period=${encodeURIComponent(period)}`, { method: 'POST' })
}

export interface CategoryAmount {
  category: string
  amount: number
  /** true = 该分类已不在当前分类表中（历史遗留，如「住宿 / 发展 / 家庭」） */
  legacy?: boolean
}

export interface Summary {
  period: string
  totals: Record<Kind, number>
  /** 净收入 = 收入 - 支出（不含报销） */
  net_income: number
  net_expense: number
  pending: number
  settled: number
  /** 未收回垫付（滚动余额口径）：截至期末的累计垫付 − 累计到账，与资产卡/年度走势一致 */
  unreimbursed: number
  breakdown: {
    expense: CategoryAmount[]
    income: CategoryAmount[]
    reimburse: CategoryAmount[]
  }
}

export function getMeta(): Promise<Meta> {
  return request(`${BASE}/meta`)
}

export function listTransactions(params?: {
  kind?: Kind
  year?: string
  month?: string
}): Promise<Transaction[]> {
  const q = new URLSearchParams()
  if (params?.kind) q.set('kind', params.kind)
  if (params?.year) q.set('year', params.year)
  if (params?.month) q.set('month', params.month)
  const qs = q.toString()
  return request(`${BASE}/transactions${qs ? `?${qs}` : ''}`)
}

export function createTransaction(payload: TransactionIn): Promise<Transaction> {
  return request(`${BASE}/transactions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTransaction(id: number, payload: TransactionIn): Promise<Transaction> {
  return request(`${BASE}/transactions/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteTransaction(id: number): Promise<{ ok: boolean }> {
  return request(`${BASE}/transactions/${id}`, { method: 'DELETE' })
}

export function settleReimbursement(id: number): Promise<Transaction> {
  return request(`${BASE}/transactions/${id}/settle`, { method: 'POST' })
}

// ---------------------------------------------------------------------------
// 报销事件（事件化：每笔到账一条记录）
// ---------------------------------------------------------------------------
export interface ReimburseEvent {
  id: number
  tx_id: number
  amount: number
  event_date: string
  note: string
  created_at: string
}

export interface ReimburseEventIn {
  amount: number
  event_date: string
  note: string
}

export function listReimburseEvents(txId: number): Promise<ReimburseEvent[]> {
  return request(`${BASE}/transactions/${txId}/reimburse-events`)
}

export function createReimburseEvent(
  txId: number,
  payload: ReimburseEventIn,
): Promise<ReimburseEvent> {
  return request(`${BASE}/transactions/${txId}/reimburse-events`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function deleteReimburseEvent(eid: number): Promise<{ ok: boolean }> {
  return request(`${BASE}/reimburse-events/${eid}`, { method: 'DELETE' })
}

export function getSummary(params?: { year?: string; month?: string }): Promise<Summary> {
  const q = new URLSearchParams()
  if (params?.year) q.set('year', params.year)
  if (params?.month) q.set('month', params.month)
  const qs = q.toString()
  return request(`${BASE}/summary${qs ? `?${qs}` : ''}`)
}

export interface MonthPoint {
  month: number
  expense: number
  income: number
  pending: number
  settled: number
  /** 未收回垫付（月末滚动余额：累计待报销 − 累计已报销到账） */
  unreimbursed: number
  net_expense: number
  net_income: number
}

export interface YearSeries {
  year: string
  series: MonthPoint[]
}

export function getYearSeries(year: string): Promise<YearSeries> {
  return request(`${BASE}/series?year=${encodeURIComponent(year)}`)
}

export interface DailyNet {
  year: string
  month: string | null
  daily: Record<string, number> // 'YYYY-MM-DD' -> 净收入
}

export function getDailyNet(year: string, month?: string): Promise<DailyNet> {
  const q = month ? `?year=${year}&month=${month}` : `?year=${year}`
  return request(`${BASE}/daily${q}`)
}

export interface Balance {
  /** 多账户明细 */
  accounts: Account[]
  /** 账户余额合计（元） */
  accounts_total: number
  /** 累计净收入（元）= 全部收入 − 全部支出（不含报销） */
  net_income: number
  /** 未收回垫付（元）= 全部待报销 − 全部已报销到账 */
  outstanding: number
  /** 净资产（元）= 账户合计 + 累计净收入 − 未收回垫付 */
  balance: number
}

export function getSettings(): Promise<Balance> {
  return request(`${BASE}/settings`)
}

export function saveSettings(deposit: number, saving: number): Promise<Balance> {
  return request(`${BASE}/settings`, {
    method: 'PUT',
    body: JSON.stringify({ deposit, saving }),
  })
}

export function exportUrl(params?: { year?: string; month?: string }): string {
  const q = new URLSearchParams()
  if (params?.year) q.set('year', params.year)
  if (params?.month) q.set('month', params.month)
  const qs = q.toString()
  return `${BASE}/export${qs ? `?${qs}` : ''}`
}
