<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  addColumn,
  applyColumnsJson,
  applyTemplate,
  deleteColumn,
  listTemplates,
  setColumnsOrder,
  updateColumn,
  type Column,
  type ColumnType,
  type Template,
} from '@/api/planpool'
import TemplatePicker from '@/components/TemplatePicker.vue'

const props = defineProps<{ columns: Column[] }>()
const emit = defineEmits<{ (e: 'updated'): void; (e: 'close'): void }>()

const FTYPES: { value: ColumnType; label: string }[] = [
  { value: 'text', label: '文本' },
  { value: 'date', label: '日期' },
  { value: 'number', label: '数字' },
  { value: 'select', label: '下拉' },
  { value: 'check', label: '勾选' },
]

const templates = ref<Template[]>([])
const showAdd = ref(false)
const newLabel = ref('')
const newType = ref<ColumnType>('text')
const newOptions = ref('')

const dragId = ref<number | null>(null)

onMounted(async () => {
  try {
    templates.value = await listTemplates()
  } catch {
    /* 忽略 */
  }
})

async function reload() {
  emit('updated')
}

function optionsText(c: Column): string {
  return c.options.join('，')
}

async function toggleVisible(c: Column) {
  await updateColumn(c.id, { visible: !c.visible })
  reload()
}

async function rename(c: Column, label: string) {
  if (!label.trim() || label === c.label) return
  await updateColumn(c.id, { label: label.trim() })
  reload()
}

async function changeType(c: Column, ftype: ColumnType) {
  const patch: { ftype: ColumnType; options?: string[] } = { ftype }
  if (ftype === 'select' && c.options.length === 0) patch.options = ['选项1', '选项2']
  await updateColumn(c.id, patch)
  reload()
}

async function changeOptions(c: Column, text: string) {
  const opts = text.split(/[，,]/).map((s) => s.trim()).filter(Boolean)
  await updateColumn(c.id, { options: opts })
  reload()
}

async function remove(c: Column) {
  await deleteColumn(c.id)
  ElMessage.success('已删除列')
  reload()
}

async function doAdd() {
  if (!newLabel.value.trim()) return
  const opts = newType.value === 'select' ? newOptions.value.split(/[，,]/).map((s) => s.trim()).filter(Boolean) : []
  await addColumn(newLabel.value.trim(), newType.value, opts)
  newLabel.value = ''
  newOptions.value = ''
  showAdd.value = false
  ElMessage.success('已新增列')
  reload()
}

// 拖拽重排
function onDragStart(id: number) {
  dragId.value = id
}
function onDrop(targetId: number) {
  if (dragId.value == null || dragId.value === targetId) return
  const ids = props.columns.map((c) => c.id)
  const from = ids.indexOf(dragId.value)
  const to = ids.indexOf(targetId)
  ids.splice(to, 0, ids.splice(from, 1)[0])
  dragId.value = null
  setColumnsOrder(ids).then(reload).catch(() => ElMessage.error('排序失败'))
}

async function doApply(name: string) {
  await applyTemplate(name)
  ElMessage.success(`已套用模板「${name}」`)
  reload()
}

// 统一模板库（横切能力 E3）：任务表模板走统一库，可自建
const tplOpen = ref(false)
async function onApplyLibraryTpl(item: { name: string; content: string }) {
  let cols: { label: string; ftype: ColumnType; options: string[] }[] = []
  try {
    cols = JSON.parse(item.content || '[]')
  } catch {
    ElMessage.error('模板内容不是合法的列定义')
    return
  }
  await applyColumnsJson(cols)
  ElMessage.success(`已套用模板「${item.name}」`)
  reload()
}
</script>

<template>
  <div class="pp-cm-overlay" @click.self="emit('close')">
    <div class="pp-cm-drawer" role="dialog" aria-label="列管理">
      <div class="pp-cm-head">
        <div class="pp-cm-title">列管理</div>
        <button class="pp-note-close" @click="emit('close')">✕</button>
      </div>

      <div class="pp-cm-sec">
        <div class="pp-cm-seclabel">
          预设模板
          <button class="pp-cm-addbtn" @click="tplOpen = true">模板库…</button>
        </div>
        <div class="pp-cm-tpls">
          <button v-for="t in templates" :key="t.id" class="pp-cm-tpl" @click="doApply(t.name)">{{ t.name }}</button>
        </div>
      </div>

      <div class="pp-cm-sec">
        <div class="pp-cm-seclabel">
          列（拖拽排序 · 内置列不可删除）
          <button class="pp-cm-addbtn" @click="showAdd = !showAdd">{{ showAdd ? '收起' : '+ 新增列' }}</button>
        </div>

        <div v-if="showAdd" class="pp-cm-add">
          <input v-model="newLabel" class="pp-cm-input" placeholder="列名" @keydown.enter="doAdd" />
          <select v-model="newType" class="pp-cm-input">
            <option v-for="f in FTYPES" :key="f.value" :value="f.value">{{ f.label }}</option>
          </select>
          <input
            v-if="newType === 'select'"
            v-model="newOptions"
            class="pp-cm-input"
            placeholder="选项，用逗号分隔"
          />
          <button class="pp-cm-addok" @click="doAdd">添加</button>
        </div>

        <ul class="pp-cm-list">
          <li
            v-for="c in columns"
            :key="c.id"
            class="pp-cm-item"
            :class="{ pinned: c.pinned }"
            draggable="true"
            @dragstart="onDragStart(c.id)"
            @dragover.prevent
            @drop="onDrop(c.id)"
          >
            <span class="pp-cm-grip">⠿</span>
            <input
              class="pp-cm-label"
              :value="c.label"
              @change="rename(c, ($event.target as HTMLInputElement).value)"
            />
            <select
              v-if="!c.builtin"
              class="pp-cm-type"
              :value="c.ftype"
              @change="changeType(c, ($event.target as HTMLSelectElement).value as ColumnType)"
            >
              <option v-for="f in FTYPES" :key="f.value" :value="f.value">{{ f.label }}</option>
            </select>
            <input
              v-if="!c.builtin && c.ftype === 'select'"
              class="pp-cm-opts"
              :value="optionsText(c)"
              @change="changeOptions(c, ($event.target as HTMLInputElement).value)"
            />
            <label class="pp-cm-vis">
              <input type="checkbox" :checked="c.visible" @change="toggleVisible(c)" /> 显示
            </label>
            <button v-if="!c.builtin" class="pp-cm-del" @click="remove(c)">删</button>
            <span v-else class="pp-cm-built">内置</span>
          </li>
        </ul>
      </div>
    </div>

    <!-- 统一模板库（横切能力 E3）：任务表列预设 -->
    <TemplatePicker
      :open="tplOpen"
      scope="task"
      title="任务表模板库"
      @close="tplOpen = false"
      @apply="onApplyLibraryTpl"
    />
  </div>
</template>
