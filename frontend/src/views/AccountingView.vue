<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listTransactions,
  getSummary,
  getYearSeries,
  exportUrl,
  getSettings,
  saveSettings,
  type Kind,
  type Transaction,
  type Summary,
  type YearSeries,
  type Balance,
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

const balance = ref<Balance | null>(null)
const depositInput = ref<number>(0)
const savingInput = ref<number>(0)
const savingSettings = ref(false)

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
    const [list, sum, series, bal] = await Promise.all([
      listTransactions(q),
      getSummary(q),
      mode.value === 'year' ? getYearSeries(yearStr) : Promise.resolve(null),
      getSettings(),
    ])
    transactions.value = list
    summary.value = sum
    yearSeries.value = series
    balance.value = bal
    depositInput.value = bal.deposit
    savingInput.value = bal.saving
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function saveBalance() {
  savingSettings.value = true
  try {
    balance.value = await saveSettings(depositInput.value ?? 0, savingInput.value ?? 0)
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    savingSettings.value = false
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
            <span class="ov-label">未报销费用</span>
            <span class="ov-value">¥ {{ (summary?.unreimbursed ?? 0).toFixed(2) }}</span>
          </div>
          <div class="ov-item">
            <span class="ov-label">已报销到账</span>
            <span class="ov-value">¥ {{ (summary?.settled ?? 0).toFixed(2) }}</span>
          </div>
          <div class="ov-item">
            <span class="ov-label">净收入</span>
            <span class="ov-value">¥ {{ (summary?.net_income ?? 0).toFixed(2) }}</span>
          </div>
        </div>

        <div class="asset-card">
          <div class="asset-row">
            <label class="asset-label">存款</label>
            <input v-model.number="depositInput" class="field" type="number" min="0" step="0.01" placeholder="0.00" />
            <label class="asset-label">储蓄</label>
            <input v-model.number="savingInput" class="field" type="number" min="0" step="0.01" placeholder="0.00" />
            <button class="btn-asset-save" :disabled="savingSettings" @click="saveBalance">
              {{ savingSettings ? '保存中…' : '保存' }}
            </button>
          </div>
          <div class="asset-row asset-hint-row">
            <span class="asset-hint">存款/储蓄 = 启用记账前的账户期初余额（余额 = 期初 + 累计净收入 − 未收回垫付）</span>
          </div>
          <div class="asset-row asset-total">
            <span class="asset-label">余额</span>
            <span class="asset-value" :class="(balance?.balance ?? 0) >= 0 ? 'pos' : 'neg'">
              ¥ {{ (balance?.balance ?? 0).toFixed(2) }}
            </span>
            <span class="asset-hint">
              = 存款 + 储蓄 + 累计净收入({{ (balance?.net_income ?? 0).toFixed(2) }}) − 未收回垫付({{ (balance?.outstanding ?? 0).toFixed(2) }})
            </span>
          </div>
        </div>

        <SummaryCharts :summary="summary" :year-series="yearSeries" />
      </div>
    </div>
  </div>
</template>
