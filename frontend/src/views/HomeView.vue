<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getDailyNet } from '@/api/accounting'
import {
  getMonthNote,
  listCalDays,
  listWeekNotes,
  saveCalDay,
  saveMonthNote,
  saveWeekNote,
  type CalLine,
} from '@/api/calday'
import {
  checkin as habitCheckin,
  getByDate,
  getCalendar,
  getStats as getHabitStats,
  uncheck as habitUncheck,
  type BoardStats,
  type Habit,
  type HabitForDate,
  type HabitStats,
} from '@/api/habit'
import { listTimers, startTimer as startFocusTimer, type Timer } from '@/api/timer'
import { useRouter } from 'vue-router'
import { fmtMoney, fmtSec, getDashboard, type Dashboard } from '@/api/insight'
import { computeRange } from '@/utils/dateRange'
import CalendarDayEditor from '@/components/home/CalendarDayEditor.vue'
import { useIsMobile } from '@/utils/useIsMobile'

// 本周概览：与复盘中心同一套聚合接口，失败不影响日历主体
const week = ref<Dashboard | null>(null)
async function loadWeek() {
  const r = computeRange('week', new Date())
  try {
    week.value = await getDashboard(r.from, r.to)
  } catch {
    week.value = null
  }
}

// ---------------------------------------------------------------------------
// 习惯进度（并入今天页：原「习惯」页是独立入口，这里只做当日快速打卡）
// ---------------------------------------------------------------------------
const habitBoard = ref<BoardStats | null>(null)
/** 今日习惯明细（含真实完成态，来自 getByDate） */
const todayHabitList = ref<HabitForDate[]>([])

async function loadHabitBoard() {
  try {
    const [board, todayRes] = await Promise.all([getHabitStats(), getByDate(todayStr)])
    habitBoard.value = board
    todayHabitList.value = todayRes.habits
  } catch {
    habitBoard.value = null
    todayHabitList.value = []
  }
}

/** 习惯进度条百分比（0–100） */
const habitPct = computed(() => {
  const list = todayHabitList.value
  const expected = list.filter((h) => h.expected)
  if (!expected.length) return 0
  const done = expected.filter((h) => h.done).length
  return Math.round((done / expected.length) * 100)
})

const habitDoneCount = computed(() => todayHabitList.value.filter((h) => h.expected && h.done).length)
const habitExpectedCount = computed(() => todayHabitList.value.filter((h) => h.expected).length)

/** 快速打卡/取消：作用于今天，成功后刷新看板与日历红点 */
const habitBusy = ref(false)
async function quickToggleHabit(h: HabitForDate) {
  if (habitBusy.value) return
  habitBusy.value = true
  try {
    if (h.done) {
      await habitUncheck(h.habit.id, todayStr)
    } else {
      await habitCheckin(h.habit.id, todayStr)
    }
    await Promise.all([loadHabitBoard(), reloadCalendar()])
  } catch {
    ElMessage.error('操作失败')
  } finally {
    habitBusy.value = false
  }
}

// ---------------------------------------------------------------------------
// 专注计时（并入今天页：原「计时」页是独立入口，这里只放当日在跑的计时器）
// ---------------------------------------------------------------------------
const focusTimers = ref<Timer[]>([])
async function loadFocus() {
  try {
    const list = await listTimers()
    // 只保留进行中/暂停中的（今日专注入口）
    focusTimers.value = list
      .filter((t) => t.status === 'active' || t.status === 'paused')
      .slice(0, 3)
  } catch {
    focusTimers.value = []
  }
}

const focusBusy = ref(false)
async function quickStartTimer(id: number) {
  if (focusBusy.value) return
  focusBusy.value = true
  try {
    await startFocusTimer(id)
    await loadFocus()
  } catch {
    ElMessage.error('启动失败')
  } finally {
    focusBusy.value = false
  }
}

