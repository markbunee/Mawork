<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { ElMessage } from 'element-plus'
import {
  listDaily,
  listYears,
  getDaily,
  upsertDaily,
  exportDailyUrl,
  type DailyGroup,
  type CalTask,
} from '@/api/daily'

const years = ref<string[]>([])
const year = ref(new Date().getFullYear().toString())

const groups = ref<DailyGroup[]>([])
const activeDate = ref('')
const body = ref('')
const calTasks = ref<CalTask[]>([])
const exists = ref(false)
const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)

const md = new MarkdownIt({ html: false, linkify: true })
const viewMode = ref<'code' | 'preview'>('code')
const rendered = computed(() => md.render(body.value))

// 折叠状态：month -> boolean
const collapsed = ref<Record<string, boolean>>({})

const today = computed(() => {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
})

const allDates = computed(() => groups.value.flatMap((g) => g.dates))
const isNew = computed(() => !exists.value && !!activeDate.value)

// ---------------------------------------------------------------------------
// 日期选择：可跳到任意日期补写（昨天 / 前几天 / 跨年）
// ---------------------------------------------------------------------------
function toDateStr(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

function shiftDateStr(date: string, delta: number): string {
  const d = new Date(Number(date.slice(0, 4)), Number(date.slice(5, 7)) - 1, Number(date.slice(8, 10)))
  d.setDate(d.getDate() + delta)
  return toDateStr(d)
}

/** 未来日期不允许写日报 */
function disableFuture(d: Date): boolean {
  return toDateStr(d) > today.value
}

function ensureYear(y: string) {
  if (!years.value.includes(y)) {
    years.value = [...years.value, y].sort((a, b) => Number(b) - Number(a))
  }
}

/** 切换到指定日期：必要时顺带切换年份并刷新左侧日期树 */
async function goToDate(date: string) {
  if (!date || date === activeDate.value) return
  await flushSave()
  const y = date.slice(0, 4)
  if (y !== year.value) {
    year.value = y
    ensureYear(y)
    await loadGroups()
  }
  activeDate.value = date
  await loadContent()
}

function onPickDate(date: unknown) {
  void goToDate(typeof date === 'string' ? date : '')
}

function shiftDay(delta: number) {
  void goToDate(shiftDateStr(activeDate.value || today.value, delta))
}

/** delta 相对今天：0=今天，-1=昨天 */
function quickDay(delta: number) {
  void goToDate(shiftDateStr(today.value, delta))
}

const defaultTemplate = `一、今日工作内容

1. 

二、问题反馈



三、明日工作计划

`

// ---------------------------------------------------------------------------
// 保存：输入停顿 1.2s 自动保存；切换前强制落盘
// ---------------------------------------------------------------------------
let saveTimer: number | undefined
// 载入内容（切换日期）时程序化设置 body，不应触发「已修改 / 自动保存」
let loadingContent = false

watch(body, () => {
  if (loadingContent) return
  dirty.value = true
  if (saveTimer) window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => {
    saveTimer = undefined
    void doSave(true)
  }, 1200)
})

function cancelAuto() {
  if (saveTimer) window.clearTimeout(saveTimer)
  saveTimer = undefined
}

