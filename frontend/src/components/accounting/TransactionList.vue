<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteTransaction,
  settleReimbursement,
  type Transaction,
} from '@/api/accounting'

const props = defineProps<{ list: Transaction[]; kindLabel: (k: string) => string }>()
const emit = defineEmits<{ (e: 'changed'): void }>()

const total = computed(() =>
  props.list.reduce((s, t) => s + t.amount, 0).toFixed(2),
)

function kindClass(kind: string) {
  return `kind-${kind}`
}

async function onSettle(tx: Transaction) {
  try {
    await ElMessageBox.confirm(
      `将「${tx.note || tx.category}」（¥${tx.amount.toFixed(2)}）转为已报销？`,
      '确认报销',
      { type: 'info' },
    )
    await settleReimbursement(tx.id)
    ElMessage.success('已转为已报销')
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
    </div>

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
          </td>
          <td class="cell-note">{{ tx.note || '—' }}</td>
          <td class="col-amount amount">{{ tx.amount.toFixed(2) }}</td>
          <td class="col-actions">
            <button
              v-if="tx.kind === 'reimburse' && tx.category === '待报销'"
              class="link-btn"
              @click="onSettle(tx)"
            >
              报销
            </button>
            <button class="link-btn danger" @click="onDelete(tx)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