/** 计时类型 → 中文短标 */
function timerLabel(t: Timer): string {
  switch (t.type) {
    case 'countup': return '正计时'
    case 'countdown': return '倒计时'
    case 'countup_days': return '累计天'
    case 'countdown_days': return '倒数天'
    default: return '计时'
  }
}

const viewYear = ref(new Date().getFullYear())
const viewMonth = ref(new Date().getMonth() + 1)

const days = ref<Record<string, CalLine[]>>({})
const dailyNet = ref<Record<string, number>>({})

// 月度计划（按月）与周计划（按该周周一），均为用户自由书写
const monthNote = ref('')
const weekNotes = ref<Record<string, string>>({})

// 习惯：日历红点 + 日期打卡面板（红色）
const habitMap = ref<Record<string, { total: number; done: number }>>({})
const panelVisible = ref(false)
const panelDate = ref('')
const panelHabits = ref<HabitForDate[]>([])
const panelSaving = ref(false)

// 右侧抽屉：习惯 + 专注计时（点击右缘标签拉出，不占日历布局）
const sideOpen = ref(false)

// 打卡成功庆祝弹窗（与「习惯」页体验一致）
const celebrateVisible = ref(false)
const celebrate = ref<{ habit: Habit; stats: HabitStats; board: BoardStats | null } | null>(null)

const today = new Date()
const todayStr = toDateStr(today)

function toDateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// ---------------------------------------------------------------------------
// 日历格子
// ---------------------------------------------------------------------------
/** 月度计划的键：YYYY-MM */
const monthKey = computed(() => `${viewYear.value}-${String(viewMonth.value).padStart(2, '0')}`)

interface DayCell {
  date: string
  dayNum: number
  inMonth: boolean
  net: number | null
}

const weeks = computed<DayCell[][]>(() => {
  const year = viewYear.value
  const month = viewMonth.value
  const first = new Date(year, month - 1, 1)
  const firstDow = first.getDay()
  const leadingBlanks = firstDow === 0 ? 6 : firstDow - 1
  const daysInMonth = new Date(year, month, 0).getDate()

  const cells: DayCell[] = []
  for (let i = 0; i < leadingBlanks; i++) {
    const dt = new Date(year, month - 1, 1 - (leadingBlanks - i))
    cells.push(makeCell(dt, false))
  }
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push(makeCell(new Date(year, month - 1, d), true))
  }
  while (cells.length % 7 !== 0) {
    const last = cells[cells.length - 1]
    const next = new Date(`${last.date}T00:00:00`)
    next.setDate(next.getDate() + 1)
    cells.push(makeCell(next, false))
  }

  const arr: DayCell[][] = []
  for (let i = 0; i < cells.length; i += 7) arr.push(cells.slice(i, i + 7))
  return arr
})

// 手机端：单日切换视图（桌面端 isMobile 为 false，仍走整月多周渲染）
const isMobile = useIsMobile()
const mobileDayDate = ref(todayStr)

const router = useRouter()
function writeDaily(date: string) {
  router.push({ path: '/daily', query: { date } })
}

// 跨月时把单日视图对齐到当月（优先今天，否则月中 15 号）
function syncMobileDay() {
  const y = viewYear.value
  const m = String(viewMonth.value).padStart(2, '0')
  const inMonth = todayStr.slice(0, 7) === `${y}-${m}`
  mobileDayDate.value = inMonth ? todayStr : `${y}-${m}-15`
}

const weekdayNames = ['日', '一', '二', '三', '四', '五', '六']
const mobileDayLabel = computed(() => {
  const d = new Date(`${mobileDayDate.value}T00:00:00`)
  return `${mobileDayDate.value.slice(5)} 周${weekdayNames[d.getDay()]}`
})

const mobileCell = computed(() => {
  const date = mobileDayDate.value
  return {
    date,
    dayNum: Number(date.slice(8, 10)),
    inMonth: date.slice(0, 7) === monthKey.value,
    net: dailyNet.value[date] ?? null,
    lines: linesOf(date),
    habitDone: habitMap.value[date]?.done,
    habitTotal: habitMap.value[date]?.total,
  }
})

