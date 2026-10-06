<script setup lang="ts">
import { computed } from 'vue'
import type { Task } from '@/api/planpool'

const props = defineProps<{ tasks: Task[]; year: number; month: number }>()
const emit = defineEmits<{ (e: 'goto', taskId: number): void }>()

const WEEK = ['一', '二', '三', '四', '五', '六', '日']

const cells = computed(() => {
  const first = new Date(props.year, props.month - 1, 1)
  const startDow = (first.getDay() + 6) % 7 // 周一=0
  const daysInMonth = new Date(props.year, props.month, 0).getDate()
  const out: { day: number; tasks: Task[]; inMonth: boolean }[] = []
  // 前置上个月的空格
  for (let i = 0; i < startDow; i++) out.push({ day: 0, tasks: [], inMonth: false })
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = `${props.year}-${String(props.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const ts = props.tasks.filter((t) => {
      const s = t.start_date || ''
      const e = t.end_date || ''
      if (!s && !e) return false
      if (s && e) return s <= ds && ds <= e
      if (s) return s === ds
      return e === ds
    })
    out.push({ day: d, tasks: ts, inMonth: true })
  }
  while (out.length % 7 !== 0) out.push({ day: 0, tasks: [], inMonth: false })
  return out
})

function progressClass(t: Task): string {
  return { 未完成: 'pp-dot-todo', 进行中: 'pp-dot-doing', 已完成: 'pp-dot-done' }[t.progress] || 'pp-dot-todo'
}
</script>

<template>
  <div class="pp-cal">
    <div class="pp-cal-week">
      <div v-for="w in WEEK" :key="w" class="pp-cal-weekcell">{{ w }}</div>
    </div>
    <div class="pp-cal-grid">
      <div
        v-for="(c, i) in cells"
        :key="i"
        class="pp-cal-cell"
        :class="{ 'pp-cal-out': !c.inMonth, 'pp-cal-has': c.tasks.length }"
      >
        <div v-if="c.day" class="pp-cal-day">{{ c.day }}</div>
        <div v-for="t in c.tasks.slice(0, 3)" :key="t.id" class="pp-cal-chip" @click="emit('goto', t.id)">
          <span class="pp-cal-dot" :class="progressClass(t)"></span>{{ t.title || '任务' }}
        </div>
        <div v-if="c.tasks.length > 3" class="pp-cal-more">+{{ c.tasks.length - 3 }}</div>
      </div>
    </div>
  </div>
</template>
