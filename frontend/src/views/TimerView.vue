<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getMeta,
  listTimers,
  getStats,
  type Meta,
  type Timer,
  type TimerType,
  type Stats,
} from '@/api/timer'
import TimerCard from '@/components/timer/TimerCard.vue'
import TimerForm from '@/components/timer/TimerForm.vue'
import TimerStats from '@/components/timer/TimerStats.vue'

const meta = ref<Meta | null>(null)
const timers = ref<Timer[]>([])
const stats = ref<Stats | null>(null)

// 实时刷新（1s tick）驱动卡片显示
const tick = ref(0)
let tickHandle: number | undefined

function startTick() {
  stopTick()
  tickHandle = window.setInterval(() => {
    tick.value += 1
  }, 1000)
}
function stopTick() {
  if (tickHandle !== undefined) {
    clearInterval(tickHandle)
    tickHandle = undefined
  }
}

const showForm = ref(false)
const editing = ref<Timer | null>(null)

const granularity = ref<'day' | 'week' | 'month'>('day')

const typeLabels = computed<Record<TimerType, string>>(
  () => (meta.value?.type_labels ?? {}) as Record<TimerType, string>,
)

async function loadMeta() {
  meta.value = await getMeta()
}
async function loadTimers() {
  timers.value = await listTimers()
}
async function loadStats() {
  stats.value = await getStats(granularity.value)
}
async function loadAll() {
  try {
    await Promise.all([loadMeta(), loadTimers(), loadStats()])
  } catch {
    ElMessage.error('加载失败')
  }
}

function openCreate() {
  editing.value = null
  showForm.value = true
}
function openEdit(t: Timer) {
  editing.value = t
  showForm.value = true
}
async function onSaved() {
  showForm.value = false
  await loadTimers()
}
async function onChanged() {
  await Promise.all([loadTimers(), loadStats()])
}
function changeGranularity(g: 'day' | 'week' | 'month') {
  granularity.value = g
  loadStats()
}

onMounted(() => {
  loadAll()
  startTick()
})
onUnmounted(stopTick)
</script>

<template>
  <div class="timer">
    <div class="tm-toolbar">
      <button class="tm-create-btn" @click="openCreate">+ 新建计时</button>
      <span class="tm-hint">倒计时 / 正计时 / 倒数日 / 正数日，可设计划与备注；正计时的开始-停止会进入时间消耗统计</span>
    </div>

    <div class="tm-cards">
      <TimerCard
        v-for="t in timers"
        :key="t.id"
        :timer="t"
        :type-label="typeLabels[t.type] || t.type"
        :tick="tick"
        @edit="openEdit"
        @changed="onChanged"
      />
      <div v-if="timers.length === 0" class="tm-empty">还没有计时器，点「新建计时」开始</div>
    </div>

    <div class="tm-stats">
      <div class="tm-stats-head">
        <span class="tm-stats-title">时间消耗统计</span>
        <div class="tm-gran">
          <button class="tm-gran-btn" :class="{ active: granularity === 'day' }" @click="changeGranularity('day')">日</button>
          <button class="tm-gran-btn" :class="{ active: granularity === 'week' }" @click="changeGranularity('week')">周</button>
          <button class="tm-gran-btn" :class="{ active: granularity === 'month' }" @click="changeGranularity('month')">月</button>
        </div>
      </div>
      <TimerStats :stats="stats" :granularity="granularity" />
    </div>

    <TimerForm v-model="showForm" :editing="editing" :meta="meta" @saved="onSaved" />
  </div>
</template>
