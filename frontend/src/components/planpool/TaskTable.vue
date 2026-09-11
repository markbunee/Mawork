<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createTask,
  deleteTask,
  updateTask,
  progressOptions,
  type Progress,
  type Task,
} from '@/api/planpool'

const props = defineProps<{ tasks: Task[] }>()
const emit = defineEmits<{ (e: 'changed'): void }>()

// 列定义（Excel 列字母）
const columns = [
  { key: 'level1', label: '一级计划', letter: 'A' },
  { key: 'title', label: '任务', letter: 'B' },
  { key: 'progress', label: '状态', letter: 'C' },
  { key: 'completion', label: '完成度', letter: 'D' },
  { key: 'note', label: '备注', letter: 'E' },
  { key: 'start_date', label: '开始日期', letter: 'F' },
  { key: 'end_date', label: '结束日期', letter: 'G' },
] as const
type ColKey = (typeof columns)[number]['key']
const ACTION_LETTER = 'H'

const editing = ref<{ id: number; key: ColKey } | null>(null)
const editValue = ref('')

const draft = reactive({
  level1: '',
  title: '',
  progress: '未完成' as Progress,
  completion: 0,
  note: '',
  start_date: '',
  end_date: '',
})

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

function clampCompletion(v: number): number {
  if (Number.isNaN(v)) return 0
  return Math.max(0, Math.min(100, Math.round(v)))
}

function validDates(s: string, e: string): boolean {
  return !(s && e && s > e)
}

// ---------------------------------------------------------------------------
// 单元格编辑
// ---------------------------------------------------------------------------
function cellVal(t: Task, key: ColKey): string {
  const v = (t as unknown as Record<string, unknown>)[key]
  return v === null || v === undefined ? '' : String(v)
}

function startEdit(t: Task, key: ColKey) {
  if (key === 'progress') return
  editing.value = { id: t.id, key }
  editValue.value = cellVal(t, key)
}

function stopEdit(t: Task) {
  if (!editing.value) return
  const { key } = editing.value
  editing.value = null
  const raw = editValue.value.trim()
  const old = cellVal(t, key)
  if (raw === old) return

  const payload = payloadOf(t)
  if (key === 'completion') {
    payload.completion = clampCompletion(Number(raw))
  } else {
    ;(payload as unknown as Record<string, string>)[key] = raw
  }
  if (!validDates(payload.start_date, payload.end_date)) {
    ElMessage.error('开始日期不能晚于结束日期')
    return
  }
  updateTask(t.id, payload)
    .then(() => emit('changed'))
    .catch(() => ElMessage.error('保存失败'))
}

function changeProgress(t: Task, p: Progress) {
  updateTask(t.id, { ...payloadOf(t), progress: p })
    .then(() => emit('changed'))
    .catch(() => ElMessage.error('保存失败'))
}

async function onDelete(t: Task) {
  await deleteTask(t.id).catch(() => {})
  ElMessage.success('已删除')
  emit('changed')
}

// ---------------------------------------------------------------------------
// 新增行
// ---------------------------------------------------------------------------
function isAdding(key: ColKey) {
  return editing.value?.id === -1 && editing.value?.key === key
}
function startAdd(key: ColKey) {
  editing.value = { id: -1, key }
  editValue.value = String((draft as unknown as Record<string, unknown>)[key] ?? '')
}
function onAddInput(key: ColKey) {
  ;(draft as unknown as Record<string, unknown>)[key] =
    key === 'completion' ? clampCompletion(Number(editValue.value)) : editValue.value.trim()
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
      editing.value = null
      emit('changed')
    })
    .catch(() => ElMessage.error('添加失败'))
}
function addDisplay(key: ColKey): string {
  const v = String((draft as unknown as Record<string, unknown>)[key] ?? '')
  if (v) return v
  return key === 'start_date' || key === 'end_date' ? '选择日期' : '点击填写'
}

// ---------------------------------------------------------------------------
// 备注详情面板：单击备注列 → 右侧抽屉，可查看 / 编辑大篇幅备注（计划文本）
// ---------------------------------------------------------------------------
const noteTarget = ref<Task | null>(null)
const noteDraft = ref('')
const noteArea = ref<HTMLTextAreaElement | null>(null)

function noteFirstLine(note: string): string {
  const first = (note || '').trim().split('\n')[0]
  if (!first) return '—'
  return first.length > 46 ? first.slice(0, 46) + '…' : first
}

function openNote(t: Task) {
  // 若表格正处于行内编辑，先让其失焦提交，避免与面板同时操作
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
  // 改动自动保存，保存成功才关闭（失败保留编辑内容）
  updateTask(t.id, { ...payloadOf(t), note: raw })
    .then(() => {
      noteTarget.value = null
      emit('changed')
    })
    .catch(() => ElMessage.error('备注保存失败'))
}

const rowCount = computed(() => props.tasks.length + 1)
</script>

