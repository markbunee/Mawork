// 统计区间工具：复盘中心与首页概览共用

export type RangePreset = 'today' | 'week' | 'month' | 'quarter' | 'year'

export const presetLabels: Record<RangePreset, string> = {
  today: '今日',
  week: '本周',
  month: '本月',
  quarter: '本季',
  year: '本年',
}

export function iso(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function parseISO(s: string): Date {
  return new Date(`${s}T00:00:00`)
}

/** 周一为一周之首 */
export function startOfWeek(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const dow = x.getDay()
  return new Date(x.getFullYear(), x.getMonth(), x.getDate() - (dow === 0 ? 6 : dow - 1))
}

export interface ComputedRange {
  from: string
  to: string
  label: string
  days: number
}

export function computeRange(preset: RangePreset, anchor: Date): ComputedRange {
  let fromD: Date
  let toD: Date
  switch (preset) {
    case 'today':
      fromD = toD = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate())
      break
    case 'week':
      fromD = startOfWeek(anchor)
      toD = new Date(fromD.getFullYear(), fromD.getMonth(), fromD.getDate() + 6)
      break
    case 'month':
      fromD = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
      toD = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0)
      break
    case 'quarter': {
      const q = Math.floor(anchor.getMonth() / 3)
      fromD = new Date(anchor.getFullYear(), q * 3, 1)
      toD = new Date(anchor.getFullYear(), q * 3 + 3, 0)
      break
    }
    case 'year':
      fromD = new Date(anchor.getFullYear(), 0, 1)
      toD = new Date(anchor.getFullYear(), 11, 31)
      break
  }
  const from = iso(fromD)
  const to = iso(toD)
  const days = Math.round((parseISO(to).getTime() - parseISO(from).getTime()) / 86400000) + 1
  return {
    from,
    to,
    days,
    label: from === to ? from : `${from} ~ ${to}（${days} 天）`,
  }
}

/** 上一个等长区间（环比基准） */
export function previousRange(preset: RangePreset, anchor: Date): ComputedRange {
  return computeRange(preset, shiftAnchor(preset, anchor, -1))
}

/** 去年同期区间（同比基准） */
export function yearAgoRange(preset: RangePreset, anchor: Date): ComputedRange {
  const a = new Date(anchor.getFullYear() - 1, anchor.getMonth(), anchor.getDate())
  return computeRange(preset, a)
}

/** 按区间类型平移锚点：dir = -1 往前，1 往后 */
export function shiftAnchor(preset: RangePreset, anchor: Date, dir: number): Date {
  const y = anchor.getFullYear()
  const m = anchor.getMonth()
  const d = anchor.getDate()
  switch (preset) {
    case 'today':
      return new Date(y, m, d + dir)
    case 'week':
      return new Date(y, m, d + dir * 7)
    case 'month':
      return new Date(y, m + dir, 1)
    case 'quarter':
      return new Date(y, m + dir * 3, 1)
    case 'year':
      return new Date(y + dir, 0, 1)
  }
}

/** 区间内的每一天（YYYY-MM-DD） */
export function eachDay(from: string, to: string): string[] {
  const out: string[] = []
  const cur = parseISO(from)
  const end = parseISO(to)
  while (cur <= end) {
    out.push(iso(cur))
    cur.setDate(cur.getDate() + 1)
  }
  return out
}
