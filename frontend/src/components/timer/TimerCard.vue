<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  startTimer,
  stopTimer,
  resetTimer,
  deleteTimer,
  type Timer,
} from '@/api/timer'

const props = defineProps<{
  timer: Timer
  typeLabel: string
  tick: number
}>()
const emit = defineEmits<{
  (e: 'edit', t: Timer): void
  (e: 'changed'): void
}>()

function fmtDuration(sec: number): string {
  const s = Math.max(0, Math.floor(sec))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

function parseLocal(s: string): Date | null {
  if (!s) return null
  let str = s.trim()
  // 仅日期：补零时刻并标本地时区
  if (/^\d{4}-\d{2}-\d{2}$/.test(str)) str = `${str}T00:00:00`
  else str = str.replace(' ', 'T')
  const d = new Date(str)
  return isNaN(d.getTime()) ? null : d
}

// 实时显示文案（依赖 props.tick 每秒重算）
const display = computed(() => {
  void props.tick // 触发依赖，使每秒重算
  const t = props.timer
  if (t.type === 'countup') {
    let sec = t.accumulated_sec
    if (t.running_since) {
      const rs = parseLocal(t.running_since)
      if (rs) sec += (Date.now() - rs.getTime()) / 1000
    }
    return {
      text: fmtDuration(sec),
      sub: t.running_since ? '进行中' : '已暂停',
      running: !!t.running_since,
    }
  }
  if (t.type === 'countdown') {
    const tg = parseLocal(t.target_at)
    if (!tg) return { text: '未设目标', sub: '', running: false }
    const diff = (tg.getTime() - Date.now()) / 1000
    if (diff >= 0) return { text: fmtDuration(diff), sub: '距目标', running: true }
    return { text: fmtDuration(-diff), sub: '已超时', running: false }
  }
  if (t.type === 'countdown_days') {
    const tg = parseLocal(t.target_at)
    if (!tg) return { text: '—', sub: '未设目标日', running: false }
    const days = Math.ceil((tg.getTime() - Date.now()) / 86400000)
    return { text: `${days >= 0 ? days : -days} 天`, sub: days >= 0 ? '还有' : '已过期', running: days >= 0 }
  }
  // countup_days
  const st = parseLocal(t.start_at)
  if (!st) return { text: '—', sub: '未设起始日', running: false }
  const days = Math.floor((Date.now() - st.getTime()) / 86400000)
  return { text: `${days} 天`, sub: '已过去', running: true }
})

const isCountup = computed(() => props.timer.type === 'countup')

async function doStart() {
  try {
    await startTimer(props.timer.id)
    emit('changed')
  } catch {
    ElMessage.error('操作失败')
  }
}
async function doStop() {
  try {
    await stopTimer(props.timer.id)
    emit('changed')
  } catch {
    ElMessage.error('操作失败')
  }
}
async function doReset() {
  try {
    await resetTimer(props.timer.id)
    emit('changed')
  } catch {
    ElMessage.error('操作失败')
  }
}
async function doDelete() {
  try {
    await deleteTimer(props.timer.id)
    emit('changed')
  } catch {
    ElMessage.error('操作失败')
  }
}
function doEdit() {
  emit('edit', props.timer)
}
</script>

<template>
  <div class="tm-card" :class="timer.type">
    <div class="tm-card-head">
      <span class="tm-type" :class="timer.type">{{ typeLabel }}</span>
      <span class="tm-title">{{ timer.title || '未命名' }}</span>
    </div>

    <div class="tm-display" :class="{ running: display.running }">
      <span class="tm-time">{{ display.text }}</span>
      <span class="tm-sub">{{ display.sub }}</span>
    </div>

    <div v-if="timer.note" class="tm-note">{{ timer.note }}</div>

    <div class="tm-actions">
      <template v-if="isCountup">
        <button v-if="!timer.running_since" class="tm-btn primary" @click="doStart">开始</button>
        <button v-else class="tm-btn warn" @click="doStop">停止</button>
        <button class="tm-btn" @click="doReset">重置</button>
      </template>
      <button class="tm-btn" @click="doEdit">编辑</button>
      <button class="tm-btn danger" @click="doDelete">删除</button>
    </div>
  </div>
</template>
