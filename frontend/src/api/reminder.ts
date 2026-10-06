import { request } from './http'

export interface ReminderItem {
  module: string
  module_label: string
  title: string
  detail: string
  route: string
  query: Record<string, string>
}

export interface ReminderGroup {
  module: string
  module_label: string
  items: ReminderItem[]
}

export interface ReminderResult {
  date: string
  total: number
  groups: ReminderGroup[]
}

export async function getReminders(): Promise<ReminderResult> {
  return request<ReminderResult>('/reminder/list')
}
