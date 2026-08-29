<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createTask,
  deleteTask,
  updateTask,
  type Progress,
  type Task,
} from '@/api/planpool'

const props = defineProps<{ tasks: Task[] }>()
const emit = defineEmits<{ (e: 'changed'): void }>()

const progressOptions: Progress[] = ['完成', '未完成', '进行中', '搁置']
const today = new Date().toISOString().slice(0, 10)

// 高饱和实心 chip 配色
const colors: Record<Progress, { text: string; bg: string }> = {
  完成: { text: '#fff', bg: '#67C23A' },
  未完成: { text: '#fff', bg: '#E0705A' },
  进行中: { text: '#fff', bg: '#4A90D9' },
  搁置: { text: '#fff', bg: '#A0A4A8' },
}

// 列定义（列字母）
const columns = [
  { key: 'level1', label: '一级任务', letter: 'A' },
  { key: 'level2', label: '二级任务', letter: 'B' },
  { key: 'progress', label: '进度', letter: 'C' },
  { key: 'completion', label: '完成度', letter: 'D' },
  { key: 'note', label: '备注', letter: 'E' },
  { key: 'start_date', label: '开始日期', letter: 'F' },
  { key: 'end_date', label: '结束日期', letter: 'G' },
] as const
type ColKey = (typeof columns)[number]['key']
const ACTION_LETTER = 'H'

// 编辑状态：{ id, key }，id=-1 表示新增行
const editing = ref<{ id: number; key: ColKey } | null>(null)
const editValue = ref('')

// 新增行草稿
const draft = reactive({
  level1: '',
  level2: '',
  progress: '未完成' as Progress,
  note: '',
  start_date: '',
  end_date: '',
})

// 一级任务合并：计算 rowspan
interface DisplayRow {
  task: Task
  isFirst: boolean
  rowspan: number
}

const displayRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = []
  let i = 0
  while (i < props.tasks.length) {
    const cur = props.tasks[i]
    let j = i + 1
    while (j < props.tasks.length && props.tasks[j].level1 === cur.level1) j++
    rows.push({ task: cur, isFirst: true, rowspan: j - i })
    for (let k = i + 1; k < j; k++) rows.push({ task: props.tasks[k], isFirst: false, rowspan: 0 })
    i = j
  }
  return rows
})

function isOverdue(t: Task): boolean {
  return !!t.end_date && t.end_date < today && t.display_progress !== '完成' && t.display_progress !== '搁置'
}

function colorOf(p: Progress) {
  return colors[p] ?? colors['未完成']
}

function cellVal(t: Task, key: ColKey): string {
  return String((t as any)[key] ?? '')
}

// ---- 已有任务单元格编辑 ----
function startEdit(t: Task, key: ColKey) {
  editing.value = { id: t.id, key }
  editValue.value = cellVal(t, key)
}

function stopEdit(t: Task) {
  if (!editing.value) return
  const { key } = editing.value
  editing.value = null
  const newVal = editValue.value.trim()
  const oldVal = cellVal(t, key)
  if (newVal === oldVal) return

  const payload: Record<string, string> = {
    level1: t.level1,
    level2: t.level2,
    progress: t.progress,
    note: t.note,
    start_date: t.start_date,
    end_date: t.end_date,
  }
  payload[key] = newVal
  if (!validDates(payload.start_date, payload.end_date)) {
    ElMessage.error('开始日期不能晚于结束日期')
    return
  }
  updateTask(t.id, payload as any)
    .then(() => emit('changed'))
    .catch(() => ElMessage.error('保存失败'))
}

function changeProgress(t: Task, p: Progress) {
  const payload = {
    level1: t.level1,
    level2: t.level2,
    progress: p,
    note: t.note,
    start_date: t.start_date,
    end_date: t.end_date,
  }
  updateTask(t.id, payload)
    .then(() => emit('changed'))
    .catch(() => ElMessage.error('保存失败'))
}

