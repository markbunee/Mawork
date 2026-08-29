<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listTasks, updateTask, checkin, uncheckin, type Task } from '@/api/planpool'
import { getDailyNet } from '@/api/accounting'

// 当前查看的日历月份（年-月）
const viewYear = ref(new Date().getFullYear())
const viewMonth = ref(new Date().getMonth() + 1)

const tasks = ref<Task[]>([])
const dailyNet = ref<Record<string, number>>({})

// 今天
const today = new Date()
const todayStr = toDateStr(today)

function toDateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// 该任务在某天是否活动（start_date <= d <= end_date）
function activeOn(t: Task, d: string): boolean {
  if (t.start_date && d < t.start_date) return false
  if (t.end_date && d > t.end_date) return false
  return true
}

// 任务是否真正完成（日程里手动改为"已完成"）
function isDone(t: Task): boolean {
  return t.progress === '完成'
}

// 该任务在某天是否已打卡
function checkedOn(t: Task, date: string): boolean {
  return (t.checkins || []).includes(date)
}

// 打勾 = 对该日期打卡（跨时间段任务每日打卡）；再点取消
async function toggleCheckin(t: Task, date: string) {
  try {
    if (checkedOn(t, date)) {
      await uncheckin(t.id, date)
      ElMessage.success('已取消打卡')
    } else {
      await checkin(t.id, date)
      ElMessage.success('已打卡')
    }
    await load()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

// ---- 顶部三列表 ----
// 本周范围
function weekRange(): { start: string; end: string } {
  // 周一为一周起点
  const day = today.getDay() // 0=周日
  const diffToMon = (day === 0 ? 6 : day - 1)
  const monday = new Date(today)
  monday.setDate(today.getDate() - diffToMon)
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  return { start: toDateStr(monday), end: toDateStr(sunday) }
}

// 本月范围
function monthRange(month: number, year: number): { start: string; end: string } {
  const start = `${year}-${String(month).padStart(2, '0')}-01`
  const last = new Date(year, month, 0).getDate()
  return { start, end: `${year}-${String(month).padStart(2, '0')}-${String(last).padStart(2, '0')}` }
}

// 今日待做：今天的任务（未完成），打勾=今天打卡
const todayTasks = computed(() =>
  tasks.value.filter((t) => activeOn(t, todayStr) && !isDone(t)),
)

// 本周计划：二级任务，未完成在前、已完成在后（手动勾选标记完成）
const weekTasks = computed(() => {
  const { start, end } = weekRange()
  const list = tasks.value.filter((t) => activeOn(t, start) && activeOn(t, end))
  return [...list.filter((t) => !isDone(t)), ...list.filter((t) => isDone(t))]
})

// 本月计划：一级任务（聚合其下二级），未完成在前、已完成在后
const monthTasks = computed(() => {
  const { start, end } = monthRange(viewMonth.value, viewYear.value)
  const list = tasks.value.filter((t) => activeOn(t, start) && activeOn(t, end))
  // 按一级任务聚合
  const map = new Map<string, { level1: string; todos: number; dones: number }>()
  for (const t of list) {
    const key = t.level1 || '(未分组)'
    if (!map.has(key)) map.set(key, { level1: key, todos: 0, dones: 0 })
    const item = map.get(key)!
    if (isDone(t)) item.dones++
    else item.todos++
  }
  const arr = [...map.values()]
  // 未完成在前（todos>0），已完成（全 done）在后
  return arr.filter((g) => g.todos > 0).concat(arr.filter((g) => g.todos === 0))
})

// 某一级任务是否已完成（其下所有二级都完成）
function level1Done(level1: string): boolean {
  const { start, end } = monthRange(viewMonth.value, viewYear.value)
  const subs = tasks.value.filter(
    (t) => (t.level1 || '(未分组)') === level1 && activeOn(t, start) && activeOn(t, end),
  )
  return subs.length > 0 && subs.every((t) => isDone(t))
}

// 本周：勾选一个二级任务 = 标记完成（同步日程）
async function toggleWeekComplete(t: Task) {
  try {
    await updateTask(t.id, {
      level1: t.level1,
      level2: t.level2,
      progress: '完成',
      note: t.note,
      start_date: t.start_date,
      end_date: t.end_date,
    })
    ElMessage.success('已标记完成')
    await load()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

// 本月：勾选一个一级任务 = 其下所有二级任务标记完成
async function toggleMonthComplete(level1: string) {
  const { start, end } = monthRange(viewMonth.value, viewYear.value)
  const subs = tasks.value.filter(
    (t) => (t.level1 || '(未分组)') === level1 && activeOn(t, start) && activeOn(t, end) && !isDone(t),
  )
  if (subs.length === 0) return
  try {
    await Promise.all(
      subs.map((t) =>
        updateTask(t.id, {
          level1: t.level1,
          level2: t.level2,
          progress: '完成',
          note: t.note,
          start_date: t.start_date,
          end_date: t.end_date,
        }),
      ),
    )
    ElMessage.success('已全部完成')
    await load()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

// 预分组：date -> Task[]。任务展开式：每个任务遍历其活动日期范围加入对应天，
// 避免日历每个格子对所有任务重复 filter。
const tasksByDate = computed<Map<string, Task[]>>(() => {
  const map = new Map<string, Task[]>()
  const year = viewYear.value
  const month = viewMonth.value
  const daysInMonth = new Date(year, month, 0).getDate()
  const monthPrefix = `${year}-${String(month).padStart(2, '0')}`
  const monthStart = `${monthPrefix}-01`
  const monthEnd = `${monthPrefix}-${String(daysInMonth).padStart(2, '0')}`

  const add = (ds: string, t: Task) => {
    if (!map.has(ds)) map.set(ds, [])
    map.get(ds)!.push(t)
  }

  for (const t of tasks.value) {
    // 任务有效日期范围（限当月）
    const s = t.start_date && t.start_date > monthStart ? t.start_date : monthStart
    const e = t.end_date && t.end_date < monthEnd ? t.end_date : monthEnd
    if (s > e) continue

    // 无日期或跨期范围外跳过
    if (!t.start_date && !t.end_date) continue

    // 遍历该任务在当月的每一天
    let cur = new Date(`${s}T00:00:00`)
    const endDate = new Date(`${e}T00:00:00`)
    while (cur <= endDate) {
      add(toDateStr(cur), t)
      cur = new Date(cur)
      cur.setDate(cur.getDate() + 1)
    }
  }
  return map
})

// ---- 大日历 ----
interface DayCell {
  date: string
  dayNum: number
  inMonth: boolean
  dayTasks: Task[]
  netIncome: number | null
}

// 生成当月的日历格子（6 行 x 7 列，周一起始）
const weeks = computed<DayCell[][]>(() => {
  const year = viewYear.value
  const month = viewMonth.value
  const first = new Date(year, month - 1, 1)
  const firstDow = first.getDay() // 0=周日
  const leadingBlanks = firstDow === 0 ? 6 : firstDow - 1 // 对齐周一起始
  const daysInMonth = new Date(year, month, 0).getDate()

  const cells: DayCell[] = []
  // 前导空白
  for (let i = 0; i < leadingBlanks; i++) {
    const dt = new Date(year, month - 1, 1 - (leadingBlanks - i))
    cells.push({
      date: toDateStr(dt),
      dayNum: dt.getDate(),
      inMonth: false,
      dayTasks: [],
      netIncome: null,
    })
  }
  // 当月
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    cells.push({
      date: ds,
      dayNum: d,
      inMonth: true,
      dayTasks: tasksByDate.value.get(ds) ?? [],
      netIncome: dailyNet.value[ds] ?? null,
    })
  }
  // 补齐到 7 的倍数
  while (cells.length % 7 !== 0) {
    const last = cells[cells.length - 1]
    const next = new Date(`${last.date}T00:00:00`)
    next.setDate(next.getDate() + 1)
    cells.push({
      date: toDateStr(next),
      dayNum: next.getDate(),
      inMonth: false,
      dayTasks: [],
      netIncome: null,
    })
  }

  // 切分周
  const weeksArr: DayCell[][] = []
  for (let i = 0; i < cells.length; i += 7) {
    weeksArr.push(cells.slice(i, i + 7))
  }
  return weeksArr
})

// 月份导航
function prevMonth() {
  if (viewMonth.value === 1) {
    viewMonth.value = 12
    viewYear.value--
  } else {
    viewMonth.value--
  }
  load()
}
function nextMonth() {
  if (viewMonth.value === 12) {
    viewMonth.value = 1
    viewYear.value++
  } else {
    viewMonth.value++
  }
  load()
}
function todayBtn() {
  viewYear.value = new Date().getFullYear()
  viewMonth.value = new Date().getMonth() + 1
  load()
}

async function load() {
  try {
    const [t, d] = await Promise.all([
      listTasks(),
      getDailyNet(String(viewYear.value), String(viewMonth.value).padStart(2, '0')),
    ])
    tasks.value = t
    dailyNet.value = d.daily
  } catch (e) {
    ElMessage.error('加载失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="home">
    <!-- 顶部三列表 -->
    <div class="home-todos">
      <div class="todo-col">
        <h3 class="todo-title">今日待做</h3>
        <ul class="todo-list">
          <li v-if="todayTasks.length === 0" class="todo-empty">暂无</li>
          <li v-for="t in todayTasks" :key="t.id" class="todo-item" :class="{ checked: checkedOn(t, todayStr) }" @click="toggleCheckin(t, todayStr)">
            <span class="todo-check"></span>
            <span class="todo-text">{{ t.level2 || t.level1 }}</span>
          </li>
        </ul>
      </div>
      <div class="todo-col">
        <h3 class="todo-title">本周计划</h3>
        <ul class="todo-list">
          <li v-if="weekTasks.length === 0" class="todo-empty">暂无</li>
          <li v-for="t in weekTasks" :key="t.id" class="todo-item" :class="{ checked: isDone(t) }" @click="toggleWeekComplete(t)">
            <span class="todo-check"></span>
            <span class="todo-text">{{ t.level2 || t.level1 }}</span>
          </li>
        </ul>
      </div>
      <div class="todo-col">
        <h3 class="todo-title">本月计划</h3>
        <ul class="todo-list">
          <li v-if="monthTasks.length === 0" class="todo-empty">暂无</li>
          <li
            v-for="g in monthTasks"
            :key="g.level1"
            class="todo-item"
            :class="{ checked: level1Done(g.level1) }"
            @click="toggleMonthComplete(g.level1)"
          >
            <span class="todo-check"></span>
            <span class="todo-text">{{ g.level1 }}</span>
          </li>
        </ul>
      </div>
    </div>

    <!-- 大日历 -->
    <div class="home-calendar">
      <div class="cal-head">
        <button class="cal-nav" @click="prevMonth">‹</button>
        <span class="cal-title">{{ viewYear }}年 {{ viewMonth }}月</span>
        <button class="cal-nav" @click="nextMonth">›</button>
        <button class="cal-today" @click="todayBtn">今天</button>
      </div>

      <div class="cal-weekdays">
        <span v-for="w in ['一','二','三','四','五','六','日']" :key="w" class="cal-weekday">{{ w }}</span>
      </div>

      <div class="cal-body">
        <div v-for="(week, wi) in weeks" :key="wi" class="cal-week">
          <div
            v-for="cell in week"
            :key="cell.date"
            class="cal-day"
            :class="{ 'out-month': !cell.inMonth, today: cell.date === todayStr }"
          >
            <div class="cal-day-head">
              <span class="cal-daynum">{{ cell.dayNum }}</span>
              <span v-if="cell.netIncome !== null" class="cal-net" :class="cell.netIncome >= 0 ? 'pos' : 'neg'">
                {{ cell.netIncome >= 0 ? '+' : '' }}{{ cell.netIncome }}
              </span>
            </div>
            <ul class="cal-tasks">
              <li
                v-for="t in cell.dayTasks"
                :key="t.id"
                class="cal-task"
                :class="{ checked: checkedOn(t, cell.date) }"
                @click="toggleCheckin(t, cell.date)"
              >
                <span class="cal-task-check"></span>
                <span class="cal-task-text">{{ t.level2 || t.level1 }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
