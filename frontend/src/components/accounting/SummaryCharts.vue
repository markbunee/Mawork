<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import type { Summary, YearSeries } from '@/api/accounting'
import { loadEcharts, type ECharts } from '@/utils/echarts'

const props = defineProps<{
  summary: Summary | null
  yearSeries: YearSeries | null
}>()

const expenseEl = ref<HTMLDivElement>()
const incomeEl = ref<HTMLDivElement>()
const reimburseEl = ref<HTMLDivElement>()
const trendEl = ref<HTMLDivElement>()

let pieCharts: ECharts[] = []
let trendChart: ECharts | null = null
// 异步加载 echarts 期间组件可能已卸载，避免给已卸载节点 init
let disposed = false

// 高饱和配色（与日程模块一致）
const COLORS = ['#E0705A', '#67C23A', '#4A90D9', '#F5A623', '#9B59B6', '#E74C3C', '#2ECC71']

// 折线图各序列配色
const TREND_COLORS = {
  expense: '#E0705A',      // 支出 红
  income: '#67C23A',       // 收入 绿
  pending: '#4A90D9',      // 未报销费用 蓝
  net_income: '#F5A623',   // 净收入 橙
}

function makePieOption(title: string, data: { name: string; value: number }[]) {
  return {
    title: { text: title, left: 'center', textStyle: { fontSize: 14, color: '#2c2a26', fontFamily: 'serif' } },
    color: COLORS,
    tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
    series: [
      {
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['50%', '58%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: {
          label: { show: true, fontSize: 12, fontWeight: 'normal', formatter: '{b}\n{d}%' },
        },
        data,
      },
    ],
  }
}

async function renderPies() {
  if (!props.summary) return
  const b = props.summary.breakdown
  // 历史遗留分类（已不在当前分类表）加「历史」后缀，避免与现行分类混淆
  const toData = (arr: { category: string; amount: number; legacy?: boolean }[]) =>
    arr
      .filter((x) => x.amount > 0)
      .map((x) => ({ name: x.legacy ? `${x.category}（历史）` : x.category, value: x.amount }))

  const echarts = await loadEcharts()
  if (disposed) return

  if (expenseEl.value) {
    pieCharts[0] = echarts.init(expenseEl.value)
    pieCharts[0].setOption(makePieOption('支出占比', toData(b.expense)))
  }
  if (incomeEl.value) {
    pieCharts[1] = echarts.init(incomeEl.value)
    pieCharts[1].setOption(makePieOption('收入占比', toData(b.income)))
  }
  if (reimburseEl.value) {
    pieCharts[2] = echarts.init(reimburseEl.value)
    pieCharts[2].setOption(makePieOption('报销占比', toData(b.reimburse)))
  }
}

async function renderTrend() {
  if (!props.yearSeries || !trendEl.value) return

  const months = props.yearSeries.series.map((p) => `${p.month}月`)
  // 未收回垫付是「时点余额」，其余是「期间发生额」，量纲不同 → 必须分置双 Y 轴，
  // 否则余额线会被流量线压扁，读数失真。
  const lines = [
    { name: '支出', key: 'expense', color: TREND_COLORS.expense, axis: 'left' },
    { name: '收入', key: 'income', color: TREND_COLORS.income, axis: 'left' },
    { name: '净收入', key: 'net_income', color: TREND_COLORS.net_income, axis: 'left' },
    { name: '未收回垫付', key: 'unreimbursed', color: TREND_COLORS.pending, axis: 'right' },
  ]

  const echarts = await loadEcharts()
  if (disposed) return
  trendChart = echarts.init(trendEl.value)
  trendChart.setOption({
    title: {
      text: `${props.yearSeries.year} 年度收支走势`,
      left: 'center',
      textStyle: { fontSize: 14, color: '#2c2a26', fontFamily: 'serif' },
    },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: any) => `¥${v?.toFixed?.(2) ?? v}`,
    },
    legend: {
      bottom: 0,
      textStyle: { fontSize: 12, color: '#8a857a' },
      itemWidth: 14,
      itemHeight: 10,
    },
    grid: { top: 56, left: 56, right: 64, bottom: 56 },
    xAxis: {
      type: 'category',
      data: months,
      axisLine: { lineStyle: { color: '#ece7de' } },
      axisLabel: { color: '#8a857a' },
    },
    yAxis: [
      {
        type: 'value',
        name: '发生额',
        nameTextStyle: { color: '#8a857a', fontSize: 11 },
        axisLabel: { color: '#8a857a' },
        splitLine: { lineStyle: { color: '#f0ece3' } },
      },
      {
        type: 'value',
        name: '未收回余额',
        nameTextStyle: { color: TREND_COLORS.pending, fontSize: 11 },
        axisLabel: { color: TREND_COLORS.pending },
        splitLine: { show: false },
      },
    ],
    series: lines.map((l) => ({
      name: l.name,
      type: 'line',
      yAxisIndex: l.axis === 'right' ? 1 : 0,
      data: props.yearSeries!.series.map((p) => (p as any)[l.key]),
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 2.5, color: l.color },
      itemStyle: { color: l.color },
    })),
  })
}

function resize() {
  pieCharts.forEach((c) => c.resize())
  trendChart?.resize()
}

onMounted(() => {
  renderPies()
  renderTrend()
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  disposed = true
  window.removeEventListener('resize', resize)
  pieCharts.forEach((c) => c.dispose())
  pieCharts = []
  trendChart?.dispose()
  trendChart = null
})

watch(
  () => [props.summary, props.yearSeries] as const,
  () => {
    renderPies()
    renderTrend()
  },
)
</script>

<template>
  <div class="charts-wrap">
    <div class="charts-grid">
      <div ref="expenseEl" class="chart-box"></div>
      <div ref="incomeEl" class="chart-box"></div>
      <div ref="reimburseEl" class="chart-box"></div>
    </div>

    <!-- 年度折线图 -->
    <div v-if="yearSeries" ref="trendEl" class="chart-box chart-trend"></div>
  </div>
</template>