async function onDelete(t: Task) {
  await deleteTask(t.id).catch(() => {})
  ElMessage.success('已删除')
  emit('changed')
}

function validDates(s: string, e: string): boolean {
  return !(s && e && s > e)
}

// ---- 新增行 ----
function isAdding(key: ColKey) {
  return editing.value?.id === -1 && editing.value?.key === key
}

function startAdd(key: ColKey) {
  editing.value = { id: -1, key }
  editValue.value = String((draft as any)[key] ?? '')
}

function commitAdd() {
  const hasContent = draft.level1 || draft.level2 || draft.note || draft.start_date || draft.end_date
  if (!hasContent) return
  if (!validDates(draft.start_date, draft.end_date)) {
    ElMessage.error('开始日期不能晚于结束日期')
    return
  }
  createTask({ ...draft })
    .then(() => {
      ElMessage.success('已添加')
      Object.assign(draft, { level1: '', level2: '', note: '', start_date: '', end_date: '' })
      editing.value = null
      emit('changed')
    })
    .catch(() => ElMessage.error('添加失败'))
}

function onAddInput(key: ColKey) {
  ;(draft as any)[key] = editValue.value.trim()
}
function onAddCommit() {
  commitAdd()
}
function addDisplay(key: ColKey): string {
  const v = String((draft as any)[key] ?? '')
  return v || (key === 'start_date' || key === 'end_date' ? '选择日期' : '点击填写')
}
</script>

