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
import CalendarDayEditor from '@/components/home/CalendarDayEditor.vue'

const viewYear = ref(new Date().getFullYear())
const viewMonth = ref(new Date().getMonth() + 1)

const days = ref<Record<string, CalLine[]>>({})
const dailyNet = ref<Record<string, number>>({})

// 月度计划（按月）与周计划（按该周周一），均为用户自由书写
const monthNote = ref('')
const weekNotes = ref<Record<string, string>>({})

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
    }, 700),
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
    }, 700),
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
    const res = await saveCalDay(
      date,
      lines.map((l) => ({ kind: l.kind, text: l.text, done: l.done })),
    )
    // 回填服务端 id，保持 :key 稳定，避免输入过程中重渲染丢焦点
    res.lines.forEach((l, i) => {
      if (lines[i]) lines[i].id = l.id
    })
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
  await flushPending()
  const { from, to } = visibleRange.value
  try {
    const [cal, net, mn, wn] = await Promise.all([
      listCalDays(from, to),
      getDailyNet(String(viewYear.value), String(viewMonth.value).padStart(2, '0')),
      getMonthNote(monthKey.value),
      listWeekNotes(from, to),
    ])
    days.value = cal.days
    dailyNet.value = net.daily
    monthNote.value = mn.content
    weekNotes.value = { ...wn.notes }
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

onMounted(load)
onBeforeUnmount(() => {
  void flushPending()
})
</script>

<template>
  <div class="home">
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
            @change="onEdit(cell.date)"
          />
        </div>
      </div>
    </div>
  </div>
</template>
