// 表级数据导出 / 恢复 API
//
// 只提供 JSON 一对能力（各业务库的表数据），用于换机迁移与灾难恢复。
// 整目录 zip 打包上传/下载、以及自动快照回滚均已下线——
// 文件级增删改查与资料文件下载走「知识 · 文件」页（/api/resources/*）。

import { request } from './http'

export const backupExportUrl = '/api/backup/export'

export interface BackupPayload {
  version: number
  exported_at: string
  counts: Record<string, number>
  modules: Record<string, Record<string, unknown[]>>
  /** 导出失败的模块（若有）。缺模块不会被静默吞掉，靠它暴露。 */
  errors?: Record<string, string>
}

export interface BackupRestoreResult {
  ok: boolean
  restored: Record<string, Record<string, number | string>>
}

export function exportBackup(): Promise<BackupPayload> {
  return request(backupExportUrl)
}

export function importBackup(payload: BackupPayload): Promise<BackupRestoreResult> {
  return request('/api/backup/import', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
