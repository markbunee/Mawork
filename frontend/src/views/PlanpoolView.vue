<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { exportUrl, getStats, listColumns, listTasks, progressOptions, type Column, type Stats, type Task } from '@/api/planpool'
import { download } from '@/api/http'
import TaskTable from '@/components/planpool/TaskTable.vue'
import TaskBoard from '@/components/planpool/TaskBoard.vue'
import TaskCalendar from '@/components/planpool/TaskCalendar.vue'
import ColumnManager from '@/components/planpool/ColumnManager.vue'
import SegmentedControl from '@/components/common/SegmentedControl.vue'

const now = new Date()
const curYear = ref(now.getFullYear())
const months = Array.from({ length: 12 }, (_, i) => i + 1)
const selectedMonth = ref<number>(now.getMonth() + 1)

const tasks = ref<Task[]>([])
const stats = ref<Stats>({ total: 0, done: 0, todo: 0, doing: 0 })
const columns = ref<Column[]>([])

type View = 'table' | 'board' | 'calendar'
const view = ref<View>('table')

// 视图切换：分段控件（表格 / 看板 / 日历），指示块宽度由组件按项数计算
const views: { key: View; label: string }[] = [
  { key: 'table', label: '表格' },
  { key: 'board', label: '看板' },
  { key: 'calendar', label: '日历' },
]

// 统计卡：总数 + 未完成 / 进行中 / 已完成，对齐设计稿的统计条
const statCards = computed(() => [
  { key: 'todo', label: '未完成', value: stats.value.todo },
  { key: 'doing', label: '进行中', value: stats.value.doing },
  { key: 'done', label: '已完成', value: stats.value.done },
])

const showFilter = ref(false)
const showCM = ref(false)
const filterQ = ref('')
const filterStatus = ref('')
const filterLevel1 = ref('')
const groupBy = ref<'level1' | null>('level1')
const sortKey = ref<string | null>('end_date')
const sortDir = ref<'asc' | 'desc'>('asc')

function period(): string {
  return `${curYear.value}-${String(selectedMonth.value).padStart(2, '0')}`
}

async function load() {
  try {
    const month = period()
    const [t, s, cs] = await Promise.all([listTasks(month), getStats(month), listColumns()])
    tasks.value = t
    stats.value = s
    columns.value = cs
  } catch {
    ElMessage.error('加载失败')
  }
}

function selectMonth(m: number) {
  selectedMonth.value = m
  load()
}

function onSort(key: string) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
}

const level1Options = computed(() => Array.from(new Set(tasks.value.map((t) => t.level1).filter(Boolean))))

// 筛选 + 排序
const displayTasks = computed(() => {
  const q = filterQ.value.trim().toLowerCase()
  let list = tasks.value.filter((t) => {
    if (filterStatus.value && t.progress !== filterStatus.value) return false
    if (filterLevel1.value && t.level1 !== filterLevel1.value) return false
    if (q) {
      const hay = [t.level1, t.title, t.note, t.progress, ...Object.values(t.fields || {})].join(' ').toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
  if (sortKey.value) {
    const key = sortKey.value
    const isNum = key === 'completion' || columns.value.find((c) => c.key === key)?.ftype === 'number'
    list = list.slice().sort((a, b) => {
      const av = a.fields?.[key] ?? (a as unknown as Record<string, unknown>)[key] ?? ''
      const bv = b.fields?.[key] ?? (b as unknown as Record<string, unknown>)[key] ?? ''
      let r = 0
      if (isNum) r = Number(av) - Number(bv)
      else r = String(av).localeCompare(String(bv), 'zh')
      return sortDir.value === 'asc' ? r : -r
    })
  }
  return list
})

function toggleGroup() {
  groupBy.value = groupBy.value ? null : 'level1'
}

async function doExport() {
  try {
    await download(exportUrl, 'tasks.xlsx')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  }
}

function onColumnsUpdated() {
  load()
}

onMounted(load)
</script>

<template>
  <div class="planpool">
    <!-- 统计条：三张统计卡，对齐设计稿 -->
    <div class="pp-stats">
      <div v-for="c in statCards" :key="c.key" class="pp-stat-card" :class="c.key">
        <span class="pp-stat-num">{{ c.value }}</span>
        <span class="pp-stat-cap">{{ c.label }}</span>
      </div>
      <span class="pp-stat-total">共 {{ stats.total }} 项</span>
    </div>

    <!-- 周期 + 视图切换 + 操作 -->
    <div class="pp-toolbar">
      <SegmentedControl
        v-model="view"
        :items="views"
        aria-label="日程视图切换"
      />
      <div class="pp-actions">
        <button class="pp-act" @click="toggleGroup()">{{ groupBy ? '取消分组' : '按计划分组' }}</button>
        <button class="pp-act" @click="showFilter = !showFilter">筛选</button>
        <button class="pp-act" @click="showCM = true">列管理</button>
        <button class="btn-export" @click="doExport">导出 Excel</button>
      </div>
    </div>

    <!-- 月份 -->
    <div class="pp-months">
      <button
        v-for="m in months"
        :key="m"
        class="pp-month"
        :class="{ active: selectedMonth === m }"
        @click="selectMonth(m)"
      >
        {{ m }}月
      </button>
      <select v-model="curYear" class="pp-year" @change="load">
        <option v-for="y in [curYear - 1, curYear, curYear + 1]" :key="y" :value="y">{{ y }}</option>
      </select>
    </div>

    <!-- 筛选条 -->
    <div v-if="showFilter" class="pp-filterbar">
      <input v-model="filterQ" class="pp-filter-input" placeholder="搜索任务 / 备注 / 自定义字段…" />
      <select v-model="filterStatus" class="pp-filter-sel">
        <option value="">全部状态</option>
        <option v-for="p in progressOptions" :key="p" :value="p">{{ p }}</option>
      </select>
      <select v-model="filterLevel1" class="pp-filter-sel">
        <option value="">全部分类</option>
        <option v-for="l in level1Options" :key="l" :value="l">{{ l }}</option>
      </select>
      <button class="pp-filter-clear" @click="filterQ = ''; filterStatus = ''; filterLevel1 = ''">清空</button>
    </div>

    <!-- 视图 -->
    <TaskTable
      v-if="view === 'table'"
      :tasks="displayTasks"
      :columns="columns"
      :group-by="groupBy"
      :sort-key="sortKey"
      :sort-dir="sortDir"
      @changed="load"
      @sort="onSort"
    />
    <TaskBoard v-else-if="view === 'board'" :tasks="displayTasks" :columns="columns" @changed="load" />
    <TaskCalendar
      v-else
      :tasks="tasks"
      :year="curYear"
      :month="selectedMonth"
      @goto="view = 'table'"
    />

    <ColumnManager v-if="showCM" :columns="columns" @updated="onColumnsUpdated" @close="showCM = false" />
  </div>
</template>
