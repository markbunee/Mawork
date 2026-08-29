<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listTransactions,
  getSummary,
  getYearSeries,
  exportUrl,
  type Kind,
  type Transaction,
  type Summary,
  type YearSeries,
} from '@/api/accounting'
import TransactionForm from '@/components/accounting/TransactionForm.vue'
import TransactionList from '@/components/accounting/TransactionList.vue'
import SummaryCharts from '@/components/accounting/SummaryCharts.vue'

// 视图模式：month / year
type ViewMode = 'month' | 'year'

const now = new Date()
const curYear = ref(now.getFullYear())
const curMonth = ref(now.getMonth() + 1) // 1-12
const mode = ref<ViewMode>('month')

// 生成最近 10 年与 12 月选项
const yearOptions = Array.from({ length: 10 }, (_, i) => now.getFullYear() - 5 + i)
const monthOptions = Array.from({ length: 12 }, (_, i) => i + 1)

const period = computed(() =>
  mode.value === 'month'
    ? `${curYear.value}-${String(curMonth.value).padStart(2, '0')}`
    : `${curYear.value}`,
)

const query = computed(() =>
  mode.value === 'month'
    ? { month: period.value }
    : { year: period.value },
)

const transactions = ref<Transaction[]>([])
const summary = ref<Summary | null>(null)
const yearSeries = ref<YearSeries | null>(null)
const activeKind = ref<Kind | ''>('')
const loading = ref(false)

const kindLabelMap: Record<string, string> = {
  expense: '支出',
  income: '收入',
  reimburse: '报销',
}

function kindLabel(k: string) {
  return kindLabelMap[k] ?? k
}

const filteredList = computed(() =>
  activeKind.value ? transactions.value.filter((t) => t.kind === activeKind.value) : transactions.value,
)

async function load() {
  loading.value = true
  try {
    const q = query.value
    const yearStr = mode.value === 'year' ? q.year! : String(curYear.value)
    const [list, sum, series] = await Promise.all([
      listTransactions(q),
      getSummary(q),
      mode.value === 'year' ? getYearSeries(yearStr) : Promise.resolve(null),
    ])
    transactions.value = list
    summary.value = sum
    yearSeries.value = series
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function onSaved() {
  load()
}

function prev() {
  if (mode.value === 'month') {
    if (curMonth.value === 1) {
      curMonth.value = 12
      curYear.value--
    } else {
      curMonth.value--
    }
  } else {
    curYear.value--
  }
  load()
}

function next() {
  if (mode.value === 'month') {
    if (curMonth.value === 12) {
      curMonth.value = 1
      curYear.value++
    } else {
      curMonth.value++
    }
  } else {
    curYear.value++
  }
  load()
}

function doExport() {
  window.open(exportUrl(query.value), '_blank')
}

onMounted(load)
</script>

<template>
  <div class="accounting">
    <!-- 顶部：视图切换 + 账单浏览 -->
    <div class="acct-toolbar">
      <div class="view-switch">
        <button class="switch-btn" :class="{ active: mode === 'month' }" @click="mode = 'month'; load()">月账单</button>
        <button class="switch-btn" :class="{ active: mode === 'year' }" @click="mode = 'year'; load()">年账单</button>
      </div>

      <div class="period-nav">
        <button class="nav-arrow" @click="prev">‹</button>
        <select v-if="mode === 'month'" v-model="curYear" class="sel" @change="load">
          <option v-for="y in yearOptions" :key="y" :value="y">{{ y }}</option>
        </select>
        <select v-if="mode === 'month'" v-model="curMonth" class="sel" @change="load">
          <option v-for="m in monthOptions" :key="m" :value="m">{{ m }}月</option>
        </select>
        <select v-else v-model="curYear" class="sel" @change="load">
          <option v-for="y in yearOptions" :key="y" :value="y">{{ y }}年</option>
        </select>
        <button class="nav-arrow" @click="next">›</button>
      </div>

      <button class="btn-export" @click="doExport">导出 Excel</button>
    </div>

    <!-- 主体：左侧录入 + 账单，右侧报表 -->
    <div class="acct-body">
      <div class="acct-left">
        <TransactionForm @saved="onSaved" />

        <div class="kind-filter">
          <button class="switch-btn" :class="{ active: activeKind === '' }" @click="activeKind = ''">全部</button>
          <button
            v-for="(label, k) in kindLabelMap"
            :key="k"
            class="switch-btn"
            :class="{ active: activeKind === k }"
            @click="activeKind = k as Kind"
          >
            {{ label }}
          </button>
        </div>

        <TransactionList :list="filteredList" :kind-label="kindLabel" @changed="load" />
      </div>

      <div class="acct-right">
        <div class="overview">
          <div class="ov-item">
            <span class="ov-label">支出</span>
            <span class="ov-value">¥ {{ (summary?.totals.expense ?? 0).toFixed(2) }}</span>
          </div>
          <div class="ov-item">
            <span class="ov-label">收入</span>
            <span class="ov-value">¥ {{ (summary?.totals.income ?? 0).toFixed(2) }}</span>
          </div>
          <div class="ov-item">
            <span class="ov-label">净支出</span>
            <span class="ov-value">¥ {{ (summary?.net_expense ?? 0).toFixed(2) }}</span>
          </div>
          <div class="ov-item">
            <span class="ov-label">净收入</span>
            <span class="ov-value">¥ {{ (((summary?.totals.income ?? 0) - (summary?.net_expense ?? 0))).toFixed(2) }}</span>
          </div>
        </div>

        <SummaryCharts :summary="summary" :year-series="yearSeries" />
      </div>
    </div>
  </div>
</template>