function setMobileDay(date: string) {
  mobileDayDate.value = date
  const y = Number(date.slice(0, 4))
  const m = Number(date.slice(5, 7))
  if (y !== viewYear.value || m !== viewMonth.value) {
    viewYear.value = y
    viewMonth.value = m
    void load()
  }
}
const prevMobileDay = () => {
  const d = new Date(`${mobileDayDate.value}T00:00:00`)
  d.setDate(d.getDate() - 1)
  setMobileDay(toDateStr(d))
}
const nextMobileDay = () => {
  const d = new Date(`${mobileDayDate.value}T00:00:00`)
  d.setDate(d.getDate() + 1)
  setMobileDay(toDateStr(d))
}

function makeCell(dt: Date, inMonth: boolean): DayCell {
  const date = toDateStr(dt)
  return { date, dayNum: dt.getDate(), inMonth, net: dailyNet.value[date] ?? null }
}

/** 可见区间的首尾日期，用于一次性拉取整屏文本行 */
const visibleRange = computed(() => {
  const flat = weeks.value.flat()
  return { from: flat[0].date, to: flat[flat.length - 1].date }
})

function linesOf(date: string): CalLine[] {
  if (!days.value[date]) days.value[date] = []
  return days.value[date]
}

// ---------------------------------------------------------------------------
// 保存（按天防抖）；日历任务行可在日报页「来自日历」区看到
// ---------------------------------------------------------------------------
const timers = new Map<string, number>()
// 月度 / 周计划的防抖任务：{ 定时器, 立即执行的保存函数 }
const noteTimers = new Map<string, { timer: number; save: () => Promise<unknown> }>()

function scheduleSave(date: string) {
  const old = timers.get(date)
  if (old) window.clearTimeout(old)
  timers.set(
    date,
    window.setTimeout(() => {
      timers.delete(date)
      void doSave(date)
    }, 1000),
  )
}

/** 月度 / 周计划防抖保存，key 形如 month:2026-09 / week:2026-09-01 */
function scheduleNoteSave(key: string, save: () => Promise<unknown>) {
  const old = noteTimers.get(key)
  if (old) window.clearTimeout(old.timer)
  noteTimers.set(key, {
    timer: window.setTimeout(() => {
      noteTimers.delete(key)
      void save().catch(() => ElMessage.error('保存失败'))
    }, 1000),
    save,
  })
}

function onMonthEdit() {
  const m = monthKey.value
  scheduleNoteSave(`month:${m}`, () => saveMonthNote(m, monthNote.value))
}

function onWeekEdit(weekStart: string) {
  scheduleNoteSave(`week:${weekStart}`, () =>
    saveWeekNote(weekStart, weekNotes.value[weekStart] ?? ''),
  )
}

function onWeekInput(weekStart: string, ev: Event) {
  weekNotes.value[weekStart] = (ev.target as HTMLTextAreaElement).value
  onWeekEdit(weekStart)
}

async function doSave(date: string) {
  const lines = days.value[date] ?? []
  try {
    await saveCalDay(
      date,
      lines.map((l) => ({ kind: l.kind, text: l.text, done: l.done })),
    )
  } catch {
    ElMessage.error('保存失败')
  }
}

/** 切月 / 卸载前把挂起的编辑立即落库，避免丢掉最后 700ms 内的输入 */
async function flushPending() {
  const pendingDates = [...timers.keys()]
  timers.forEach((t) => window.clearTimeout(t))
  timers.clear()
  const pendingNotes = [...noteTimers.values()]
  noteTimers.forEach((t) => window.clearTimeout(t.timer))
  noteTimers.clear()
  for (const d of pendingDates) await doSave(d).catch(() => {})
  for (const n of pendingNotes) await n.save().catch(() => {})
}

function onEdit(date: string) {
  scheduleSave(date)
}

