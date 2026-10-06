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
  // 资产账户
  listAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  getSettings,
  type Account,
  type AccountType,
  type Balance,
  // 预算
  getBudgetStatus,
  createBudget,
  deleteBudget,
  type BudgetStatus,
  // 周期账
  listRecurring,
  createRecurring,
  deleteRecurring,
  applyRecurring,
  type Recurring,
} from '@/api/accounting'
import { download } from '@/api/http'
import TransactionForm from '@/components/accounting/TransactionForm.vue'
import TransactionList from '@/components/accounting/TransactionList.vue'
import SummaryCharts from '@/components/accounting/SummaryCharts.vue'

// 视图模式：month / year
type ViewMode = 'month' | 'year'

const now = new Date()
const curYear = ref(now.getFullYear())
const curMonth = ref(now.getMonth() + 1) // 1-12
const mode = ref<ViewMode>('month')

const yearOptions = Array.from({ length: 10 }, (_, i) => now.getFullYear() - 5 + i)
const monthOptions = Array.from({ length: 12 }, (_, i) => i + 1)

const period = computed(() =>
  mode.value === 'month'
    ? `${curYear.value}-${String(curMonth.value).padStart(2, '0')}`
    : `${curYear.value}`,
)
const curMonthStr = computed(() => `${curYear.value}-${String(curMonth.value).padStart(2, '0')}`)

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

// ===== 资产账户 =====
const accounts = ref<Account[]>([])
// 净资产（全部口径）：账户合计 + 累计净收入 − 未收回垫付，由后端 balance() 计算
const balanceInfo = ref<Balance | null>(null)
const accountTypeLabels: Record<AccountType, string> = {
  cash: '现金',
  bank: '银行卡',
  alipay: '支付宝',
  wechat: '微信',
  other: '其他',
}
const newAccount = ref({ name: '', type: 'cash' as AccountType, balance: 0 })

// ===== 预算 =====
const budgetStatus = ref<BudgetStatus | null>(null)
const totalBudgetInput = ref<number>(0)
const catBudgetCat = ref('')
const catBudgetInput = ref<number>(0)
const EXPENSE_CATS = [
  '餐饮', '交通', '居住', '购物', '学习', '医疗', '娱乐', '人情', '其他',
]

// ===== 周期账 =====
const recurring = ref<Recurring[]>([])
const newRecurring = ref({
  kind: 'expense' as Kind,
  category: '居住',
  category2: '房租',
  amount: 0,
  freq: 'monthly' as 'monthly' | 'weekly',
  day_of_month: 1,
  note: '',
})

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

async function loadSide() {
  try {
    const [accts, bstatus, recs, bal] = await Promise.all([
      listAccounts(),
      getBudgetStatus(curMonthStr.value),
      listRecurring(),
      getSettings(),
    ])
    accounts.value = accts
    budgetStatus.value = bstatus
    recurring.value = recs
    balanceInfo.value = bal
    if (bstatus.total.limit > 0) totalBudgetInput.value = bstatus.total.limit
  } catch (e) {
    /* 侧栏非阻断 */
  }
}

const balanceTotal = computed(() =>
  accounts.value.reduce((s, a) => s + a.balance, 0),
)

// 净资产 = 账户合计 + 累计净收入 − 未收回垫付（全部口径，来自后端 balance()，
// 不能混用当前月/年的 summary，否则与账户余额（累计）口径不一致）
const netBalance = computed(() => balanceInfo.value?.balance ?? 0)

const overBudget = computed(() => budgetStatus.value?.total.over ?? false)

