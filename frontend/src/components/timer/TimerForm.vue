<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createTimer,
  updateTimer,
  type Meta,
  type Timer,
  type TimerIn,
  type TimerType,
} from '@/api/timer'

const props = defineProps<{
  editing: Timer | null
  meta: Meta | null
}>()
const show = defineModel<boolean>({ required: true })
const emit = defineEmits<{ (e: 'saved'): void }>()

const form = ref<TimerIn>({
  type: 'countup',
  title: '',
  note: '',
  target_at: '',
  start_at: '',
  status: 'active',
})

const typeOptions = computed(() => {
  const labels = (props.meta?.type_labels ?? {}) as Record<string, string>
  return (props.meta?.types ?? ['countup']).map((t) => ({
    value: t as TimerType,
    label: labels[t as TimerType] ?? t,
  }))
})

const needsTarget = computed(
  () => form.value.type === 'countdown' || form.value.type === 'countdown_days',
)
const needsStart = computed(
  () => form.value.type === 'countup' || form.value.type === 'countup_days',
)

// 存储格式 <-> 输入控件格式互转
function toInput(type: TimerType, val: string): string {
  if (!val) return ''
  if (type === 'countdown' || type === 'countup') {
    // 2026-09-11 14:30:00 -> 2026-09-11T14:30
    return val.replace(' ', 'T').slice(0, 16)
  }
  return val.slice(0, 10) // 日期
}
function toStorage(type: TimerType, val: string): string {
  if (!val) return ''
  if (type === 'countdown' || type === 'countup') {
    const s = val.replace('T', ' ')
    return s.length === 16 ? `${s}:00` : s
  }
  return val.slice(0, 10) // 日期
}

watch(show, (v) => {
  if (!v) return
  const t = props.editing
  if (t) {
    form.value = {
      type: t.type,
      title: t.title,
      note: t.note,
      target_at: toInput(t.type, t.target_at),
      start_at: toInput(t.type, t.start_at),
      status: t.status,
    }
  } else {
    form.value = { type: 'countup', title: '', note: '', target_at: '', start_at: '', status: 'active' }
  }
})

// 切换类型时清空日期字段（避免 datetime-local 与 date 控件格式不一致）。
// 注意：只在「用户主动改类型」时清空，编辑已有计时器时由 watch(show) 回填，
// 不能用 watch(type) 清空——否则编辑打开时会把已有 target/start 误清空。
function onTypeChange() {
  form.value.target_at = ''
  form.value.start_at = ''
}

async function submit() {
  try {
    const type = form.value.type
    const payload: TimerIn = {
      type,
      title: form.value.title,
      note: form.value.note,
      target_at: needsTarget.value ? toStorage(type, form.value.target_at ?? '') : '',
      start_at: needsStart.value ? toStorage(type, form.value.start_at ?? '') : '',
      status: form.value.status,
    }
    if (props.editing) await updateTimer(props.editing.id, payload)
    else await createTimer(payload)
    ElMessage.success('已保存')
    show.value = false
    emit('saved')
  } catch {
    ElMessage.error('保存失败')
  }
}
</script>

<template>
  <el-dialog
    v-model="show"
    :title="editing ? '编辑计时器' : '新建计时器'"
    width="460px"
  >
    <div class="tm-form">
      <label class="tm-field">
        <span class="tm-label">类型</span>
        <select v-model="form.type" class="field" @change="onTypeChange">
          <option v-for="o in typeOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>

      <label class="tm-field">
        <span class="tm-label">计划 / 任务名</span>
        <input v-model="form.title" class="field" placeholder="例如：写周报" />
      </label>

      <label class="tm-field">
        <span class="tm-label">备注</span>
        <textarea v-model="form.note" class="field" rows="2" placeholder="可选" />
      </label>

      <label v-if="needsTarget" class="tm-field">
        <span class="tm-label">{{ form.type === 'countdown' ? '目标时刻' : '目标日期' }}</span>
        <input
          v-model="form.target_at"
          class="field"
          :type="form.type === 'countdown' ? 'datetime-local' : 'date'"
        />
      </label>

      <label v-if="needsStart" class="tm-field">
        <span class="tm-label">{{ form.type === 'countup' ? '起始时刻' : '起始日期' }}</span>
        <input
          v-model="form.start_at"
          class="field"
          :type="form.type === 'countup' ? 'datetime-local' : 'date'"
        />
      </label>
    </div>

    <template #footer>
      <button class="tm-btn" @click="show = false">取消</button>
      <button class="tm-btn primary" @click="submit">保存</button>
    </template>
  </el-dialog>
</template>