// ---------------------------------------------------------------------------
// 习惯：日期打卡面板（红色）
// ---------------------------------------------------------------------------
async function reloadCalendar() {
  const { from, to } = visibleRange.value
  try {
    const cm = await getCalendar(from, to)
    habitMap.value = cm.map
  } catch {
    // 习惯接口异常不影响日历主体
  }
}

async function openHabitPanel(date: string) {
  panelDate.value = date
  panelSaving.value = false
  try {
    const res = await getByDate(date)
    panelHabits.value = res.habits
    panelVisible.value = true
  } catch {
    ElMessage.error('加载失败')
  }
}

async function togglePanelHabit(h: HabitForDate) {
  if (panelSaving.value) return
  panelSaving.value = true
  try {
    if (h.done) {
      await habitUncheck(h.habit.id, panelDate.value)
    } else {
      const res = await habitCheckin(h.habit.id, panelDate.value)
      const board = await getHabitStats()
      celebrate.value = { habit: h.habit, stats: res.stats, board }
      celebrateVisible.value = true
    }
    const r = await getByDate(panelDate.value)
    panelHabits.value = r.habits
    await reloadCalendar()
  } catch {
    ElMessage.error('操作失败')
  } finally {
    panelSaving.value = false
  }
}

// ---------------------------------------------------------------------------
// 月份导航
// ---------------------------------------------------------------------------
function prevMonth() {
  if (viewMonth.value === 1) {
    viewMonth.value = 12
    viewYear.value--
  } else {
    viewMonth.value--
  }
  load()
  syncMobileDay()
}
function nextMonth() {
  if (viewMonth.value === 12) {
    viewMonth.value = 1
    viewYear.value++
  } else {
    viewMonth.value++
  }
  load()
  syncMobileDay()
}
function todayBtn() {
  viewYear.value = new Date().getFullYear()
  viewMonth.value = new Date().getMonth() + 1
  load()
  syncMobileDay()
}

async function load() {
  await flushPending()
  const { from, to } = visibleRange.value
  try {
    const [cal, net, mn, wn, cm] = await Promise.all([
      listCalDays(from, to),
      getDailyNet(String(viewYear.value), String(viewMonth.value).padStart(2, '0')),
      getMonthNote(monthKey.value),
      listWeekNotes(from, to),
      getCalendar(from, to),
    ])
    days.value = cal.days
    dailyNet.value = net.daily
    monthNote.value = mn.content
    weekNotes.value = { ...wn.notes }
    habitMap.value = cm.map
    // 每一周预置键，保证 textarea 的 v-model 绑定稳定
    weeks.value.forEach((w) => {
      const ws = w[0].date
      if (weekNotes.value[ws] === undefined) weekNotes.value[ws] = ''
    })
    // 空白日期预置一行，点进去就能直接打字
    weeks.value.flat().forEach((c) => {
      if (linesOf(c.date).length === 0) linesOf(c.date).push(blankLine(c.date))
    })
  } catch {
    ElMessage.error('加载失败')
  }
}

let uid = -1
function blankLine(date: string): CalLine {
  return { id: uid--, date, sort: 0, kind: 'text', text: '', done: false }
}

onMounted(() => {
  void load()
  void loadWeek()
  void loadHabitBoard()
  void loadFocus()
})
onBeforeUnmount(() => {
  void flushPending()
})
</script>