async function doSave(silent: boolean) {
  if (!activeDate.value || !dirty.value || saving.value) return
  saving.value = true
  try {
    const res = await upsertDaily(year.value, activeDate.value, body.value)
    dirty.value = false
    exists.value = true
    ensureYear(activeDate.value.slice(0, 4))
    void loadGroups()
    if (!silent) {
      ElMessage.success(
        res.plan_synced > 0
          ? `已保存，${res.plan_synced} 条明日计划已写入次日日历`
          : '已保存',
      )
    }
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

function save() {
  dirty.value = true
  void doSave(false)
}

async function flushSave() {
  if (dirty.value) await doSave(true)
}

async function loadYears() {
  const res = await listYears()
  years.value = res.years
  if (years.value.length > 0 && !years.value.includes(year.value)) {
    year.value = years.value[0]
  }
}

async function loadGroups() {
  const res = await listDaily(year.value)
  groups.value = res.groups
}

async function selectDate(date: string) {
  await flushSave()
  activeDate.value = date
  await loadContent()
}

async function loadContent() {
  loading.value = true
  try {
    const res = await getDaily(year.value, activeDate.value)
    calTasks.value = res.calTasks
    exists.value = res.exists
    loadingContent = true
    body.value = res.body && res.body.trim() ? res.body : defaultTemplate
    await nextTick()
    dirty.value = false
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loadingContent = false
    loading.value = false
  }
}

async function newDaily(date?: string) {
  await flushSave()
  const target = date ?? today.value
  const y = target.slice(0, 4)
  if (y !== year.value) {
    year.value = y
    ensureYear(y)
    await loadGroups()
  }
  activeDate.value = target
  calTasks.value = []
  exists.value = false
  loadingContent = true
  body.value = defaultTemplate
  await nextTick()
  loadingContent = false
  dirty.value = false
}

async function changeYear(y: string) {
  await flushSave()
  year.value = y
  activeDate.value = ''
  calTasks.value = []
  body.value = ''
  dirty.value = false
  await loadGroups()
}

function toggleGroup(title: string) {
  collapsed.value[title] = !collapsed.value[title]
}

function isCollapsed(title: string): boolean {
  return !!collapsed.value[title]
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    save()
  }
}

onMounted(async () => {
  await loadYears()
  await loadGroups()
  const dates = allDates.value
  if (dates.length > 0) {
    activeDate.value = dates[dates.length - 1]
    await loadContent()
  } else {
    await newDaily()
  }
})

onBeforeUnmount(() => {
  cancelAuto()
})
</script>

<template>
  <div class="daily" @keydown="onKeydown">
    <div class="daily-list">
      <div class="list-header">
        <select v-model="year" class="year-select" @change="changeYear(year)">
          <option v-for="y in years" :key="y" :value="y">{{ y }}年</option>
        </select>
        <button class="btn-new" title="新建日报（默认今天；可在上方选任意日期补写）" @click="newDaily()">
          ＋ 新日报
        </button>
      </div>

      <div class="daily-tree">
        <div v-if="groups.length === 0" class="empty-tip">还没有日报，点「新日报」开始（可改日期补写）</div>

        <div v-for="g in groups" :key="g.title" class="month-group">
          <div class="month-head" @click="toggleGroup(g.title)">
            <span class="month-arrow" :class="{ open: !isCollapsed(g.title) }">▸</span>
            <span class="month-title">{{ g.title }}</span>
            <span v-if="g.dates.length" class="month-count">{{ g.dates.length }}</span>
          </div>

          <ul v-if="!isCollapsed(g.title)" class="date-list">
            <li
              v-for="date in g.dates"
              :key="date"
              class="date-item"
              :class="{ active: date === activeDate }"
              @click="selectDate(date)"
            >
              <span class="date-dot"></span>
              <span class="date-text">{{ date }}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div class="daily-editor">
      <div class="editor-head">
        <div class="editor-title">
          <el-date-picker
            :model-value="activeDate"
            type="date"
            value-format="YYYY-MM-DD"
            format="YYYY-MM-DD"
            placeholder="选择日期"
            :clearable="false"
            :disabled-date="disableFuture"
            size="small"
            class="date-picker"
            @change="onPickDate"
          />
          <button class="day-nav" title="前一天" @click="shiftDay(-1)">‹</button>
          <button class="day-nav" title="后一天" @click="shiftDay(1)">›</button>
          <button class="day-quick" :class="{ active: activeDate === today }" @click="quickDay(0)">今天</button>
          <button class="day-quick" @click="quickDay(-1)">昨天</button>
          <span v-if="isNew" class="tag-new">新建</span>
          <span v-if="!activeDate" class="placeholder-hint">选择日期开始记录</span>
        </div>
        <div class="editor-actions">
          <span v-if="dirty" class="dirty-hint">未保存…</span>
          <button class="switch-btn" :class="{ active: viewMode === 'preview' }" @click="viewMode = viewMode === 'code' ? 'preview' : 'code'">
            {{ viewMode === 'code' ? '预览' : '代码' }}
          </button>
          <a class="btn-export" :href="year ? exportDailyUrl(year) : undefined" download>导出</a>
          <button class="btn-save" :disabled="saving || !activeDate" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>

      <!-- 来自日历的任务：只读展示，勾选请回到日历页 -->
      <div v-if="activeDate && calTasks.length" class="daily-caltasks">
        <span class="cal-tasks-label">来自日历</span>
        <span
          v-for="t in calTasks"
          :key="t.id"
          class="cal-task-chip"
          :class="{ done: t.done }"
        >{{ t.done ? '已完成- ' : '未完成- ' }}{{ t.text }}</span>
      </div>

      <textarea
        v-if="viewMode === 'code'"
        v-model="body"
        class="editor-textarea"
        spellcheck="false"
        placeholder="记录今天…（三、明日工作计划 的内容会自动写入明天的日历）"
        @keydown.stop
      ></textarea>
      <div v-else class="md-body" v-html="rendered"></div>
    </div>
  </div>
</template>
