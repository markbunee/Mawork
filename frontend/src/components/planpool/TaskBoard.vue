<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { updateTask, type Column, type Progress, type Task } from '@/api/planpool'

const props = defineProps<{ tasks: Task[]; columns: Column[] }>()
const emit = defineEmits<{ (e: 'changed'): void }>()

const BUILTIN_KEYS = new Set(['level1', 'title', 'progress', 'completion', 'note', 'start_date', 'end_date'])

const lanes: { key: Progress; label: string }[] = [
  { key: '未完成', label: '未完成' },
  { key: '进行中', label: '进行中' },
  { key: '已完成', label: '已完成' },
]

const byLane = computed(() => {
  const m: Record<string, Task[]> = { 未完成: [], 进行中: [], 已完成: [] }
  for (const t of props.tasks) (m[t.progress] || (m[t.progress] = [])).push(t)
  return m
})

function customFields(t: Task): { label: string; value: string }[] {
  return props.columns
    .filter((c) => !c.builtin && c.visible)
    .map((c) => ({ label: c.label, value: t.fields?.[c.key] ?? '' }))
    .filter((f) => f.value && f.value !== '0' && f.value !== 'false')
}

function payloadOf(t: Task) {
  return {
    level1: t.level1,
    title: t.title,
    progress: t.progress,
    completion: t.completion,
    note: t.note,
    start_date: t.start_date,
    end_date: t.end_date,
  }
}

function move(t: Task, p: Progress) {
  if (t.progress === p) return
  updateTask(t.id, { ...payloadOf(t), progress: p })
    .then(() => emit('changed'))
    .catch(() => ElMessage.error('保存失败'))
}
</script>

<template>
  <div class="pp-board">
    <div v-for="lane in lanes" :key="lane.key" class="pp-lane">
      <div class="pp-lane-head">
        <span class="pp-lane-label">{{ lane.label }}</span>
        <span class="pp-lane-count">{{ byLane[lane.key].length }}</span>
      </div>
      <div class="pp-lane-body">
        <div v-for="t in byLane[lane.key]" :key="t.id" class="pp-card">
          <div class="pp-card-top">
            <span v-if="t.level1" class="pp-card-cat">{{ t.level1 }}</span>
            <select class="pp-card-move" :value="t.progress" @change="move(t, ($event.target as HTMLSelectElement).value as Progress)">
              <option v-for="l in lanes" :key="l.key" :value="l.key">{{ l.label }}</option>
            </select>
          </div>
          <div class="pp-card-title">{{ t.title || '未命名任务' }}</div>
          <div v-if="t.start_date || t.end_date" class="pp-card-date">
            {{ t.start_date || '…' }} ~ {{ t.end_date || '…' }}
          </div>
          <div class="pp-card-completion">
            <div class="pp-completion-bar"><div class="pp-completion-fill" :style="{ width: t.completion + '%' }"></div></div>
            <span class="pp-completion-text">{{ t.completion }}%</span>
          </div>
          <div v-if="customFields(t).length" class="pp-card-fields">
            <span v-for="f in customFields(t)" :key="f.label" class="pp-field-chip">{{ f.label }}: {{ f.value }}</span>
          </div>
        </div>
        <div v-if="byLane[lane.key].length === 0" class="pp-lane-empty">拖拽或下拉状态来归置</div>
      </div>
    </div>
  </div>
</template>
