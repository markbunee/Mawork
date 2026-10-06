<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  createTask,
  deleteTask,
  updateTask,
  upsertCells,
  progressOptions,
  type Column,
  type Progress,
  type Task,
} from '@/api/planpool'
import { createTimer, startTimer } from '@/api/timer'

const props = defineProps<{
  tasks: Task[]
  columns: Column[]
  groupBy: 'level1' | null
  sortKey: string | null
  sortDir: 'asc' | 'desc'
}>()
const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'sort', key: string): void
}>()

const BUILTIN_KEYS = new Set(['level1', 'title', 'progress', 'completion', 'note', 'start_date', 'end_date'])

// 可见列按 position 排序，pinned 的列排在最前
const visibleCols = computed(() => {
  const vs = props.columns.filter((c) => c.visible).slice()
  return vs.sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    return a.position - b.position
  })
})

// Excel 列字母 A, B, ..., Z, AA ...
function colLetter(i: number): string {
  let s = ''
  let n = i
  do {
    s = String.fromCharCode(65 + (n % 26)) + s
    n = Math.floor(n / 26) - 1
  } while (n >= 0)
  return s
}

const ACTION_LABEL = '操作'

// 分组（按一级计划）
const groups = computed(() => {
  if (!props.groupBy) return [{ key: '__all', label: '', items: props.tasks }]
  const map = new Map<string, Task[]>()
  for (const t of props.tasks) {
    const k = t.level1 || '未分类'
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(t)
  }
  return Array.from(map.entries()).map(([k, items]) => ({ key: k, label: k, items }))
})
const collapsed = ref<Set<string>>(new Set())
function toggleGroup(key: string) {
  const s = new Set(collapsed.value)
  s.has(key) ? s.delete(key) : s.add(key)
  collapsed.value = s
}

// ---------------------------------------------------------------------------
// 单元格取值与编辑
// ---------------------------------------------------------------------------
function cellValue(t: Task, col: Column): string {
  if (BUILTIN_KEYS.has(col.key)) {
    const v = (t as unknown as Record<string, unknown>)[col.key]
    return v == null ? '' : String(v)
  }
  return t.fields?.[col.key] ?? ''
}

function isChecked(t: Task, col: Column): boolean {
  const v = cellValue(t, col)
  return v === '1' || v === 'true' || v === '✓'
}

const editing = ref<{ id: number; key: string } | null>(null)
const editValue = ref('')

function startEdit(t: Task, col: Column) {
  if (col.ftype === 'check' || col.ftype === 'select' || col.key === 'note' || col.key === 'progress') return
  editing.value = { id: t.id, key: col.key }
  editValue.value = cellValue(t, col)
  nextTick(() => {
    const el = document.querySelector<HTMLInputElement>('.pp-input.is-editing')
    el?.focus()
  })
}

function payloadOf(t: Task) {
  return {
    level1: t.level1,
    title: t.title,
    progress: t.progress,
    completion: t.completion,
    note: t.note,
    start_date: t.start_date,
    end_date: t.end_date,
  }
}

function clamp(n: number): number {
  if (Number.isNaN(n)) return 0
  return Math.max(0, Math.min(100, Math.round(n)))
}

function stopEdit(t: Task, col: Column) {
  if (!editing.value) return
  editing.value = null
  const raw = editValue.value.trim()
  const old = cellValue(t, col)
  if (raw === old) return
  if (BUILTIN_KEYS.has(col.key)) {
    const payload = payloadOf(t)
    if (col.key === 'completion') {
      ;(payload as Record<string, unknown>)['completion'] = clamp(Number(raw))
    } else {
      ;(payload as Record<string, unknown>)[col.key] = raw
    }
    if (!validDates((payload as unknown as Record<string, string>).start_date, (payload as unknown as Record<string, string>).end_date)) {
      ElMessage.error('开始日期不能晚于结束日期')
      return
    }
    updateTask(t.id, payload).then(() => emit('changed')).catch(() => ElMessage.error('保存失败'))
  } else {
    upsertCells(t.id, { [col.key]: raw }).then(() => emit('changed')).catch(() => ElMessage.error('保存失败'))
  }
}

