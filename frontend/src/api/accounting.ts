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
  /** 报销账目：已报销到账总额 / 剩余待报销 */
  reimbursed?: number
  remaining?: number
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
  /** 净收入 = 收入 - 支出（不含报销） */
  net_income: number
  net_expense: number
  pending: number
  settled: number
  /** 未报销费用 = 全部垫付 − 已报销到账（按当前月/年/全部口径） */
  unreimbursed: number
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
  deposit: number
  saving: number
  net_income: number
  /** 未收回垫付：垫付出去但尚未报销回来的钱（只影响余额，不影响净收入） */
  outstanding: number
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
