// 认证 API 封装
import { request } from './http'
import { clearAuth, saveAuth } from '@/utils/auth'

const BASE = '/api/auth'

export interface LoginResult {
  access_token: string
  token_type: string
  uid: number
  username: string
  role: string
}

/** 登录：成功后保存令牌与用户信息到本地 */
export async function login(username: string, password: string): Promise<LoginResult> {
  const res = await request<LoginResult>(`${BASE}/login`, {
    method: 'POST',
    body: JSON.stringify({ username, password }),
    noAuthRedirect: true,
  })
  saveAuth(res.access_token, res.username, res.uid, res.role)
  return res
}

/** 校验当前令牌，返回用户信息（uid / username / role） */
export function getMe(): Promise<{ id: number; username: string; role: string }> {
  return request(`${BASE}/me`)
}

/**
 * 成员申请 / 重置密码申请。
 * 同用户名 + 同手机号再次提交 = 重置密码申请，均需管理员通过后生效。
 */
export function applyMember(payload: {
  username: string
  phone: string
  password: string
  note?: string
}): Promise<{ id: number; kind: 'new' | 'reset'; username: string; status: string; message: string }> {
  return request(`${BASE}/apply`, {
    method: 'POST',
    body: JSON.stringify(payload),
    withAuth: false,
    noAuthRedirect: true,
  })
}

/** 退出登录：清空本地登录态 */
export function logout(): void {
  clearAuth()
}