function changeProgress(t: Task, p: Progress) {
  updateTask(t.id, { ...payloadOf(t), progress: p }).then(() => emit('changed')).catch(() => ElMessage.error('保存失败'))
}

function toggleCheck(t: Task, col: Column) {
  const next = !isChecked(t, col)
  upsertCells(t.id, { [col.key]: next }).then(() => emit('changed')).catch(() => ElMessage.error('保存失败'))
}

function changeSelect(t: Task, col: Column, val: string) {
  if (BUILTIN_KEYS.has(col.key)) {
    changeProgress(t, val as Progress)
    return
  }
  upsertCells(t.id, { [col.key]: val }).then(() => emit('changed')).catch(() => ElMessage.error('保存失败'))
}

function validDates(s: string, e: string): boolean {
  return !(s && e && s > e)
}

async function onDelete(t: Task) {
  await deleteTask(t.id).catch(() => {})
  ElMessage.success('已删除')
  emit('changed')
}

// 日程联动计时（横切能力 E2）：从任务一键创建并开始正计时
const router = useRouter()
async function startTimerFor(t: Task) {
  try {
    const timer = await createTimer({
      type: 'countup',
      title: t.title || '未命名任务',
      note: t.level1,
      source_type: 'planpool',
      source_ref: String(t.id),
    })
    if (timer && timer.id) {
      await startTimer(timer.id).catch(() => {})
    }
    ElMessage.success('已创建计时，去「计时」页开始')
    router.push('/timer')
  } catch {
    ElMessage.error('创建计时失败')
  }
}

function sortBy(col: Column) {
  if (col.key === 'note' || col.key === 'progress') return
  emit('sort', col.key)
}

// ---------------------------------------------------------------------------
// 新增行（核心字段）
// ---------------------------------------------------------------------------
const draft = reactive({
  level1: '',
  title: '',
  progress: '未完成' as Progress,
  completion: 0,
  note: '',
  start_date: '',
  end_date: '',
})
const addingKey = ref<string | null>(null)
const addValue = ref('')

function isAdding(key: string) {
  return addingKey.value === key
}
function startAdd(key: string) {
  addingKey.value = key
  addValue.value = String((draft as unknown as Record<string, unknown>)[key] ?? '')
}
function onAddInput(key: string) {
  ;(draft as unknown as Record<string, unknown>)[key] =
    key === 'completion' ? clamp(Number(addValue.value)) : addValue.value.trim()
}
function addDisplay(key: string): string {
  const v = String((draft as unknown as Record<string, unknown>)[key] ?? '')
  if (v) return v
  if (key === 'progress') return draft.progress
  if (key === 'completion') return '0%'
  return key === 'start_date' || key === 'end_date' ? '选择日期' : '点击填写'
}
function commitAdd() {
  if (!draft.level1 && !draft.title && !draft.note && !draft.start_date && !draft.end_date) return
  if (!validDates(draft.start_date, draft.end_date)) {
    ElMessage.error('开始日期不能晚于结束日期')
    return
  }
  createTask({ ...draft })
    .then(() => {
      ElMessage.success('已添加')
      Object.assign(draft, {
        level1: '',
        title: '',
        progress: '未完成' as Progress,
        completion: 0,
        note: '',
        start_date: '',
        end_date: '',
      })
      addingKey.value = null
      emit('changed')
    })
    .catch(() => ElMessage.error('添加失败'))
}

// ---------------------------------------------------------------------------
// 备注抽屉
// ---------------------------------------------------------------------------
const noteTarget = ref<Task | null>(null)
const noteDraft = ref('')
const noteArea = ref<HTMLTextAreaElement | null>(null)
function noteFirstLine(note: string): string {
  const first = (note || '').trim().split('\n')[0]
  return !first ? '' : first.length > 46 ? first.slice(0, 46) + '…' : first
}
function openNote(t: Task) {
  if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
  editing.value = null
  noteTarget.value = t
  noteDraft.value = t.note ?? ''
  nextTick(() => {
    noteArea.value?.focus()
    const len = noteDraft.value.length
    noteArea.value?.setSelectionRange(len, len)
  })
}
function closeNote() {
  const t = noteTarget.value
  if (!t) return
  const raw = noteDraft.value.trim()
  if (raw === (t.note ?? '')) {
    noteTarget.value = null
    return
  }
  updateTask(t.id, { ...payloadOf(t), note: raw })
    .then(() => {
      noteTarget.value = null
      emit('changed')
    })
    .catch(() => ElMessage.error('备注保存失败'))
}