<template>
  <div class="home">
    <div class="home-cols">
      <div class="home-main">
    <!-- 本周概览：数据来自复盘中心的同一套聚合接口 -->
    <section class="home-summary">
      <div class="hs-head">
        <span class="hs-title">本周概览</span>
        <span class="hs-range">{{ week?.range.from.slice(5) }} ~ {{ week?.range.to.slice(5) }}</span>
        <RouterLink class="hs-more" to="/analysis">复盘中心 →</RouterLink>
      </div>
      <div v-if="week" class="hs-cells">
        <div class="hs-cell" :class="{ down: week.finance.net < 0 }">
          <span class="hs-num">{{ fmtMoney(week.finance.net) }}</span>
          <span class="hs-cap">收支结余</span>
        </div>
        <div class="hs-cell">
          <span class="hs-num">{{ fmtSec(week.focus.total_sec) }}</span>
          <span class="hs-cap">专注时长</span>
        </div>
        <div class="hs-cell">
          <span class="hs-num">{{ week.tasks.done }}/{{ week.tasks.total }}</span>
          <span class="hs-cap">任务完成</span>
        </div>
        <div class="hs-cell">
          <span class="hs-num">{{ week.habits.rate }}%</span>
          <span class="hs-cap">习惯达标</span>
        </div>
        <div class="hs-cell">
          <span class="hs-num">{{ week.writing.days }}</span>
          <span class="hs-cap">日报篇数</span>
        </div>
      </div>
      <div v-else class="hs-empty">本周概览加载失败，可到「复盘中心」查看</div>
    </section>

    <div class="home-calendar">
      <div class="cal-head">
        <button class="cal-nav" @click="prevMonth">‹</button>
        <span class="cal-title">{{ viewYear }}年 {{ viewMonth }}月</span>
        <button class="cal-nav" @click="nextMonth">›</button>
        <button class="cal-today" @click="todayBtn">今天</button>
        <span class="cal-hint">回车换行 · 左侧圆点刷成任务 · 点方框切换完成 / 未完成 · 任务会出现在当日日报顶部</span>
      </div>

      <!-- 月度计划：整块自由文本，按月独立保存 -->
      <div class="cal-monthplan">
        <div class="cal-monthplan-head">
          <span class="cal-monthplan-title">月度计划</span>
          <span class="cal-monthplan-hint">{{ viewYear }}年{{ viewMonth }}月 · 自动保存</span>
        </div>
        <textarea
          v-model="monthNote"
          class="cal-monthplan-input"
          placeholder="写下本月的月度计划…"
          spellcheck="false"
          @input="onMonthEdit"
        ></textarea>
      </div>

      <div class="cal-weekdays">
        <span class="cal-weekday cal-weekplan-head">周计划</span>
        <span v-for="w in ['一', '二', '三', '四', '五', '六', '日']" :key="w" class="cal-weekday">
          {{ w }}
        </span>
      </div>

      <div class="cal-body">
        <!-- 手机端：单日切换 -->
        <template v-if="isMobile">
          <div class="cal-week-nav">
            <button class="week-nav-btn" @click="prevMobileDay">‹ 前一天</button>
            <span class="week-nav-label">{{ mobileDayLabel }}</span>
            <button class="week-nav-btn" @click="nextMobileDay">后一天 ›</button>
          </div>
          <div v-if="mobileCell" class="cal-day">
            <CalendarDayEditor
              :date="mobileCell.date"
              :day-num="mobileCell.dayNum"
              :in-month="mobileCell.inMonth"
              :is-today="mobileCell.date === todayStr"
              :net="mobileCell.net"
              :lines="mobileCell.lines"
              :habit-done="mobileCell.habitDone"
              :habit-total="mobileCell.habitTotal"
              @change="onEdit(mobileCell.date)"
              @dayclick="openHabitPanel(mobileCell.date)"
            />
          </div>
          <div class="cal-day-actions">
            <button class="day-action-btn" @click="writeDaily(mobileCell.date)">写日报</button>
          </div>
        </template>

        <!-- 桌面端：整月多周 -->
        <template v-else>
          <div v-for="(week, wi) in weeks" :key="wi" class="cal-week">
            <!-- 周计划：周一左边一列，按该周周一保存 -->
            <div class="cal-weekplan">
              <span class="cal-weekplan-label">第 {{ wi + 1 }} 周</span>
              <textarea
                :value="weekNotes[week[0].date] ?? ''"
                class="cal-weekplan-input"
                placeholder="周计划…"
                spellcheck="false"
                @input="onWeekInput(week[0].date, $event)"
              ></textarea>
            </div>
            <CalendarDayEditor
              v-for="cell in week"
              :key="cell.date"
              :date="cell.date"
              :day-num="cell.dayNum"
              :in-month="cell.inMonth"
              :is-today="cell.date === todayStr"
              :net="cell.net"
              :lines="linesOf(cell.date)"
              :habit-done="habitMap[cell.date]?.done"
              :habit-total="habitMap[cell.date]?.total"
              @change="onEdit(cell.date)"
              @dayclick="openHabitPanel(cell.date)"
            />
          </div>
        </template>
      </div>
    </div>
    </div>

    </div>

    <!-- 右侧抽屉：习惯 + 专注计时（点右缘标签拉出，不再占据日历主区域的布局） -->
    <button class="side-tab" type="button" title="习惯 / 计时" @click="sideOpen = true">习惯 · 计时</button>
    <el-drawer v-model="sideOpen" direction="rtl" size="300px" :with-header="false">
      <aside class="home-side">
        <section class="hs-card">
          <div class="hs-card-head">
            <span class="hs-card-title">今日习惯</span>
            <span class="hs-card-num">{{ habitDoneCount }}/{{ habitExpectedCount }}</span>
          </div>
          <div class="hs-bar"><span :style="{ width: habitPct + '%' }"></span></div>
          <ul v-if="todayHabitList.length" class="hs-habit-list">
            <li
              v-for="h in todayHabitList"
              :key="h.habit.id"
              class="hs-habit"
              :class="{ done: h.done, muted: !h.expected }"
              @click="quickToggleHabit(h)"
            >
              <span class="hs-habit-emoji">{{ h.habit.emoji }}</span>
              <span class="hs-habit-name">{{ h.habit.name }}</span>
              <span class="hs-habit-streak" v-if="h.expected">连续</span>
              <span class="hs-habit-check">{{ h.done ? '✓' : '' }}</span>
            </li>
          </ul>
          <p v-else class="hs-card-empty">今天没有需要打卡的习惯</p>
          <RouterLink class="hs-card-more" to="/habit">管理习惯 →</RouterLink>
        </section>

        <section class="hs-card">
          <div class="hs-card-head">
            <span class="hs-card-title">专注计时</span>
            <RouterLink class="hs-card-link" to="/timer">全部 →</RouterLink>
          </div>
          <ul v-if="focusTimers.length" class="hs-timer-list">
            <li v-for="t in focusTimers" :key="t.id" class="hs-timer">
              <span class="hs-timer-title">{{ t.title }}</span>
              <span class="hs-timer-type">{{ timerLabel(t) }}</span>
              <span v-if="t.status === 'paused'" class="hs-timer-go" @click="quickStartTimer(t.id)">继续</span>
              <span v-else class="hs-timer-live">进行中</span>
            </li>
          </ul>
          <p v-else class="hs-card-empty">当前没有进行中的计时</p>
          <RouterLink class="hs-card-more" to="/timer">新建计时 →</RouterLink>
        </section>
      </aside>
    </el-drawer>

    <!-- 习惯日期打卡面板（红色） -->
    <el-dialog v-model="panelVisible" width="90%">
      <div class="habit-panel">
        <div class="hp-date">🔴 {{ panelDate }} 习惯打卡</div>
        <div
          v-for="h in panelHabits"
          :key="h.habit.id"
          class="hp-item"
          :class="{ muted: !h.expected }"
        >
          <span class="hp-emoji">{{ h.habit.emoji }}</span>
          <span class="hp-name">{{ h.habit.name }}</span>
          <span
            class="hp-check"
            :class="{ on: h.done }"
            :title="h.done ? '取消打卡' : '打卡'"
            @click="togglePanelHabit(h)"
          >{{ h.done ? '✓' : '' }}</span>
        </div>
        <div v-if="!panelHabits.length" class="hp-empty">这一天还没有创建任何习惯</div>
      </div>
    </el-dialog>

    <!-- 打卡成功庆祝弹窗（与「习惯」页一致） -->
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
