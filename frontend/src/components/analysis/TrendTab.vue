<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Dashboard } from '@/api/insight'
import { loadEcharts, type ECharts } from '@/utils/echarts'
import { eachDay } from '@/utils/dateRange'

const props = defineProps<{ data: Dashboard | null }>()

const finEl = ref<HTMLDivElement>()
const focusEl = ref<HTMLDivElement>()
const taskEl = ref<HTMLDivElement>()
const writeEl = ref<HTMLDivElement>()

let charts: ECharts[] = []
// 异步加载 echarts 期间组件可能已卸载，避免给已卸载节点 init
let disposed = false

const UP = '#3f6b45'
const DOWN = '#b4553f'
const ACCENT = '#7a4e2d'
const HABIT = '#c0392b'
const BLUE = '#4a90d9'

const axisStyle = {
  axisLine: { lineStyle: { color: '#ece7de' } },
  axisLabel: { color: '#8a857a', fontSize: 11 },
}

function baseGrid() {
  return { top: 42, left: 52, right: 20, bottom: 46 }
}

function days(): string[] {
  const d = props.data
  if (!d) return []
  return eachDay(d.range.from, d.range.to)
}

function shortLabel(date: string): string {
  const [y, m, dd] = date.split('-')
  return new Date().getFullYear().toString() === y ? `${Number(m)}/${Number(dd)}` : `${y.slice(2)}/${Number(m)}/${Number(dd)}`
}

function pick(src: Record<string, number>, day: string): number {
  return src[day] ?? 0
}

async function renderAll() {
  disposeAll()
  const d = props.data
  if (!d) return
  // 无数据时不加载 echarts，省掉 1MB+ 下载
  const echarts = await loadEcharts()
  if (disposed) return
  const labels = days().map(shortLabel)
  const rawDays = days()

  if (finEl.value) {
    const c = echarts.init(finEl.value)
    c.setOption({
      title: { text: '收支走势', left: 'center', textStyle: { fontSize: 14, color: '#2c2a26' } },
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, textStyle: { fontSize: 12, color: '#8a857a' }, itemWidth: 14, itemHeight: 10 },
      grid: baseGrid(),
      xAxis: { type: 'category', data: labels, ...axisStyle },
      yAxis: { type: 'value', axisLabel: axisStyle.axisLabel, splitLine: { lineStyle: { color: '#f0ece3' } } },
      series: [
        {
          name: '收入',
          type: 'bar',
          data: rawDays.map((x) => Math.max(0, pick(d.finance.by_day, x))),
          itemStyle: { color: UP, borderRadius: [3, 3, 0, 0] },
          barMaxWidth: 18,
        },
        {
          name: '支出',
          type: 'bar',
          data: rawDays.map((x) => Math.max(0, -pick(d.finance.by_day, x))),
          itemStyle: { color: DOWN, borderRadius: [3, 3, 0, 0] },
          barMaxWidth: 18,
        },
        {
          name: '净额',
          type: 'line',
          smooth: true,
          data: rawDays.map((x) => pick(d.finance.by_day, x)),
          lineStyle: { width: 2.2, color: ACCENT },
          itemStyle: { color: ACCENT },
          symbolSize: 5,
        },
      ],
    })
    charts.push(c)
  }

  if (focusEl.value) {
    const c = echarts.init(focusEl.value)
    c.setOption({
      title: { text: '专注时长（小时）', left: 'center', textStyle: { fontSize: 14, color: '#2c2a26' } },
      tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => `${Number(v).toFixed(1)} 小时` },
      grid: baseGrid(),
      xAxis: { type: 'category', data: labels, ...axisStyle },
      yAxis: { type: 'value', axisLabel: axisStyle.axisLabel, splitLine: { lineStyle: { color: '#f0ece3' } } },
      series: [
        {
          name: '专注',
          type: 'bar',
          data: rawDays.map((x) => Number((pick(d.focus.by_day, x) / 3600).toFixed(2))),
          itemStyle: { color: BLUE, borderRadius: [3, 3, 0, 0] },
          barMaxWidth: 22,
        },
      ],
    })
    charts.push(c)
  }

  if (taskEl.value) {
    const c = echarts.init(taskEl.value)
    c.setOption({
      title: { text: '任务完成与习惯达标', left: 'center', textStyle: { fontSize: 14, color: '#2c2a26' } },
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, textStyle: { fontSize: 12, color: '#8a857a' }, itemWidth: 14, itemHeight: 10 },
      grid: baseGrid(),
      xAxis: { type: 'category', data: labels, ...axisStyle },
      yAxis: { type: 'value', axisLabel: axisStyle.axisLabel, splitLine: { lineStyle: { color: '#f0ece3' } } },
      series: [
        {
          name: '完成任务数',
          type: 'bar',
          data: rawDays.map((x) => pick(d.tasks.by_day, x)),
          itemStyle: { color: ACCENT, borderRadius: [3, 3, 0, 0] },
          barMaxWidth: 18,
        },
        {
          name: '习惯达标率 %',
          type: 'line',
          smooth: true,
          data: rawDays.map((x) => {
            const v = d.habits.by_day[x]
            return v && v.total ? Math.round((v.done / v.total) * 100) : 0
          }),
          lineStyle: { width: 2.2, color: HABIT },
          itemStyle: { color: HABIT },
          symbolSize: 5,
        },
      ],
    })
    charts.push(c)
  }

  if (writeEl.value) {
    const c = echarts.init(writeEl.value)
    c.setOption({
      title: { text: '日报字数', left: 'center', textStyle: { fontSize: 14, color: '#2c2a26' } },
      tooltip: { trigger: 'axis' },
      grid: baseGrid(),
      xAxis: { type: 'category', data: labels, ...axisStyle },
      yAxis: { type: 'value', axisLabel: axisStyle.axisLabel, splitLine: { lineStyle: { color: '#f0ece3' } } },
      series: [
        {
          name: '字数',
          type: 'line',
          smooth: true,
          areaStyle: { color: 'rgba(122,78,45,0.14)' },
          data: rawDays.map((x) => pick(d.writing.by_day, x)),
          lineStyle: { width: 2.2, color: ACCENT },
          itemStyle: { color: ACCENT },
          symbolSize: 5,
        },
      ],
    })
    charts.push(c)
  }
}

function resize() {
  charts.forEach((c) => c.resize())
}

function disposeAll() {
  charts.forEach((c) => c.dispose())
  charts = []
}

onMounted(() => {
  renderAll()
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  disposed = true
  window.removeEventListener('resize', resize)
  disposeAll()
})

watch(() => props.data, renderAll)
</script>

<template>
  <div class="an-trend">
    <div v-if="!data" class="an-loading">请选择统计区间</div>
    <template v-else>
      <div ref="finEl" class="an-chart"></div>
      <div ref="focusEl" class="an-chart"></div>
      <div ref="taskEl" class="an-chart"></div>
      <div ref="writeEl" class="an-chart"></div>
    </template>
  </div>
</template>
