<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  archiveHabit,
  checkin,
  createHabit,
  getStats,
  habitLogs,
  uncheck,
  updateHabit,
  type BoardHabit,
  type BoardStats,
  type FreqType,
  type Habit,
} from '@/api/habit'
import '@/styles/habit.css'

const board = ref<BoardStats | null>(null)
// 每个习惯的打卡日期集合（用于近 30 天热力图）
const logsById = reactive<Record<number, Set<string>>>({})
const loading = ref(false)
const saving = ref(false)

const todayStr = toDateStr(new Date())

// ---------------------------------------------------------------------------
// 加载
// ---------------------------------------------------------------------------
async function load() {
  loading.value = true
  try {
    const b = await getStats()
    board.value = b
    // 并行拉取每个习惯的打卡日期
    await Promise.all(
      b.habits.map(async (h) => {
        const res = await habitLogs(h.id)
        logsById[h.id] = new Set(res.dates)
      }),
    )
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function refresh() {
  try {
    const b = await getStats()
    board.value = b
    for (const h of b.habits) {
      const res = await habitLogs(h.id)
      logsById[h.id] = new Set(res.dates)
    }
  } catch {
    ElMessage.error('刷新失败')
  }
}

// ---------------------------------------------------------------------------
// 打卡（今日）
// ---------------------------------------------------------------------------
const celebrateVisible = ref(false)
const celebrate = ref<{ habit: BoardHabit; stats: any; board: BoardStats | null } | null>(null)

async function toggleCheckin(h: BoardHabit) {
  if (saving.value) return
  saving.value = true
  try {
    if (h.checked_today) {
      await uncheck(h.id, todayStr)
      await refresh()
    } else {
      const res = await checkin(h.id)
      await refresh()
      if (board.value) {
        celebrate.value = { habit: h, stats: res.stats, board: board.value }
        celebrateVisible.value = true
      }
    }
  } catch {
    ElMessage.error('打卡失败')
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------------------
// 新建 / 编辑习惯
// ---------------------------------------------------------------------------
const dialogVisible = ref(false)
const editing = ref<Habit | null>(null)
const form = reactive({
  name: '',
  reason: '',
  emoji: '🔴',
  freq_type: 'daily' as FreqType,
  freq_days: [] as number[],
  start_date: todayStr,
})

function openCreate() {
  editing.value = null
  form.name = ''
  form.reason = ''
  form.emoji = '🔴'
  form.freq_type = 'daily'
  form.freq_days = []
  form.start_date = todayStr
  dialogVisible.value = true
}

function openEdit(h: Habit) {
  editing.value = h
  form.name = h.name
  form.reason = h.reason
  form.emoji = h.emoji || '🔴'
  form.freq_type = h.freq_type
  form.freq_days = (h.freq_days || '')
    .split(',')
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => !Number.isNaN(n))
  form.start_date = h.start_date
  dialogVisible.value = true
}

async function saveHabit() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写习惯名')
    return
  }
  if (saving.value) return
  saving.value = true
  const payload = {
    name: form.name.trim(),
    reason: form.reason,
    emoji: form.emoji || '🔴',
    freq_type: form.freq_type,
    freq_days: form.freq_type === 'custom' ? form.freq_days.join(',') : '',
    start_date: form.start_date,
  }
  try {
    if (editing.value) {
      await updateHabit(editing.value.id, payload)
    } else {
      await createHabit(payload)
    }
    dialogVisible.value = false
    await refresh()
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onArchive(h: Habit) {
  try {
    await archiveHabit(h.id)
    await refresh()
    ElMessage.success('已归档')
  } catch {
    ElMessage.error('操作失败')
  }
}

// ---------------------------------------------------------------------------
// 频率选择 / 自定义周几
// ---------------------------------------------------------------------------
const WEEK = [
  { v: 1, label: '一' },
  { v: 2, label: '二' },
  { v: 3, label: '三' },
  { v: 4, label: '四' },
  { v: 5, label: '五' },
  { v: 6, label: '六' },
  { v: 7, label: '日' },
]

function toggleDay(v: number) {
  const i = form.freq_days.indexOf(v)
  if (i >= 0) form.freq_days.splice(i, 1)
  else form.freq_days.push(v)
}

// ---------------------------------------------------------------------------
// 近 30 天热力图
// ---------------------------------------------------------------------------
function toDateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function expectedOn(h: Habit, ds: string): boolean {
  const d = new Date(ds + 'T00:00:00')
  if (h.freq_type === 'daily') return true
  if (h.freq_type === 'weekdays') return d.getDay() >= 1 && d.getDay() <= 5
  if (h.freq_type === 'custom') {
    const days = (h.freq_days || '')
      .split(',')
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !Number.isNaN(n))
    const mon1 = ((d.getDay() + 6) % 7) + 1
    return days.includes(mon1)
  }
  return true
}

function heatmap(h: BoardHabit) {
  const logs = logsById[h.id] || new Set<string>()
  const arr: { date: string; expected: boolean; done: boolean; cls: string }[] = []
  const t = new Date()
  for (let i = 29; i >= 0; i--) {
    const d = new Date(t)
    d.setDate(d.getDate() - i)
    const ds = toDateStr(d)
    const exp = expectedOn(h, ds)
    const done = exp && logs.has(ds)
    let cls = 'hm'
    if (exp) cls += done ? ' done' : ' expected'
    arr.push({ date: ds, expected: exp, done, cls })
  }
  return arr
}

function heatTip(c: { date: string; expected: boolean; done: boolean }): string {
  const base = c.date
  if (!c.expected) return `${base}（非打卡日）`
  return `${base} ${c.done ? '已打卡' : '未打卡'}`
}

onMounted(load)
</script>

<template>
  <div class="habit-board">
    <!-- 总览 -->
    <div class="board-summary" v-if="board">
      <div class="board-card">
        <div class="bc-label">今日完成度</div>
        <div class="bc-value">
          {{ board.today_checked }} / {{ board.today_total }}
        </div>
        <div class="bc-bar">
          <span
            :style="{
              width:
                board.today_total
                  ? (board.today_checked / board.today_total) * 100 + '%'
                  : '0%',
            }"
          ></span>
        </div>
      </div>
      <div class="board-card">
        <div class="bc-label">累计打卡次数</div>
        <div class="bc-value">{{ board.total_checkins }}</div>
        <div class="bc-sub">每一次坚持都在累积</div>
      </div>
      <div class="board-card">
        <div class="bc-label">最长连续坚持</div>
        <div class="bc-value">{{ board.longest_overall }} 天</div>
        <div class="bc-sub">坚持就是力量 💪</div>
      </div>
    </div>

    <!-- 头部 -->
    <div class="habit-head">
      <span class="hh-title">习惯看板</span>
      <button class="btn-habit-new" @click="openCreate">＋ 新建习惯</button>
    </div>

    <!-- 列表 -->
    <div v-if="board && board.habits.length" class="habit-list">
      <div
        v-for="h in board.habits"
        :key="h.id"
        class="habit-card"
        :class="{ 'is-checked': h.checked_today }"
      >
        <div class="habit-top">
          <span class="habit-emoji">{{ h.emoji }}</span>
          <div>
            <div class="habit-name">{{ h.name }}</div>
            <div v-if="h.reason" class="habit-reason">{{ h.reason }}</div>
          </div>
          <div class="habit-streak">
            <span class="streak-num">🔥 {{ h.current_streak }}</span>
            <div class="streak-label">连续天数</div>
          </div>
          <div class="habit-card-actions">
            <button class="icon-btn" title="编辑" @click="openEdit(h)">编辑</button>
            <button class="icon-btn" title="归档" @click="onArchive(h)">归档</button>
          </div>
        </div>

        <div class="habit-stats">
          <span>累计 <b>{{ h.total_checkins }}</b> 次</span>
          <span>最长 <b>{{ h.longest_streak }}</b> 天</span>
          <div class="habit-rate">
            <span>完成率 {{ h.completion_rate }}%</span>
            <div class="rate-bar">
              <span :style="{ width: h.completion_rate + '%' }"></span>
            </div>
          </div>
        </div>

        <div class="habit-heat" :title="'近 30 天'">
          <span
            v-for="(c, i) in heatmap(h)"
            :key="i"
            :class="c.cls"
            :title="heatTip(c)"
          ></span>
        </div>

        <button
          class="checkin-btn"
          :class="{ done: h.checked_today }"
          :disabled="saving"
          @click="toggleCheckin(h)"
        >
          {{ h.checked_today ? '✓ 今日已打卡（点击取消）' : '今日打卡' }}
        </button>
      </div>
    </div>

    <div v-else-if="!loading" class="empty-habit">
      还没有习惯，点「新建习惯」开始你的坚持之旅吧 🔴
    </div>

    <!-- 新建 / 编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑习惯' : '新建习惯'"
      width="90%"
    >
      <div class="habit-form">
        <div class="form-row">
          <label>习惯名</label>
          <input v-model="form.name" type="text" placeholder="如：每天阅读 30 分钟" />
        </div>
        <div class="form-row">
          <label>为什么要坚持（可选）</label>
          <textarea
            v-model="form.reason"
            rows="2"
            placeholder="写下你的理由，帮助你感受坚持的力量"
          ></textarea>
        </div>
        <div class="form-row">
          <label>图标</label>
          <input v-model="form.emoji" type="text" maxlength="4" style="width: 80px" />
        </div>
        <div class="form-row">
          <label>频率</label>
          <div class="freq-opts">
            <div
              class="freq-opt"
              :class="{ active: form.freq_type === 'daily' }"
              @click="form.freq_type = 'daily'"
            >
              每天
            </div>
            <div
              class="freq-opt"
              :class="{ active: form.freq_type === 'weekdays' }"
              @click="form.freq_type = 'weekdays'"
            >
              工作日
            </div>
            <div
              class="freq-opt"
              :class="{ active: form.freq_type === 'custom' }"
              @click="form.freq_type = 'custom'"
            >
              自定义
            </div>
          </div>
        </div>
        <div v-if="form.freq_type === 'custom'" class="form-row">
          <label>每周几（可多选）</label>
          <div class="week-days">
            <button
              v-for="w in WEEK"
              :key="w.v"
              type="button"
              class="week-day"
              :class="{ active: form.freq_days.includes(w.v) }"
              @click="toggleDay(w.v)"
            >
              {{ w.label }}
            </button>
          </div>
        </div>
        <div class="form-row">
          <label>起始日</label>
          <el-date-picker
            v-model="form.start_date"
            type="date"
            value-format="YYYY-MM-DD"
            format="YYYY-MM-DD"
            placeholder="选择起始日"
            size="default"
          />
        </div>
      </div>
      <template #footer>
        <button class="btn-habit-new" :disabled="saving" @click="saveHabit">保存</button>
      </template>
    </el-dialog>

    <!-- 打卡成功庆祝弹窗 -->
    <el-dialog v-model="celebrateVisible" width="90%" align-center>
      <div v-if="celebrate" class="celebrate">
        <div class="ce-emoji">🎉</div>
        <div class="ce-title">打卡成功！</div>
        <div class="ce-name">{{ celebrate.habit.emoji }} {{ celebrate.habit.name }}</div>

        <div class="ce-grid">
          <div class="ce-cell">
            <div class="ce-num">🔥 {{ celebrate.stats.current_streak }}</div>
            <div class="ce-cap">连续坚持（天）</div>
          </div>
          <div class="ce-cell">
            <div class="ce-num">{{ celebrate.stats.total_checkins }}</div>
            <div class="ce-cap">累计打卡（次）</div>
          </div>
          <div class="ce-cell">
            <div class="ce-num">{{ celebrate.stats.completion_rate }}%</div>
            <div class="ce-cap">完成率</div>
          </div>
          <div class="ce-cell">
            <div class="ce-num">
              {{ celebrate.board ? celebrate.board.today_checked : 0 }} /
              {{ celebrate.board ? celebrate.board.today_total : 0 }}
            </div>
            <div class="ce-cap">今日完成</div>
          </div>
        </div>

        <div class="ce-progress">
          <span
            v-if="celebrate.board && celebrate.board.today_total"
            :style="{
              width:
                (celebrate.board.today_checked / celebrate.board.today_total) * 100 + '%',
            }"
          ></span>
        </div>
        <div class="ce-quote">坚持就是力量，你正在变得更好 💪</div>
      </div>
    </el-dialog>
  </div>
</template>
