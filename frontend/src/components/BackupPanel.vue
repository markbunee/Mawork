<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { download } from '@/api/http'
import { backupExportUrl, importBackup, type BackupPayload } from '@/api/backup'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const busy = ref(false)
const fileEl = ref<HTMLInputElement | null>(null)

function todayStr(): string {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

async function doExport() {
  busy.value = true
  try {
    await download(backupExportUrl, `mawork_backup_${todayStr()}.json`)
    ElMessage.success('备份已导出')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    busy.value = false
  }
}

async function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!window.confirm('恢复将覆盖备份中包含的表的数据，确认继续？')) {
    input.value = ''
    return
  }
  busy.value = true
  try {
    const payload = JSON.parse(await file.text()) as BackupPayload
    const res = await importBackup(payload)
    let total = 0
    for (const mod of Object.values(res.restored)) {
      for (const n of Object.values(mod)) {
        if (typeof n === 'number') total += n
      }
    }
    ElMessage.success(`已恢复 ${total} 条记录`)
  } catch {
    ElMessage.error('恢复失败：备份文件格式不正确')
  } finally {
    busy.value = false
    input.value = ''
  }
}

function onKey(e: KeyboardEvent) {
  // 嵌套的备份管理弹窗打开时，Esc 归它处理，避免两层一起关
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <transition name="gs-fade">
    <div v-if="open" class="gs-mask" @click.self="emit('close')">
      <div class="gs-panel">
        <div class="gs-bar">
          <span class="gs-title">数据备份</span>
          <button class="gs-close" aria-label="关闭" @click="emit('close')">✕</button>
        </div>

        <div class="gs-body">
          <p class="bk-desc">
            导出为 JSON 全量备份，覆盖记账 / 日程 / 日报 / 计时 / 目标 / 模板六个模块。
          </p>

          <div class="bk-actions">
            <button class="bk-btn primary" :disabled="busy" @click="doExport">导出备份</button>
            <button class="bk-btn" :disabled="busy" @click="fileEl?.click()">从文件恢复</button>
            <input
              ref="fileEl"
              type="file"
              accept="application/json,.json"
              class="bk-file"
              @change="onFile"
            />
          </div>

          <p class="bk-note">
            恢复为「覆盖」语义：备份中出现的表会先清空再写入，备份里没有的表保持原样。<br />
            资料文件（Markdown / PDF / 附件等）不在此备份内——那些请到<b>知识 · 文件</b>页
            按文件上传下载。
          </p>

        </div>
      </div>

      <!-- 嵌套的 workspaces 备份管理弹窗（z-index 更高，盖在本弹窗之上） -->
    </div>
  </transition>
</template>
