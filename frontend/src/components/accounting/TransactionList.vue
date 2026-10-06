<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteTransaction,
  listReimburseEvents,
  createReimburseEvent,
  deleteReimburseEvent,
  type Transaction,
  type ReimburseEvent,
} from '@/api/accounting'

const props = defineProps<{ list: Transaction[]; kindLabel: (k: string) => string }>()
const emit = defineEmits<{ (e: 'changed'): void }>()

const total = computed(() =>
  props.list.reduce((s, t) => s + t.amount, 0).toFixed(2),
)

// 报销类条目的细分：垫付合计 / 已收回 / 未收回（按单笔 remaining 汇总）。
const reimburseSubtotal = computed(() => {
  const items = props.list.filter((t) => t.kind === 'reimburse')
  if (!items.length) return null
  let fronted = 0
  let collected = 0
  for (const t of items) {
    fronted += t.amount
    collected += t.reimbursed ?? 0
  }
  return {
    fronted: Math.round(fronted * 100) / 100,
    collected: Math.round(collected * 100) / 100,
    outstanding: Math.round((fronted - collected) * 100) / 100,
  }
})

function kindClass(kind: string) {
  return `kind-${kind}`
}

// ---------------- 报销事件弹窗 ----------------
const settleTarget = ref<Transaction | null>(null)
const events = ref<ReimburseEvent[]>([])
const reimburseForm = reactive({ amount: 0, date: '', note: '' })
const submitting = ref(false)

const dialogVisible = computed({
  get: () => !!settleTarget.value,
  set: (v: boolean) => {
    if (!v) settleTarget.value = null
  },
})

