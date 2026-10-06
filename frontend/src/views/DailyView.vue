<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useIsMobile } from '@/utils/useIsMobile'
import MarkdownIt from 'markdown-it'
import { ElMessage } from 'element-plus'
import {
  listDaily,
  listYears,
  getDaily,
  upsertDaily,
  exportDailyUrl,
  searchDaily,
  listTags,
  type DailyGroup,
  type CalTask,
  type DailySearchResult,
} from '@/api/daily'
import { download } from '@/api/http'
import TemplatePicker from '@/components/TemplatePicker.vue'
import TagPanel from '@/components/TagPanel.vue'

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
// 预览渲染：原先是 computed，每敲一个字符就全量 render 一次 Markdown，
// 长日报下明显卡顿。改为 250ms 防抖；切换日期（loadingContent）时同步渲染，避免预览滞后。
const rendered = ref(md.render(body.value))
let renderTimer: number | undefined
watch(body, (v) => {
  if (loadingContent) {
    rendered.value = md.render(v)
    return
  }
  if (renderTimer) window.clearTimeout(renderTimer)
  renderTimer = window.setTimeout(() => {
    rendered.value = md.render(v)
  }, 250)
})

// 手机端：单日编辑弹层状态 + 断点
const isMobile = useIsMobile()
const route = useRoute()
const sheetOpen = ref(false)

// 展开状态：month -> boolean。默认全部折叠，点月份标题才展开
const expanded = ref<Record<string, boolean>>({})

const today = computed(() => {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
})

const allDates = computed(() => groups.value.flatMap((g) => g.dates))
const isNew = computed(() => !exists.value && !!activeDate.value)

/** 导出某年全部日报：带令牌下载，避免直接拼 URL 被鉴权拦截 */
async function doExportDaily() {
  if (!year.value) return
  try {
    await download(exportDailyUrl(year.value), `daily_${year.value}.md`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  }
}

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

const weeklyTemplate = `## 本周回顾

### 完成
1. 

### 不足


### 下周重点

`

const templates: Record<string, string> = {
  日报: defaultTemplate,
  周报: weeklyTemplate,
}
const showTpl = ref(false)
function applyTemplate(key: string) {
  if (body.value.trim() && !window.confirm('当前内容非空，套用模板将覆盖，确认？')) return
  loadingContent = true
  body.value = templates[key]
  dirty.value = true
  showTpl.value = false
}

// 统一模板库（横切能力 E3）：日报/周报模板改为从模板库取，可自建
const tplOpen = ref(false)

// 标签中台（横切能力 E6）
const tagHubOpen = ref(false)
function onApplyLibraryTpl(item: { content: string }) {
  if (body.value.trim() && !window.confirm('当前内容非空，套用模板将覆盖，确认？')) return
  loadingContent = true
  body.value = item.content
  dirty.value = true
}

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

async function loadTags() {
  try {
    const res = await listTags(year.value)
    yearTags.value = res.tags
  } catch {
    yearTags.value = {}
  }
}

async function loadGroups() {
  const res = await listDaily(year.value)
  groups.value = res.groups
  void loadTags()
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
  expanded.value[title] = !expanded.value[title]
}

function isCollapsed(title: string): boolean {
  return !expanded.value[title]
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    save()
  }
}

// ---------------------------------------------------------------------------
// 搜索 + 标签过滤
// ---------------------------------------------------------------------------
const searchQuery = ref('')
const searchResults = ref<DailySearchResult[]>([])
const searching = ref(false)
const isSearching = computed(() => searchQuery.value.trim().length > 0)
let searchTimer: number | undefined

