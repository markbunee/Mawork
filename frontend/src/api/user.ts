// 用户管理 API（管理员专用）
import { request } from './http'

const BASE = '/api/user'

export interface UserItem {
  id: number
  username: string
  phone: string
  role: 'admin' | 'member'
  status: 'active' | 'disabled'
  display_name: string
  created_at: string
  updated_at: string
  last_login: string
}

export interface ApplicationItem {
  id: number
  /** new = 新成员申请；reset = 重置密码申请 */
  kind: 'new' | 'reset'
  username: string
  phone: string
  user_id: number | null
  status: 'pending' | 'approved' | 'rejected'
  note: string
  created_at: string
  handled_at: string
  handled_by: number | null
}

export const kindLabel: Record<string, string> = { new: '新成员', reset: '重置密码' }
export const statusLabel: Record<string, string> = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已驳回',
}

export function listUsers(): Promise<{ items: UserItem[] }> {
  return request(`${BASE}/list`)
}

export function createUser(payload: {
  username: string
  phone: string
  password: string
  role?: string
  display_name?: string
}): Promise<UserItem> {
  return request(`${BASE}`, { method: 'POST', body: JSON.stringify(payload) })
}

export function listApplications(status = 'pending'): Promise<{ items: ApplicationItem[] }> {
  return request(`${BASE}/applications?status=${encodeURIComponent(status)}`)
}

export function approveApplication(id: number): Promise<{ ok: boolean; kind: string; user_id: number; username: string }> {
  return request(`${BASE}/applications/${id}/approve`, { method: 'POST' })
}

export function rejectApplication(id: number, note = ''): Promise<{ ok: boolean; id: number }> {
  return request(`${BASE}/applications/${id}/reject`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  })
}

/** 重置密码：返回一次性临时密码明文，仅此一次可见 */
export function resetPassword(id: number): Promise<{ user: UserItem; temp_password: string; message: string }> {
  return request(`${BASE}/${id}/reset-password`, { method: 'POST' })
}

export function setUserStatus(id: number, status: 'active' | 'disabled'): Promise<UserItem> {
  return request(`${BASE}/${id}/status`, { method: 'POST', body: JSON.stringify({ status }) })
}

export function setUserRole(id: number, role: 'admin' | 'member'): Promise<UserItem> {
  return request(`${BASE}/${id}/role`, { method: 'POST', body: JSON.stringify({ role }) })
}

export function deleteUser(id: number): Promise<{ ok: boolean; user_id: number; data_removed: boolean }> {
  return request(`${BASE}/${id}`, { method: 'DELETE' })
}
