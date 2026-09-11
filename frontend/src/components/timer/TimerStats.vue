<script setup lang="ts">
import * as echarts from 'echarts'
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { Stats } from '@/api/timer'

const props = defineProps<{
  stats: Stats | null
  granularity: string
}>()

const chartEl = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

function fmtHm(sec: number): string {
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return h > 0 ? `${h}h${m}m` : `${m}m`
}

function render() {
  if (!chart || !props.stats) return
  const buckets = [...props.stats.buckets].reverse() // 时间升序
  const labels = buckets.map((b) => b.key)
  const values = buckets.map((b) => Number((b.total_sec / 3600).toFixed(2))) // 小时
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 52, right: 16, top: 16, bottom: 40 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { rotate: labels.length > 8 ? 45 : 0, color: '#7d766c' },
      axisLine: { lineStyle: { color: '#ded9d0' } },
    },
    yAxis: {
      type: 'value',
      name: '小时',
      nameTextStyle: { color: '#7d766c' },
      axisLabel: { color: '#7d766c' },
      splitLine: { lineStyle: { color: '#e4e0d8' } },
    },
    series: [
      {
        type: 'bar',
        data: values,
        itemStyle: { color: '#6f6047', borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 28,
      },
    ],
  })
}

function initChart() {
  if (chartEl.value && !chart) {
    chart = echarts.init(chartEl.value)
  }
  render()
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  nextTick(initChart)
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})

watch(
  () => [props.stats, props.granularity],
  () => nextTick(render),
  { deep: true },
)
</script>

<template>
  <div class="tm-stats-body" v-if="stats">
    <div class="tm-total">
      累计耗时 <b>{{ fmtHm(stats.total_sec) }}</b>（共
      {{ stats.top_tasks.reduce((a, b) => a + b.sessions, 0) }} 段）
    </div>

    <div ref="chartEl" class="tm-chart"></div>

    <div class="tm-task-table">
      <div class="tm-tt-head"><span>任务</span><span>耗时</span><span>段数</span></div>
      <div v-for="t in stats.top_tasks" :key="t.title" class="tm-tt-row">
        <span class="tm-tt-title">{{ t.title }}</span>
        <span>{{ fmtHm(t.total_sec) }}</span>
        <span>{{ t.sessions }}</span>
      </div>
      <div v-if="stats.top_tasks.length === 0" class="tm-tt-empty">
        暂无耗时记录（用「正计时」开始 / 停止即可生成）
      </div>
    </div>
  </div>
</template>