<template>
  <div class="pp-excel">
    <table class="pp-table">
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
        <tr v-for="(t, index) in tasks" :key="t.id" class="pp-grid-row">
          <td class="pp-rowhead">{{ index + 1 }}</td>

          <td class="pp-cell pp-cell-level1" @click="startEdit(t, 'level1')">
            <input
              v-if="editing?.id === t.id && editing.key === 'level1'"
              v-model="editValue"
              class="pp-input"
              @blur="stopEdit(t)"
              @keydown.enter="stopEdit(t)"
            />
            <template v-else>{{ t.level1 || '—' }}</template>
          </td>

          <td class="pp-cell" @click="startEdit(t, 'title')">
            <input
              v-if="editing?.id === t.id && editing.key === 'title'"
              v-model="editValue"
              class="pp-input"
              @blur="stopEdit(t)"
              @keydown.enter="stopEdit(t)"
            />
            <template v-else>{{ t.title || '—' }}</template>
          </td>

          <td class="pp-cell pp-cell-progress">
            <select
              class="pp-select"
              :value="t.progress"
              @change="changeProgress(t, ($event.target as HTMLSelectElement).value as Progress)"
            >
              <option v-for="p in progressOptions" :key="p" :value="p">{{ p }}</option>
            </select>
          </td>

          <td class="pp-cell pp-cell-completion" @click="startEdit(t, 'completion')">
            <input
              v-if="editing?.id === t.id && editing.key === 'completion'"
              v-model="editValue"
              type="number"
              min="0"
              max="100"
              class="pp-input pp-input-num"
              @blur="stopEdit(t)"
              @keydown.enter="stopEdit(t)"
            />
            <div v-else class="pp-completion">
              <div class="pp-completion-bar">
                <div class="pp-completion-fill" :style="{ width: t.completion + '%' }"></div>
              </div>
              <span class="pp-completion-text">{{ t.completion }}%</span>
            </div>
          </td>

          <td
            class="pp-cell pp-cell-note"
            :class="{ 'has-note': !!t.note }"
            title="单击查看 / 编辑备注"
            @click="openNote(t)"
          >
            <template v-if="t.note">
              <span class="pp-note-dot"></span>{{ noteFirstLine(t.note) }}
            </template>
            <template v-else>—</template>
          </td>

          <td class="pp-cell" @click="startEdit(t, 'start_date')">
            <input
              v-if="editing?.id === t.id && editing.key === 'start_date'"
              v-model="editValue"
              type="date"
              class="pp-input"
              @blur="stopEdit(t)"
            />
            <template v-else>{{ t.start_date || '—' }}</template>
          </td>

          <td class="pp-cell" @click="startEdit(t, 'end_date')">
            <input
              v-if="editing?.id === t.id && editing.key === 'end_date'"
              v-model="editValue"
              type="date"
              class="pp-input"
              @blur="stopEdit(t)"
            />
            <template v-else>{{ t.end_date || '—' }}</template>
          </td>

          <td class="pp-cell pp-cell-action">
            <button class="pp-del" title="删除" @click="onDelete(t)">✕</button>
          </td>
        </tr>

        <tr v-if="tasks.length === 0">
          <td :colspan="columns.length + 2" class="pp-empty">本月还没有任务，从下面一行开始填</td>
        </tr>

        <!-- 新增行 -->
        <tr class="pp-grid-row pp-add-row">
          <td class="pp-rowhead">{{ rowCount }}</td>
          <td class="pp-cell pp-cell-level1" @click="startAdd('level1')">
            <input
              v-if="isAdding('level1')"
              v-model="editValue"
              class="pp-input"
              @input="onAddInput('level1')"
              @blur="commitAdd()"
              @keydown.enter="commitAdd()"
            />
            <template v-else>{{ addDisplay('level1') }}</template>
          </td>
          <td class="pp-cell" @click="startAdd('title')">
            <input
              v-if="isAdding('title')"
              v-model="editValue"
              class="pp-input"
              @input="onAddInput('title')"
              @blur="commitAdd()"
              @keydown.enter="commitAdd()"
            />
            <template v-else>{{ addDisplay('title') }}</template>
          </td>
          <td class="pp-cell pp-cell-progress">
            <select class="pp-select" v-model="draft.progress">
              <option v-for="p in progressOptions" :key="p" :value="p">{{ p }}</option>
            </select>
          </td>
          <td class="pp-cell pp-cell-completion" @click="startAdd('completion')">
            <input
              v-if="isAdding('completion')"
              v-model="editValue"
              type="number"
              min="0"
              max="100"
              class="pp-input pp-input-num"
              @input="onAddInput('completion')"
              @blur="commitAdd()"
              @keydown.enter="commitAdd()"
            />
            <template v-else>0%</template>
          </td>
          <td class="pp-cell" @click="startAdd('note')">
            <input
              v-if="isAdding('note')"
              v-model="editValue"
              class="pp-input"
              @input="onAddInput('note')"
              @blur="commitAdd()"
              @keydown.enter="commitAdd()"
            />
            <template v-else>{{ addDisplay('note') }}</template>
          </td>
          <td class="pp-cell" @click="startAdd('start_date')">
            <input
              v-if="isAdding('start_date')"
              v-model="editValue"
              type="date"
              class="pp-input"
              @input="onAddInput('start_date')"
              @blur="commitAdd()"
            />
            <template v-else>{{ addDisplay('start_date') }}</template>
          </td>
          <td class="pp-cell" @click="startAdd('end_date')">
            <input
              v-if="isAdding('end_date')"
              v-model="editValue"
              type="date"
              class="pp-input"
              @input="onAddInput('end_date')"
              @blur="commitAdd()"
            />
            <template v-else>{{ addDisplay('end_date') }}</template>
          </td>
          <td class="pp-cell pp-cell-action">
            <button class="pp-del pp-add-ok" title="新增" @click="commitAdd()">✓</button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 备注详情抽屉：查看完整内容并可编辑（大篇幅计划文本） -->
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
