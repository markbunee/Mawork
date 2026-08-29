// 记账 API 封装

const BASE = '/api/accounting'

export type Kind = 'expense' | 'income' | 'reimburse'

export interface KindMeta {
  value: Kind
  label: string
  categories: string[]
}

export interface Meta {
  kinds: KindMeta[]
}

export interface Transaction {
  id: number
  kind: Kind
  category: string
  amount: number
  note: string
  date: string
  created_at: string
}

export interface TransactionIn {
  kind: Kind
  category: string
  amount: number
  note: string
  date: string
}

export interface CategoryAmount {
  category: string
  amount: number
}

export interface Summary {
  period: string
  totals: Record<Kind, number>
  net_expense: number
  breakdown: {
    expense: CategoryAmount[]
    income: CategoryAmount[]
    reimburse: CategoryAmount[]
  }
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

export function exportUrl(params?: { year?: string; month?: string }): string {
  const q = new URLSearchParams()
  if (params?.year) q.set('year', params.year)
  if (params?.month) q.set('month', params.month)
  const qs = q.toString()
  return `${BASE}/export${qs ? `?${qs}` : ''}`
}
