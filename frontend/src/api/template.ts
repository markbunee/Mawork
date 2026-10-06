// 统一模板库 API（横切能力 E3）

import { request } from './http'

export interface TemplateItem {
  id: number
  scope: string
  name: string
  content: string
  builtin: number
  created_at: string
  updated_at: string
}

export function listTemplates(scope?: string): Promise<{ templates: TemplateItem[] }> {
  const q = scope ? `?scope=${encodeURIComponent(scope)}` : ''
  return request(`/api/template/list${q}`)
}

export function createTemplate(
  scope: string,
  name: string,
  content = '',
): Promise<TemplateItem> {
  return request('/api/template', {
    method: 'POST',
    body: JSON.stringify({ scope, name, content }),
  })
}

export function updateTemplate(
  id: number,
  name: string,
  content: string,
): Promise<TemplateItem> {
  return request(`/api/template/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ name, content }),
  })
}

export function deleteTemplate(id: number): Promise<{ ok: boolean }> {
  return request(`/api/template/${id}`, { method: 'DELETE' })
}
