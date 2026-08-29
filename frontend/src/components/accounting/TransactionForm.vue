<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getMeta, createTransaction, type Kind, type Transaction } from '@/api/accounting'

const emit = defineEmits<{ (e: 'saved', tx: Transaction): void }>()

const kinds = ref<{ value: Kind; label: string; categories: string[] }[]>([])
const loadingMeta = ref(false)
const saving = ref(false)

const form = reactive({
  kind: 'expense' as Kind,
  category: '',
  amount: undefined as number | undefined,
  note: '',
  date: new Date().toISOString().slice(0, 10),
})

const categories = ref<string[]>([])

watch(
  () => form.kind,
  (k) => {
    const meta = kinds.value.find((m) => m.value === k)
    categories.value = meta ? meta.categories : []
    form.category = categories.value[0] ?? ''
  },
)

async function loadMeta() {
  loadingMeta.value = true
  try {
    const meta = await getMeta()
    kinds.value = meta.kinds
    categories.value = meta.kinds[0]?.categories ?? []
    form.category = categories.value[0] ?? ''
  } finally {
    loadingMeta.value = false
  }
}

async function submit() {
  if (form.amount === undefined || form.amount <= 0) {
    ElMessage.warning('请输入金额')
    return
  }
  if (!form.category) {
    ElMessage.warning('请选择分类')
    return
  }
  saving.value = true
  try {
    const tx = await createTransaction({
      kind: form.kind,
      category: form.category,
      amount: form.amount,
      note: form.note,
      date: form.date,
    })
    ElMessage.success('已记一笔')
    emit('saved', tx)
    // 重置金额与说明，保留类型/分类/日期便于连续录入
    form.amount = undefined
    form.note = ''
  } catch (e) {
    ElMessage.error('记账失败')
  } finally {
    saving.value = false
  }
}

loadMeta()
</script>

<template>
  <div class="tx-form">
    <div class="form-row">
      <label class="form-label">类型</label>
      <div class="kind-tabs">
        <button
          v-for="k in kinds"
          :key="k.value"
          class="kind-tab"
          :class="{ active: form.kind === k.value }"
          @click="form.kind = k.value"
        >
          {{ k.label }}
        </button>
      </div>
    </div>

    <div class="form-row">
      <label class="form-label">分类</label>
      <div class="cat-tags">
        <button
          v-for="c in categories"
          :key="c"
          class="cat-tag"
          :class="{ active: form.category === c }"
          @click="form.category = c"
        >
          {{ c }}
        </button>
      </div>
    </div>

    <div class="form-row">
      <label class="form-label">金额</label>
      <input v-model.number="form.amount" class="field" type="number" min="0" step="0.01" placeholder="0.00" />
      <label class="form-label" style="margin-left: 16px">日期</label>
      <input v-model="form.date" class="field field-date" type="date" />
    </div>

    <div class="form-row">
      <label class="form-label">说明</label>
      <input v-model="form.note" class="field" type="text" placeholder="可选，一句话说明" />
    </div>

    <div class="form-actions">
      <button class="btn-submit" :disabled="saving" @click="submit">
        {{ saving ? '保存中…' : '记一笔' }}
      </button>
    </div>
  </div>
</template>