function onSearchInput() {
  if (searchTimer) window.clearTimeout(searchTimer)
  const q = searchQuery.value.trim()
  if (!q) {
    searchResults.value = []
    return
  }
  searchTimer = window.setTimeout(async () => {
    searching.value = true
    try {
      const res = await searchDaily(year.value, q)
      searchResults.value = res.results
    } catch {
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

function clearSearch() {
  searchQuery.value = ''
  searchResults.value = []
}

const yearTags = ref<Record<string, string[]>>({})
const activeTag = ref('')
const tagList = computed(() => Object.keys(yearTags.value))
const tagDates = computed(() =>
  activeTag.value ? new Set(yearTags.value[activeTag.value] || []) : null,
)
const displayGroups = computed(() => {
  if (!tagDates.value) return groups.value
  return groups.value
    .map((g) => ({ ...g, dates: g.dates.filter((d) => tagDates.value!.has(d)) }))
    .filter((g) => g.dates.length > 0)
})

function toggleTag(t: string) {
  activeTag.value = activeTag.value === t ? '' : t
}

function highlight(snippet: string, q: string): { t: string; hit: boolean }[] {
  const idx = snippet.indexOf(q)
  if (idx < 0) return [{ t: snippet, hit: false }]
  return [
    { t: snippet.slice(0, idx), hit: false },
    { t: snippet.slice(idx, idx + q.length), hit: true },
    { t: snippet.slice(idx + q.length), hit: false },
  ]
}

// ---------------------------------------------------------------------------
// Markdown 编辑器：工具栏 + 桌面分屏实时预览
// ---------------------------------------------------------------------------
const textareaRef = ref<HTMLTextAreaElement | null>(null)

function surround(before: string, after: string, placeholder: string) {
  const ta = textareaRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const sel = body.value.slice(start, end) || placeholder
  body.value = body.value.slice(0, start) + before + sel + after + body.value.slice(end)
  dirty.value = true
  nextTick(() => {
    ta.focus()
    ta.selectionStart = start + before.length
    ta.selectionEnd = start + before.length + sel.length
  })
}

function toggleLinePrefix(prefix: string) {
  const ta = textareaRef.value
  if (!ta) return
  const pos = ta.selectionStart
  const lineStart = body.value.lastIndexOf('\n', pos - 1) + 1
  const lineEnd = body.value.indexOf('\n', pos)
  const end2 = lineEnd === -1 ? body.value.length : lineEnd
  const line = body.value.slice(lineStart, end2)
  const newLine = line.startsWith(prefix) ? line.slice(prefix.length) : prefix + line
  body.value = body.value.slice(0, lineStart) + newLine + body.value.slice(end2)
  dirty.value = true
  nextTick(() => {
    ta.focus()
    ta.selectionStart = ta.selectionEnd = lineStart + newLine.length
  })
}

function insertAtCursor(text: string) {
  const ta = textareaRef.value
  if (!ta) {
    body.value += text
    return
  }
  const start = ta.selectionStart
  body.value = body.value.slice(0, start) + text + body.value.slice(start)
  dirty.value = true
  nextTick(() => {
    ta.focus()
    ta.selectionStart = ta.selectionEnd = start + text.length
  })
}

function applyMd(cmd: string) {
  switch (cmd) {
    case 'h2': return toggleLinePrefix('## ')
    case 'bold': return surround('**', '**', '加粗文字')
    case 'italic': return surround('*', '*', '斜体文字')
    case 'ul': return toggleLinePrefix('- ')
    case 'todo': return toggleLinePrefix('- [ ] ')
    case 'quote': return toggleLinePrefix('> ')
    case 'code': return surround('`', '`', '代码')
    case 'link': return surround('[', '](https://)', '链接文字')
    case 'hr': return insertAtCursor('\n---\n')
    case 'table':
      return insertAtCursor(
        '\n| 项目 | 内容 |\n| --- | --- |\n|  |  |\n',
      )
  }
}

// 当前日报标签（从正文解析 #标签）
const currentTags = computed(() => {
  const set = new Set<string>()
  const re = /(?:^|\s)#([^\s#,，。；;：:]+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(body.value))) set.add(m[1])
  return [...set]
})

// 字数（中文按字、英文数字按词）
const wordCount = computed(() => {
  const text = body.value || ''
  const cjk = (text.match(/[一-鿿]/g) || []).length
  const words = (text.replace(/[一-鿿]/g, ' ').match(/[A-Za-z0-9]+/g) || []).length
  return cjk + words
})

// 最近连续写作天数（截至已写的最近一篇）
const streak = computed(() => {
  const arr = allDates.value
  if (!arr.length) return 0
  const set = new Set(arr)
  const max = arr.reduce((a, b) => (b > a ? b : a))
  let s = 0
  const d = new Date(Number(max.slice(0, 4)), Number(max.slice(5, 7)) - 1, Number(max.slice(8, 10)))
  while (set.has(toDateStr(d))) {
    s++
    d.setDate(d.getDate() - 1)
  }
  return s
})

onMounted(async () => {
  await loadYears()
  await loadGroups()
  // 支持从日历「写日报」跳转指定日期
  const q = route.query.date
  if (typeof q === 'string' && q) {
    await goToDate(q)
    return
  }
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
  <div class="daily" :class="{ 'sheet-open': sheetOpen }" @keydown="onKeydown">
    <div class="daily-list">
      <div class="list-header">
        <select v-model="year" class="year-select" @change="changeYear(year)">
          <option v-for="y in years" :key="y" :value="y">{{ y }}年</option>
        </select>
        <button class="btn-new" title="新建日报（默认今天；可在上方选任意日期补写）" @click="newDaily()">
          ＋ 新日报
        </button>
      </div>

      <div class="search-row">
        <input
          v-model="searchQuery"
          class="search-input"
          type="text"
          placeholder="搜索日报内容…"
          @input="onSearchInput"
        />
        <button v-if="isSearching" class="search-clear" title="清除" @click="clearSearch">✕</button>
      </div>

      <div v-if="tagList.length" class="tag-chips">
        <button
          v-for="t in tagList"
          :key="t"
          class="tag-chip"
          :class="{ active: activeTag === t }"
          :title="`${yearTags[t].length} 篇`"
          @click="toggleTag(t)"
        >
          #{{ t }} <span class="tag-n">{{ yearTags[t].length }}</span>
        </button>
        <button class="tag-hub-btn" title="跨模块标签中台" @click="tagHubOpen = true">标签中台</button>
      </div>

      <div class="daily-tree">
        <div v-if="isSearching" class="search-results">
          <div v-if="searching" class="empty-tip">搜索中…</div>
          <div v-else-if="!searchResults.length" class="empty-tip">
            没有匹配「{{ searchQuery }}」的日报
          </div>
          <div
            v-for="r in searchResults"
            :key="r.date"
            class="search-result"
            @click="selectDate(r.date)"
          >
            <span class="sr-date">{{ r.date }}</span>
            <span class="sr-snippet">
              <template v-for="(p, i) in highlight(r.snippet, searchQuery)" :key="i">
                <mark v-if="p.hit">{{ p.t }}</mark><template v-else>{{ p.t }}</template>
              </template>
            </span>
          </div>
        </div>

        <template v-else>
          <div v-if="displayGroups.length === 0" class="empty-tip">
            还没有日报，点「新日报」开始（可改日期补写）
          </div>

          <div v-for="g in displayGroups" :key="g.title" class="month-group">
            <div class="month-head" @click="toggleGroup(g.title)">
              <span class="month-arrow" :class="{ open: !isCollapsed(g.title) }">▸</span>
              <span class="month-title">{{ g.title }}</span>
              <span v-if="g.dates.length" class="month-count">{{ g.dates.length }}</span>
            </div>

            <ul v-if="activeTag || !isCollapsed(g.title)" class="date-list">
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
        </template>
      </div>
    </div>

    <!-- 手机端：拉起编辑的浮动按钮（桌面不显示） -->
    <button v-if="isMobile" class="daily-fab" @click="sheetOpen = true">写日报</button>

    <div class="daily-editor" :class="{ sheet: isMobile }">
      <div v-if="isMobile" class="sheet-bar" @click="sheetOpen = false">
        <span class="sheet-bar-title">编辑日报</span>
        <span class="sheet-bar-done">完成</span>
      </div>
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
          <span class="meta-pill">{{ wordCount }} 字</span>
          <span v-if="streak > 0" class="meta-pill">连写 {{ streak }} 天</span>
          <span v-if="currentTags.length" class="current-tags">
            <span v-for="t in currentTags" :key="t" class="ctag">#{{ t }}</span>
          </span>
          <span v-if="dirty" class="dirty-hint">未保存…</span>
          <div class="tpl-wrap">
            <button class="switch-btn" @click="showTpl = !showTpl">模板</button>
            <div v-if="showTpl" class="tpl-menu">
              <button @click="showTpl = false; tplOpen = true">模板库…</button>
              <button v-for="(v, k) in templates" :key="k" @click="applyTemplate(k as string)">
                {{ k }}模板
              </button>
            </div>
          </div>
          <button
            v-if="!isMobile"
            class="switch-btn"
            :class="{ active: viewMode === 'preview' }"
            @click="viewMode = viewMode === 'code' ? 'preview' : 'code'"
          >
            {{ viewMode === 'code' ? '预览' : '编辑' }}
          </button>
          <button class="btn-export" @click="doExportDaily">导出</button>
          <button class="btn-save" :disabled="saving || !activeDate" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>

      <!-- Markdown 工具栏 -->
      <div class="md-toolbar">
        <button title="标题" @click="applyMd('h2')">H</button>
        <button title="加粗" @click="applyMd('bold')"><b>B</b></button>
        <button title="斜体" @click="applyMd('italic')"><i>I</i></button>
        <button title="列表" @click="applyMd('ul')">列表</button>
        <button title="待办" @click="applyMd('todo')">待办</button>
        <button title="引用" @click="applyMd('quote')">引用</button>
        <button title="行内代码" @click="applyMd('code')">&lt;/&gt;</button>
        <button title="链接" @click="applyMd('link')">链接</button>
        <button title="分割线" @click="applyMd('hr')">分割线</button>
        <button title="表格" @click="applyMd('table')">表格</button>
      </div>

      <!-- 桌面：左编辑右预览分屏；手机：按 viewMode 切换 -->
      <div class="editor-split" :class="{ mobile: isMobile, showPreview: viewMode === 'preview' }">
        <textarea
          ref="textareaRef"
          v-model="body"
          class="editor-textarea"
          spellcheck="false"
          placeholder="记录今天…（三、明日工作计划 的内容会自动写入明天的日历）"
          @keydown.stop
        ></textarea>
        <div class="md-body editor-preview" v-html="rendered"></div>
      </div>
    </div>

    <!-- 统一模板库（横切能力 E3） -->
    <TemplatePicker
      :open="tplOpen"
      :scope="['daily', 'weekly', 'monthly']"
      title="模板库（日报 / 周报 / 月报）"
      @close="tplOpen = false"
      @apply="onApplyLibraryTpl"
    />

    <!-- 标签中台（横切能力 E6） -->
    <TagPanel :open="tagHubOpen" @close="tagHubOpen = false" />
  </div>
</template>
