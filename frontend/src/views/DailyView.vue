<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listDaily, listYears, getDaily, upsertDaily, type DailyGroup } from '@/api/daily'

const years = ref<string[]>([])
const year = ref(new Date().getFullYear().toString())

const groups = ref<DailyGroup[]>([])
const activeDate = ref('')
const body = ref('')
const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)

// 折叠状态：month -> boolean
const collapsed = ref<Record<string, boolean>>({})

const today = computed(() => {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}.${m}.${day}`
})

const allDates = computed(() => groups.value.flatMap((g) => g.dates))
const isNew = computed(() => !allDates.value.includes(activeDate.value))

const defaultTemplate = (date: string) => `一、今日工作内容

1. 

二、问题反馈



三、明日工作计划

`

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
  if (dirty.value && !confirm('当前有未保存的修改，确定切换吗？')) {
    return
  }
  activeDate.value = date
  await loadContent()
}

async function loadContent() {
  loading.value = true
  try {
    if (isNew.value) {
      body.value = defaultTemplate(activeDate.value)
    } else {
      const res = await getDaily(year.value, activeDate.value)
      body.value = res.body
    }
    dirty.value = false
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function newDaily() {
  if (dirty.value && !confirm('当前有未保存的修改，确定新建吗？')) {
    return
  }
  activeDate.value = today.value
  body.value = defaultTemplate(today.value)
  dirty.value = false
}

async function changeYear(y: string) {
  year.value = y
  activeDate.value = ''
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

async function save() {
  if (!activeDate.value) return
  saving.value = true
  try {
    await upsertDaily(year.value, activeDate.value, body.value)
    dirty.value = false
    await loadGroups()
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
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
    // 默认打开最近一篇（最后一天）
    activeDate.value = dates[dates.length - 1]
    await loadContent()
  } else {
    newDaily()
  }
})
</script>

<template>
  <div class="daily" @keydown="onKeydown">
    <div class="daily-list">
      <div class="list-header">
        <select v-model="year" class="year-select" @change="changeYear(year)">
          <option v-for="y in years" :key="y" :value="y">{{ y }}年</option>
        </select>
        <button class="btn-new" @click="newDaily">＋ 新日报</button>
      </div>

      <div class="daily-tree">
        <div v-if="groups.length === 0" class="empty-tip">还没有日报，点「新日报」开始</div>

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
          <span class="date-label">{{ activeDate || '未选择' }}</span>
          <span v-if="isNew" class="tag-new">新建</span>
        </div>
        <div class="editor-actions">
          <span v-if="dirty" class="dirty-hint">未保存</span>
          <button class="btn-save" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>

      <textarea
        v-model="body"
        class="editor-textarea"
        spellcheck="false"
        placeholder="记录今天…"
        @input="dirty = true"
      ></textarea>
    </div>
  </div>
</template>