async function saveAccount(a: Account) {
  try {
    await updateAccount(a.id, { name: a.name, type: a.type, balance: a.balance })
    ElMessage.success('账户已更新')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

async function addAccount() {
  if (!newAccount.value.name) {
    ElMessage.warning('请输入账户名')
    return
  }
  try {
    const a = await createAccount({ ...newAccount.value })
    accounts.value.push(a)
    newAccount.value = { name: '', type: 'cash', balance: 0 }
    ElMessage.success('已添加账户')
  } catch (e) {
    ElMessage.error('添加失败')
  }
}

async function removeAccount(a: Account) {
  try {
    await deleteAccount(a.id)
    accounts.value = accounts.value.filter((x) => x.id !== a.id)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function setTotalBudget() {
  if (totalBudgetInput.value <= 0) {
    ElMessage.warning('请输入预算金额')
    return
  }
  try {
    await createBudget({ period: curMonthStr.value, scope: 'total', category: '', limit: totalBudgetInput.value })
    await loadSide()
    ElMessage.success('月度总预算已设定')
  } catch (e) {
    ElMessage.error('设定失败')
  }
}

async function setCatBudget() {
  if (!catBudgetCat.value || catBudgetInput.value <= 0) {
    ElMessage.warning('请选择分类并输入金额')
    return
  }
  try {
    await createBudget({ period: curMonthStr.value, scope: 'category', category: catBudgetCat.value, limit: catBudgetInput.value })
    await loadSide()
    ElMessage.success('分类预算已设定')
  } catch (e) {
    ElMessage.error('设定失败')
  }
}

async function removeBudget(id: number) {
  try {
    await deleteBudget(id)
    await loadSide()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function addRecurring() {
  if (!newRecurring.value.category) {
    ElMessage.warning('请选择分类')
    return
  }
  try {
    const r = await createRecurring({
      kind: newRecurring.value.kind,
      category: newRecurring.value.category,
      category2: newRecurring.value.category2,
      amount: newRecurring.value.amount > 0 ? newRecurring.value.amount : null,
      freq: newRecurring.value.freq,
      day_of_month: newRecurring.value.day_of_month,
      note: newRecurring.value.note,
      active: true,
    })
    recurring.value.push(r)
    newRecurring.value = { kind: 'expense', category: '居住', category2: '房租', amount: 0, freq: 'monthly', day_of_month: 1, note: '' }
    ElMessage.success('已添加周期账')
  } catch (e) {
    ElMessage.error('添加失败')
  }
}

async function removeRecurringItem(r: Recurring) {
  try {
    await deleteRecurring(r.id)
    recurring.value = recurring.value.filter((x) => x.id !== r.id)
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function applyRecurringMonth() {
  try {
    const res = await applyRecurring(curMonthStr.value)
    ElMessage.success(`已生成 ${res.created} 笔${res.skipped ? `，跳过 ${res.skipped} 笔（无金额）` : ''}`)
    await load()
    await loadSide()
  } catch (e) {
    ElMessage.error('生成失败')
  }
}

function onSaved() {
  load()
  loadSide()
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
  loadSide()
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
  loadSide()
}

async function doExport() {
  try {
    await download(exportUrl(query.value), 'accounting.xlsx')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  }
}

onMounted(() => {
  load()
  loadSide()
})
</script>

<template>
  <div class="accounting">
    <!-- 顶部：视图切换 + 账单浏览 -->
    <div class="acct-toolbar">
      <div class="view-switch">
        <button class="switch-btn" :class="{ active: mode === 'month' }" @click="mode = 'month'; load(); loadSide()">月账单</button>
        <button class="switch-btn" :class="{ active: mode === 'year' }" @click="mode = 'year'; load()">年账单</button>
      </div>

      <div class="period-nav">
        <button class="nav-arrow" @click="prev">‹</button>
        <select v-if="mode === 'month'" v-model="curYear" class="sel" @change="load(); loadSide()">
          <option v-for="y in yearOptions" :key="y" :value="y">{{ y }}</option>
        </select>
        <select v-if="mode === 'month'" v-model="curMonth" class="sel" @change="load(); loadSide()">
          <option v-for="m in monthOptions" :key="m" :value="m">{{ m }}月</option>
        </select>
        <select v-else v-model="curYear" class="sel" @change="load()">
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
        <!-- 概览 -->
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
            <span class="ov-label">未收回垫付</span>
            <span class="ov-value">¥ {{ (summary?.unreimbursed ?? 0).toFixed(2) }}</span>
          </div>
          <div class="ov-item">
            <span class="ov-label">净收入</span>
            <span class="ov-value">¥ {{ (summary?.net_income ?? 0).toFixed(2) }}</span>
          </div>
        </div>

        <!-- 超支预警 -->
        <div v-if="overBudget" class="budget-alert">
          ⚠ 本月总预算已超支 ¥{{ (budgetStatus!.total.spent - budgetStatus!.total.limit).toFixed(2) }}
        </div>

        <!-- 资产账户（多账户资产负债表） -->
        <div class="asset-card">
          <div class="card-title">资产账户 <span class="card-sub">合计 ¥{{ balanceTotal.toFixed(2) }}</span></div>
          <div v-for="a in accounts" :key="a.id" class="acct-row">
            <input v-model="a.name" class="field field-name" @change="saveAccount(a)" />
            <select v-model="a.type" class="sel sel-sm" @change="saveAccount(a)">
              <option v-for="(lbl, t) in accountTypeLabels" :key="t" :value="t">{{ lbl }}</option>
            </select>
            <input v-model.number="a.balance" type="number" step="0.01" class="field field-bal" @change="saveAccount(a)" />
            <button class="link-btn danger" @click="removeAccount(a)">删</button>
          </div>
          <div class="acct-row acct-add">
            <input v-model="newAccount.name" class="field field-name" placeholder="新账户名" />
            <select v-model="newAccount.type" class="sel sel-sm">
              <option v-for="(lbl, t) in accountTypeLabels" :key="t" :value="t">{{ lbl }}</option>
            </select>
            <input v-model.number="newAccount.balance" type="number" step="0.01" class="field field-bal" placeholder="余额" />
            <button class="link-btn" @click="addAccount">加</button>
          </div>
          <div class="asset-rows">
            <div class="asset-row">
              <span>账户合计</span>
              <span>¥ {{ balanceTotal.toFixed(2) }}</span>
            </div>
            <div class="asset-row">
              <span>累计净收入</span>
              <span>¥ {{ (balanceInfo?.net_income ?? 0).toFixed(2) }}</span>
            </div>
            <div class="asset-row">
              <span>未收回垫付</span>
              <span>¥ {{ (balanceInfo?.outstanding ?? 0).toFixed(2) }}</span>
            </div>
          </div>
          <div class="asset-total">
            <span>净资产（账户+净收入−未收回垫付）</span>
            <span class="asset-value" :class="netBalance >= 0 ? 'pos' : 'neg'">¥ {{ netBalance.toFixed(2) }}</span>
          </div>
        </div>

        <!-- 预算执行（仅月视图） -->
        <div v-if="mode === 'month'" class="budget-card">
          <div class="card-title">预算执行 · {{ curMonthStr }}</div>

          <!-- 总预算进度 -->
          <div class="budget-total">
            <div class="budget-head">
              <span>月度总预算</span>
              <span v-if="budgetStatus?.total.limit">
                ¥{{ budgetStatus.total.spent.toFixed(2) }} / ¥{{ budgetStatus.total.limit.toFixed(2) }}
                <button v-if="budgetStatus.total.id != null" class="link-btn danger" @click="removeBudget(budgetStatus.total.id)">清</button>
              </span>
              <span v-else>未设定</span>
            </div>
            <div v-if="budgetStatus?.total.limit" class="bar">
              <div class="bar-fill" :class="{ over: budgetStatus.total.over }"
                   :style="{ width: Math.min(budgetStatus.total.pct, 100) + '%' }"></div>
            </div>
            <p v-if="budgetStatus?.total.limit" class="budget-note">
              含支出 {{ budgetStatus.total.expense.toFixed(2) }}
              <template v-if="budgetStatus.total.reimburse > 0">
                · 垫付 {{ budgetStatus.total.reimburse.toFixed(2) }}（报销垫付同样计入总预算）
              </template>
            </p>
            <div v-else class="budget-set">
              <input v-model.number="totalBudgetInput" type="number" step="0.01" class="field" placeholder="设定本月总预算" />
              <button class="btn-asset-save" @click="setTotalBudget">设定</button>
            </div>
          </div>

          <!-- 分类预算 -->
          <div v-for="b in budgetStatus?.by_category" :key="b.category" class="budget-cat">
            <div class="budget-head">
              <span>{{ b.category }}</span>
              <span>¥{{ b.spent.toFixed(2) }} / ¥{{ b.limit.toFixed(2) }}
                <button class="link-btn danger" @click="removeBudget(b.id!)">清</button>
              </span>
            </div>
            <div class="bar">
              <div class="bar-fill" :class="{ over: b.over }" :style="{ width: Math.min(b.pct, 100) + '%' }"></div>
            </div>
          </div>

          <div class="budget-set budget-set-cat">
            <select v-model="catBudgetCat" class="sel">
              <option value="">分类预算…</option>
              <option v-for="c in EXPENSE_CATS" :key="c" :value="c">{{ c }}</option>
            </select>
            <input v-model.number="catBudgetInput" type="number" step="0.01" class="field" placeholder="金额" />
            <button class="btn-asset-save" @click="setCatBudget">添加</button>
          </div>
        </div>

        <!-- 周期账 -->
        <div class="recur-card">
          <div class="card-title">周期账
            <button class="btn-asset-save btn-sm" @click="applyRecurringMonth">生成本月</button>
          </div>
          <div v-for="r in recurring" :key="r.id" class="recur-row">
            <div class="recur-info">
              <span class="recur-cat">{{ r.category }}<template v-if="r.category2">·{{ r.category2 }}</template></span>
              <span class="recur-amt">{{ r.amount != null ? '¥' + r.amount.toFixed(2) : '手动金额' }}</span>
              <span class="recur-meta">{{ r.freq === 'monthly' ? '每月' + r.day_of_month + '号' : '每周' }}</span>
            </div>
            <button class="link-btn danger" @click="removeRecurringItem(r)">删</button>
          </div>
          <div class="recur-add">
            <select v-model="newRecurring.kind" class="sel sel-sm">
              <option value="expense">支出</option>
              <option value="income">收入</option>
            </select>
            <input v-model="newRecurring.category" class="field field-name" placeholder="一级" />
            <input v-model="newRecurring.category2" class="field field-name" placeholder="二级" />
            <input v-model.number="newRecurring.amount" type="number" step="0.01" class="field field-bal" placeholder="金额" />
            <button class="link-btn" @click="addRecurring">加</button>
          </div>
        </div>

        <SummaryCharts :summary="summary" :year-series="yearSeries" />
      </div>
    </div>
  </div>
</template>