const rowCount = computed(() => props.tasks.length + 1)

function sortIndicator(col: Column): string {
  if (props.sortKey !== col.key) return ''
  return props.sortDir === 'asc' ? ' ▲' : ' ▼'
}
</script>

<template>
  <div class="pp-excel">
    <table class="pp-table">
      <thead>
        <tr class="pp-letter-row">
          <th class="pp-rowhead"></th>
          <th v-for="(c, i) in visibleCols" :key="c.id" class="pp-letter">{{ colLetter(i) }}</th>
          <th class="pp-letter">{{ colLetter(visibleCols.length) }}</th>
        </tr>
        <tr class="pp-head-row">
          <th class="pp-rowhead"></th>
          <th
            v-for="c in visibleCols"
            :key="c.id"
            class="pp-head"
            :class="{ sortable: c.key !== 'note' && c.key !== 'progress' }"
            @click="sortBy(c)"
          >
            {{ c.label }}<span class="pp-sort">{{ sortIndicator(c) }}</span>
          </th>
          <th class="pp-head"></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="g in groups" :key="g.key">
          <tr v-if="groupBy" class="pp-group-row" @click="toggleGroup(g.key)">
            <td :colspan="visibleCols.length + 2" class="pp-group-cell">
              <span class="pp-group-caret">{{ collapsed.has(g.key) ? '▸' : '▾' }}</span>
              {{ g.label || '未分类' }}
              <span class="pp-group-count">{{ g.items.length }}</span>
            </td>
          </tr>
          <template v-if="!collapsed.has(g.key)">
            <tr v-for="(t, index) in g.items" :key="t.id" class="pp-grid-row">
              <td class="pp-rowhead">{{ index + 1 }}</td>

              <td
                v-for="c in visibleCols"
                :key="c.id"
                class="pp-cell"
                :class="{ 'pp-cell-level1': c.key === 'level1', 'pp-cell-note': c.key === 'note', 'pp-cell-progress': c.key === 'progress' || c.ftype === 'select', 'pp-cell-check': c.ftype === 'check', 'has-note': c.key === 'note' && !!t.note }"
                @click="c.key === 'note' ? openNote(t) : startEdit(t, c)"
              >
                <!-- 编辑中：文本/数字/日期 -->
                <input
                  v-if="editing?.id === t.id && editing.key === c.key && (c.ftype === 'text' || c.ftype === 'date' || c.ftype === 'number')"
                  v-model="editValue"
                  class="pp-input is-editing"
                  :type="c.ftype === 'date' ? 'date' : c.ftype === 'number' ? 'number' : 'text'"
                  :min="c.ftype === 'number' ? 0 : undefined"
                  :max="c.ftype === 'number' ? 100 : undefined"
                  @blur="stopEdit(t, c)"
                  @keydown.enter="stopEdit(t, c)"
                />
                <!-- 完成度（内置）：进度条 + 点击编辑数字 -->
                <template v-else-if="c.key === 'completion'">
                  <input
                    v-if="editing?.id === t.id && editing.key === 'completion'"
                    v-model="editValue"
                    type="number"
                    min="0"
                    max="100"
                    class="pp-input pp-input-num is-editing"
                    @blur="stopEdit(t, c)"
                    @keydown.enter="stopEdit(t, c)"
                  />
                  <div v-else class="pp-completion">
                    <div class="pp-completion-bar">
                      <div class="pp-completion-fill" :style="{ width: t.completion + '%' }"></div>
                    </div>
                    <span class="pp-completion-text">{{ t.completion }}%</span>
                  </div>
                </template>
                <!-- 状态下拉 -->
                <select
                  v-else-if="c.key === 'progress'"
                  class="pp-select"
                  :value="t.progress"
                  @change="changeProgress(t, ($event.target as HTMLSelectElement).value as Progress)"
                >
                  <option v-for="p in progressOptions" :key="p" :value="p">{{ p }}</option>
                </select>
                <!-- 自定义下拉 -->
                <select
                  v-else-if="c.ftype === 'select'"
                  class="pp-select"
                  :value="cellValue(t, c)"
                  @change="changeSelect(t, c, ($event.target as HTMLSelectElement).value)"
                >
                  <option value=""></option>
                  <option v-for="o in c.options" :key="o" :value="o">{{ o }}</option>
                </select>
                <!-- 勾选 -->
                <input
                  v-else-if="c.ftype === 'check'"
                  type="checkbox"
                  class="pp-check"
                  :checked="isChecked(t, c)"
                  @change="toggleCheck(t, c)"
                />
                <!-- 备注 -->
                <template v-else-if="c.key === 'note'">
                  <span v-if="t.note"><span class="pp-note-dot"></span>{{ noteFirstLine(t.note) }}</span>
                  <span v-else></span>
                </template>
                <!-- 文本/数字/日期 展示 -->
                <template v-else>{{ cellValue(t, c) }}</template>
              </td>

              <td class="pp-cell pp-cell-action">
                <button class="pp-timer" title="开始计时" @click="startTimerFor(t)">⏱</button>
                <button class="pp-del" title="删除" @click="onDelete(t)">✕</button>
              </td>
            </tr>
          </template>
        </template>

        <tr v-if="tasks.length === 0">
          <td :colspan="visibleCols.length + 2" class="pp-empty">本月还没有任务，从下面一行开始填</td>
        </tr>

        <!-- 新增行 -->
        <tr class="pp-grid-row pp-add-row">
          <td class="pp-rowhead">{{ rowCount }}</td>
          <td
            v-for="c in visibleCols"
            :key="'add-' + c.id"
            class="pp-cell"
            :class="{ 'pp-cell-level1': c.key === 'level1', 'pp-cell-progress': c.key === 'progress' || c.ftype === 'select', 'pp-cell-check': c.ftype === 'check' }"
            @click="(c.key === 'progress' || c.ftype === 'select' || c.ftype === 'check') ? null : startAdd(c.key === 'note' ? 'note' : c.key)"
          >
            <select
              v-if="c.key === 'progress'"
              class="pp-select"
              v-model="draft.progress"
            >
              <option v-for="p in progressOptions" :key="p" :value="p">{{ p }}</option>
            </select>
            <input
              v-else-if="isAdding(c.key)"
              v-model="addValue"
              class="pp-input is-editing"
              :type="c.ftype === 'date' ? 'date' : c.ftype === 'number' ? 'number' : 'text'"
              @input="onAddInput(c.key)"
              @blur="commitAdd()"
              @keydown.enter="commitAdd()"
            />
            <template v-else-if="c.ftype === 'select'"></template>
            <template v-else-if="c.ftype === 'check'"></template>
            <template v-else>{{ addDisplay(c.key) }}</template>
          </td>
          <td class="pp-cell pp-cell-action">
            <button class="pp-del pp-add-ok" title="新增" @click="commitAdd()">✓</button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 备注抽屉 -->
    <div v-if="noteTarget" class="pp-note-overlay" @click.self="closeNote()">
      <div class="pp-note-drawer" role="dialog" aria-label="备注详情">
        <div class="pp-note-head">
          <div class="pp-note-head-main">
            <div class="pp-note-title">{{ noteTarget.title || '未命名任务' }}</div>
            <div class="pp-note-meta">
              {{ noteTarget.progress }} · 完成度 {{ noteTarget.completion }}% ·
              {{ noteTarget.start_date || '?' }} ~ {{ noteTarget.end_date || '?' }}
            </div>
          </div>
          <button class="pp-note-close" title="关闭（自动保存）" @click="closeNote()">✕</button>
        </div>
        <div class="pp-note-body">
          <div class="pp-note-label">
            <span>备注</span>
            <span>支持多行，改动自动保存</span>
          </div>
          <textarea
            ref="noteArea"
            v-model="noteDraft"
            class="pp-note-textarea"
            placeholder="写下任务备注：背景、计划步骤、里程碑、参考链接…"
            spellcheck="false"
            @keydown.esc.prevent="closeNote()"
          ></textarea>
        </div>
        <div class="pp-note-foot">
          <span class="pp-note-hint">Esc / 点击外部 / ✕ 关闭，改动即保存</span>
          <button class="pp-note-save" @click="closeNote()">保存并关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>
