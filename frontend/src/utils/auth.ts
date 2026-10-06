// 登录态本地存储：令牌与用户名。
// 说明：令牌存于 localStorage，实现简单；理论上可被 XSS 窃取，
// 个人本地部署可接受。若要更抗 XSS，可改为后端下发 HttpOnly Cookie。

const TOKEN_KEY = 'mawork_token'
const USER_KEY = 'mawork_username'
const UID_KEY = 'mawork_uid'
const ROLE_KEY = 'mawork_role'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function getUsername(): string {
  return localStorage.getItem(USER_KEY) || ''
}

export function setUsername(name: string): void {
  localStorage.setItem(USER_KEY, name)
}

/** 当前用户 id；取不到返回 0 */
export function getUid(): number {
  return Number(localStorage.getItem(UID_KEY) || 0)
}

export function setUid(uid: number): void {
  localStorage.setItem(UID_KEY, String(uid))
}

/** 角色：admin / member */
export function getRole(): string {
  return localStorage.getItem(ROLE_KEY) || ''
}

export function setRole(role: string): void {
  localStorage.setItem(ROLE_KEY, role)
}

/** 是否管理员（决定「用户管理」入口是否可见） */
export function isAdmin(): boolean {
  return getRole() === 'admin'
}

/** 保存一次登录结果 */
export function saveAuth(token: string, username: string, uid = 0, role = ''): void {
  setToken(token)
  setUsername(username)
  setUid(uid)
  setRole(role)
}

/** 清空登录态 */
export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(UID_KEY)
  localStorage.removeItem(ROLE_KEY)
}

/** 是否已登录（仅判断本地是否有令牌，有效性由后端校验） */
export function isLoggedIn(): boolean {
  return !!getToken()
}