<template>
  <div class="pp-excel">
    <table class="pp-table">
      <!-- 列字母行 -->
      <thead>
        <tr class="pp-letter-row">
          <th class="pp-rowhead"></th>
          <th v-for="c in columns" :key="c.key" class="pp-letter">{{ c.letter }}</th>
          <th class="pp-letter">{{ ACTION_LETTER }}</th>
        </tr>
        <tr class="pp-head-row">
          <th class="pp-rowhead"></th>
          <th v-for="c in columns" :key="c.key" class="pp-head">{{ c.label }}</th>
          <th class="pp-head"></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(row, index) in displayRows" :key="row.task.id">
          <tr class="pp-grid-row" :class="{ overdue: isOverdue(row.task) }">
            <td class="pp-rowhead">{{ index + 1 }}</td>

            <!-- 一级任务（合并） -->
            <td
              v-if="row.isFirst"
              class="pp-cell pp-cell-level1"
              :rowspan="row.rowspan"
              @click="startEdit(row.task, 'level1')"
            >
              <template v-if="editing?.id === row.task.id && editing.key === 'level1'">
                <input v-model="editValue" class="pp-input" @blur="stopEdit(row.task)" @keydown.enter="stopEdit(row.task)" />
              </template>
              <template v-else>{{ cellVal(row.task, 'level1') || '—' }}</template>
            </td>

            <!-- 二级任务 -->
            <td class="pp-cell" @click="startEdit(row.task, 'level2')">
              <template v-if="editing?.id === row.task.id && editing.key === 'level2'">
                <input v-model="editValue" class="pp-input" @blur="stopEdit(row.task)" @keydown.enter="stopEdit(row.task)" />
              </template>
              <template v-else>{{ cellVal(row.task, 'level2') || '—' }}</template>
            </td>

            <!-- 进度 -->
            <td class="pp-cell pp-cell-progress">
              <select
                class="pp-select"
                :value="row.task.progress"
                :style="{ background: colorOf(row.task.display_progress).bg }"
                @change="changeProgress(row.task, ($event.target as HTMLSelectElement).value as Progress)"
              >
                <option v-for="p in progressOptions" :key="p" :value="p">{{ p }}</option>
              </select>
            </td>

            <!-- 完成度 -->
            <td class="pp-cell pp-cell-completion">
              <template v-if="row.task.completion !== null">
                <div class="pp-completion">
                  <div class="pp-completion-bar">
                    <div class="pp-completion-fill" :style="{ width: row.task.completion + '%' }"></div>
                  </div>
                  <span class="pp-completion-text">{{ row.task.completion }}%</span>
                </div>
              </template>
              <template v-else>—</template>
            </td>

            <!-- 备注 -->
            <td class="pp-cell" @click="startEdit(row.task, 'note')">
              <template v-if="editing?.id === row.task.id && editing.key === 'note'">
                <input v-model="editValue" class="pp-input" @blur="stopEdit(row.task)" @keydown.enter="stopEdit(row.task)" />
              </template>
              <template v-else>{{ cellVal(row.task, 'note') || '—' }}</template>
            </td>

            <!-- 开始日期 -->
            <td class="pp-cell" @click="startEdit(row.task, 'start_date')">
              <template v-if="editing?.id === row.task.id && editing.key === 'start_date'">
                <input v-model="editValue" type="date" class="pp-input" @blur="stopEdit(row.task)" />
              </template>
              <template v-else>{{ cellVal(row.task, 'start_date') || '—' }}</template>
            </td>

            <!-- 结束日期 -->
            <td class="pp-cell" :class="{ overdue: isOverdue(row.task) }" @click="startEdit(row.task, 'end_date')">
              <template v-if="editing?.id === row.task.id && editing.key === 'end_date'">
                <input v-model="editValue" type="date" class="pp-input" @blur="stopEdit(row.task)" />
              </template>
              <template v-else>{{ cellVal(row.task, 'end_date') || '—' }}</template>
            </td>

            <td class="pp-cell pp-cell-action">
              <button class="pp-del" @click="onDelete(row.task)">✕</button>
            </td>
          </tr>
        </template>

        <!-- 无任务 -->
        <tr v-if="tasks.length === 0">
          <td colspan="9" class="pp-empty">无</td>
        </tr>

        <!-- 新增行 -->
        <tr class="pp-grid-row pp-add-row">
          <td class="pp-rowhead">+</td>
          <td class="pp-cell" @click="startAdd('level1')">
            <template v-if="isAdding('level1')">
              <input v-model="editValue" class="pp-input" @input="onAddInput('level1')" @blur="onAddCommit()" @keydown.enter="onAddCommit()" />
            </template>
            <template v-else>{{ addDisplay('level1') }}</template>
          </td>
          <td class="pp-cell" @click="startAdd('level2')">
            <template v-if="isAdding('level2')">
              <input v-model="editValue" class="pp-input" @input="onAddInput('level2')" @blur="onAddCommit()" @keydown.enter="onAddCommit()" />
            </template>
            <template v-else>{{ addDisplay('level2') }}</template>
          </td>
          <td class="pp-cell pp-cell-progress">
            <select
              class="pp-select"
              v-model="draft.progress"
              :style="{ background: colorOf(draft.progress).bg }"
            >
              <option v-for="p in progressOptions" :key="p" :value="p">{{ p }}</option>
            </select>
          </td>
          <td class="pp-cell pp-cell-completion">—</td>
          <td class="pp-cell" @click="startAdd('note')">
            <template v-if="isAdding('note')">
              <input v-model="editValue" class="pp-input" @input="onAddInput('note')" @blur="onAddCommit()" @keydown.enter="onAddCommit()" />
            </template>
            <template v-else>{{ addDisplay('note') }}</template>
          </td>
          <td class="pp-cell" @click="startAdd('start_date')">
            <template v-if="isAdding('start_date')">
              <input v-model="editValue" type="date" class="pp-input" @input="onAddInput('start_date')" @blur="onAddCommit()" />
            </template>
            <template v-else>{{ addDisplay('start_date') }}</template>
          </td>
          <td class="pp-cell" @click="startAdd('end_date')">
            <template v-if="isAdding('end_date')">
              <input v-model="editValue" type="date" class="pp-input" @input="onAddInput('end_date')" @blur="onAddCommit()" />
            </template>
            <template v-else>{{ addDisplay('end_date') }}</template>
          </td>
          <td class="pp-cell pp-cell-action">
            <button class="pp-del pp-add-ok" @click="onAddCommit()">✓</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