function todayStr() {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function reimburseProgress() {
  const tx = settleTarget.value
  if (!tx) return { done: 0, remaining: 0 }
  const done = events.value.reduce((s, e) => s + e.amount, 0)
  return { done, remaining: Math.max(tx.amount - done, 0) }
}

async function openSettle(tx: Transaction) {
  settleTarget.value = tx
  reimburseForm.amount = tx.remaining ?? tx.amount
  reimburseForm.date = todayStr()
  reimburseForm.note = ''
  events.value = await listReimburseEvents(tx.id)
}

async function submitReimburse() {
  const tx = settleTarget.value
  if (!tx) return
  if (!(reimburseForm.amount > 0)) {
    ElMessage.warning('请输入报销金额')
    return
  }
  if (reimburseForm.amount > reimburseProgress().remaining) {
    ElMessage.warning('报销金额超过剩余待报销')
    return
  }
  submitting.value = true
  try {
    await createReimburseEvent(tx.id, {
      amount: reimburseForm.amount,
      event_date: reimburseForm.date,
      note: reimburseForm.note,
    })
    ElMessage.success('已记录报销到账')
    events.value = await listReimburseEvents(tx.id)
    reimburseForm.amount = reimburseProgress().remaining
    reimburseForm.note = ''
    emit('changed')
  } catch (e) {
    ElMessage.error('报销失败')
  } finally {
    submitting.value = false
  }
}

async function removeEvent(ev: ReimburseEvent) {
  const tx = settleTarget.value
  if (!tx) return
  try {
    await ElMessageBox.confirm(
      `删除这笔 ¥${ev.amount.toFixed(2)}（${ev.event_date}）的报销到账？`,
      '确认删除',
      { type: 'warning' },
    )
    await deleteReimburseEvent(ev.id)
    ElMessage.success('已删除')
    events.value = await listReimburseEvents(tx.id)
    reimburseForm.amount = reimburseProgress().remaining
    emit('changed')
  } catch (e) {
    /* 取消 */
  }
}

async function onDelete(tx: Transaction) {
  try {
    await ElMessageBox.confirm(
      `删除这笔「${props.kindLabel(tx.kind)}·${tx.category}」（¥${tx.amount.toFixed(2)}）？`,
      '确认删除',
      { type: 'warning' },
    )
    await deleteTransaction(tx.id)
    ElMessage.success('已删除')
    emit('changed')
  } catch (e) {
    /* 取消 */
  }
}
</script>

<template>
  <div class="tx-list-wrap">
    <div class="list-sum">
      <span class="sum-label">小计</span>
      <span class="sum-value">¥ {{ total }}</span>
      <template v-if="reimburseSubtotal">
        <span class="sum-reimburse">
          垫付 {{ reimburseSubtotal.fronted.toFixed(2) }} ·
          已收回 {{ reimburseSubtotal.collected.toFixed(2) }} ·
          未收回 <b>{{ reimburseSubtotal.outstanding.toFixed(2) }}</b>
        </span>
      </template>
    </div>

    <div class="tx-table-scroll">
    <table class="tx-table">
      <thead>
        <tr>
          <th>日期</th>
          <th>分类</th>
          <th>说明</th>
          <th class="col-amount">金额</th>
          <th class="col-actions"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="list.length === 0">
          <td colspan="5" class="empty">暂无记录</td>
        </tr>
        <tr v-for="tx in list" :key="tx.id">
          <td class="cell-date">{{ tx.date }}</td>
          <td>
            <span class="cat-chip" :class="kindClass(tx.kind)">{{ tx.category }}</span>
            <span v-if="tx.category2" class="cat-sub">{{ tx.category2 }}</span>
          </td>
          <td class="cell-note">{{ tx.note || '—' }}</td>
          <td class="col-amount amount">
            {{ tx.amount.toFixed(2) }}
            <div v-if="tx.kind === 'reimburse'" class="reimburse-progress">
              已报 {{ (tx.reimbursed ?? 0).toFixed(2) }} · 剩 {{ (tx.remaining ?? tx.amount).toFixed(2) }}
            </div>
          </td>
          <td class="col-actions">
            <button
              v-if="tx.kind === 'reimburse' && (tx.remaining ?? tx.amount) > 0"
              class="link-btn"
              @click="openSettle(tx)"
            >
              报销
            </button>
            <button class="link-btn danger" @click="onDelete(tx)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    </div>

    <div v-if="list.length > 0" class="list-footer">本月共 {{ list.length }} 笔</div>

    <el-dialog v-model="dialogVisible" title="报销到账" width="440px">
      <template v-if="settleTarget">
        <div class="reimburse-head">
          待报销 ¥{{ settleTarget.amount.toFixed(2) }}
          <span class="muted">
            已报 ¥{{ reimburseProgress().done.toFixed(2) }} · 剩余 ¥{{ reimburseProgress().remaining.toFixed(2) }}
          </span>
        </div>

        <div class="reimburse-form">
          <label>报销金额</label>
          <el-input-number
            v-model="reimburseForm.amount"
            :min="0.01"
            :max="Math.max(reimburseProgress().remaining, 0.01)"
            :step="0.01"
            :precision="2"
            :disabled="reimburseProgress().remaining <= 0"
          />
          <label>到账日期</label>
          <el-date-picker v-model="reimburseForm.date" type="date" value-format="YYYY-MM-DD" />
          <label>备注（可选）</label>
          <el-input v-model="reimburseForm.note" placeholder="例如：公司报销 8 月交通费" />
        </div>

        <div v-if="events.length" class="reimburse-events">
          <div class="reimburse-events-title">到账记录</div>
          <div v-for="ev in events" :key="ev.id" class="reimburse-event">
            <span class="ev-date">{{ ev.event_date }}</span>
            <span class="ev-amount">¥{{ ev.amount.toFixed(2) }}</span>
            <span class="muted ev-note">{{ ev.note || '—' }}</span>
            <button class="link-btn danger" @click="removeEvent(ev)">删除</button>
          </div>
        </div>
      </template>
      <template #footer>
        <button
          class="btn-asset-save"
          :disabled="submitting || reimburseProgress().remaining <= 0"
          @click="submitReimburse"
        >
          {{ submitting ? '保存中…' : '记录到账' }}
        </button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.reimburse-progress {
  font-size: 11px;
  color: #b09a6e;
  font-weight: normal;
  line-height: 1.4;
}
.reimburse-head {
  font-size: 14px;
  color: #2c2a26;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.muted {
  color: #8a857a;
  font-size: 12px;
}
.reimburse-form {
  display: grid;
  grid-template-columns: 80px 1fr;
  gap: 10px 12px;
  align-items: center;
  margin-bottom: 12px;
}
.reimburse-form label {
  color: #6b6558;
  font-size: 13px;
}
.reimburse-events {
  border-top: 1px dashed #ece7de;
  padding-top: 10px;
}
.reimburse-events-title {
  font-size: 12px;
  color: #8a857a;
  margin-bottom: 6px;
}
.reimburse-event {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
  font-size: 13px;
}
.ev-date {
  color: #6b6558;
  min-width: 90px;
}
.ev-amount {
  min-width: 70px;
  font-weight: 600;
  color: #2c2a26;
}
.ev-note {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
