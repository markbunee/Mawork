<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { exportUrl, getStats, listTasks, type Stats, type Task } from '@/api/planpool'
import TaskTable from '@/components/planpool/TaskTable.vue'

const now = new Date()
const curYear = ref(now.getFullYear())
const months = Array.from({ length: 12 }, (_, i) => i + 1)
// 默认界面停在当前月
const selectedMonth = ref<number>(now.getMonth() + 1)

const tasks = ref<Task[]>([])
const stats = ref<Stats>({ total: 0, done: 0, todo: 0, doing: 0 })

function period(): string {
  return `${curYear.value}-${String(selectedMonth.value).padStart(2, '0')}`
}

async function load() {
  try {
    const month = period()
    const [t, s] = await Promise.all([listTasks(month), getStats(month)])
    tasks.value = t
    stats.value = s
  } catch {
    ElMessage.error('加载失败')
  }
}

function selectMonth(m: number) {
  selectedMonth.value = m
  load()
}

function doExport() {
  window.open(exportUrl, '_blank')
}

onMounted(load)
</script>

<template>
  <div class="planpool">
    <div class="pp-toolbar">
      <div class="pp-stats">
        <span class="stat-total">共 {{ stats.total }} 项</span>
        <span class="stat-item todo">未完成 {{ stats.todo }}</span>
        <span class="stat-item doing">进行中 {{ stats.doing }}</span>
        <span class="stat-item done">已完成 {{ stats.done }}</span>
      </div>
      <button class="btn-export" @click="doExport">导出 Excel</button>
    </div>

    <!-- 月份标签 -->
    <div class="pp-months">
      <button
        v-for="m in months"
        :key="m"
        class="pp-month"
        :class="{ active: selectedMonth === m }"
        @click="selectMonth(m)"
      >
        {{ m }}月
      </button>
      <select v-model="curYear" class="pp-year" @change="load">
        <option v-for="y in [curYear - 1, curYear, curYear + 1]" :key="y" :value="y">{{ y }}</option>
      </select>
    </div>

    <TaskTable :tasks="tasks" @changed="load" />
  </div>
</template>
