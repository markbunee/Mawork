<script setup lang="ts">
import { computed } from 'vue'
import { fmtMoney, fmtSec, type Dashboard } from '@/api/insight'

const props = defineProps<{
  data: Dashboard | null
  /** 上一等长区间，用于环比 */
  prev: Dashboard | null
  loading: boolean
}>()

interface Metric {
  key: string
  icon: string
  label: string
  value: string
  unit?: string
  sub: string
  tone: 'neutral' | 'up' | 'down' | 'habit'
  /** 环比：当前值与基准值之差的百分比 */
  delta: number | null
}

function pctDelta(cur: number, base: number): number | null {
  if (!Number.isFinite(cur) || !Number.isFinite(base) || base === 0) return null
  return Math.round(((cur - base) / Math.abs(base)) * 100)
}

const metrics = computed<Metric[]>(() => {
  const d = props.data
  if (!d) return []
  const p = props.prev
  const f = d.finance
  return [
    {
      key: 'net',
      icon: '💰',
      label: '收支结余',
      value: fmtMoney(f.net),
      unit: '元',
      sub: `收 ${f.income.toFixed(0)} · 支 ${f.expense.toFixed(0)}`,
      tone: f.net >= 0 ? 'up' : 'down',
      delta: p ? pctDelta(f.net, p.finance.net) : null,
    },
    {
      key: 'focus',
      icon: '⏱',
      label: '专注时长',
      value: fmtSec(d.focus.total_sec),
      sub: `${d.focus.sessions} 个时段`,
      tone: 'neutral',
      delta: p ? pctDelta(d.focus.total_sec, p.focus.total_sec) : null,
    },
    {
      key: 'task',
      icon: '📋',
      label: '任务完成率',
      value: `${d.tasks.done_rate}`,
      unit: '%',
      sub: `${d.tasks.done}/${d.tasks.total} 项 · 均完成度 ${d.tasks.avg_completion}%`,
      tone: 'neutral',
      delta: p ? pctDelta(d.tasks.done_rate, p.tasks.done_rate) : null,
    },
    {
      key: 'habit',
      icon: '🔴',
      label: '习惯达标率',
      value: `${d.habits.rate}`,
      unit: '%',
      sub: `${d.habits.done}/${d.habits.expected} 次打卡`,
      tone: 'habit',
      delta: p ? pctDelta(d.habits.rate, p.habits.rate) : null,
    },
    {
      key: 'writing',
      icon: '📝',
      label: '日报写作',
      value: `${d.writing.days}`,
      unit: '篇',
      sub: `连续 ${d.writing.streak} 天 · ${d.writing.total_chars} 字`,
      tone: 'neutral',
      delta: p ? pctDelta(d.writing.days, p.writing.days) : null,
    },
    {
      key: 'review',
      icon: '🪞',
      label: '复盘完成度',
      value: `${d.writing.complete_rate}`,
      unit: '%',
      sub: `${d.writing.complete_days}/${d.writing.days} 篇三段齐全`,
      tone: 'neutral',
      delta: p ? pctDelta(d.writing.complete_rate, p.writing.complete_rate) : null,
    },
  ]
})

const topTags = computed(() => (props.data?.writing.tags ?? []).slice(0, 14))
const maxTag = computed(() => Math.max(1, ...topTags.value.map((t) => t.count)))
</script>

<template>
  <div class="an-overview">
    <div v-if="loading && !data" class="an-loading">正在汇总数据…</div>

    <template v-else-if="data">
      <!-- 量化卡 -->
      <div class="an-cards">
        <div
          v-for="m in metrics"
          :key="m.key"
          class="an-card"
          :class="`tone-${m.tone}`"
        >
          <div class="an-card-head">
            <span class="an-card-icon">{{ m.icon }}</span>
            <span class="an-card-label">{{ m.label }}</span>
            <span v-if="m.delta !== null" class="an-delta" :class="{ up: m.delta > 0, down: m.delta < 0 }">
              {{ m.delta > 0 ? '▲' : m.delta < 0 ? '▼' : '—' }}{{ Math.abs(m.delta) }}%
            </span>
          </div>
          <div class="an-card-value">
            {{ m.value }}<span v-if="m.unit" class="an-card-unit">{{ m.unit }}</span>
          </div>
          <div class="an-card-sub">{{ m.sub }}</div>
        </div>
      </div>

      <!-- 质化区 -->
      <div class="an-qual">
        <section class="an-panel">
          <h3 class="an-panel-title">主题标签</h3>
          <div v-if="topTags.length" class="an-tags">
            <span
              v-for="t in topTags"
              :key="t.tag"
              class="an-tag"
              :style="{ fontSize: 12 + Math.round((t.count / maxTag) * 8) + 'px' }"
            >
              #{{ t.tag }}<i>{{ t.count }}</i>
            </span>
          </div>
          <p v-else class="an-empty">这段时间还没有带 # 标签的记录</p>
        </section>

        <section class="an-panel">
          <h3 class="an-panel-title">支出结构</h3>
          <ul v-if="data.finance.top_expense.length" class="an-bars">
            <li v-for="c in data.finance.top_expense" :key="c.category">
              <div class="an-bar-top">
                <span>{{ c.category }}</span>
                <b>¥{{ c.amount.toFixed(2) }}</b>
              </div>
              <div class="an-bar">
                <i :style="{ width: (c.amount / Math.max(1, data.finance.expense)) * 100 + '%' }"></i>
              </div>
            </li>
          </ul>
          <p v-else class="an-empty">暂无支出</p>
        </section>

        <section class="an-panel">
          <h3 class="an-panel-title">习惯达标</h3>
          <ul v-if="data.habits.items.length" class="an-habits">
            <li v-for="h in data.habits.items" :key="h.id">
              <span class="an-habit-name">{{ h.emoji }} {{ h.name }}</span>
              <span class="an-habit-rate" :class="{ low: h.rate < 60 }">{{ h.rate }}%</span>
              <span class="an-habit-meta">{{ h.done }}/{{ h.expected }} · 🔥{{ h.streak }}</span>
            </li>
          </ul>
          <p v-else class="an-empty">还没有进行中的习惯</p>
        </section>

        <section class="an-panel">
          <h3 class="an-panel-title">专注 Top</h3>
          <ul v-if="data.focus.top_tasks.length" class="an-focus">
            <li v-for="(t, i) in data.focus.top_tasks.slice(0, 5)" :key="t.title">
              <span class="an-rank">{{ i + 1 }}</span>
              <span class="an-focus-name">{{ t.title }}</span>
              <span class="an-focus-time">{{ fmtSec(t.total_sec) }}</span>
            </li>
          </ul>
          <p v-else class="an-empty">还没有专注记录</p>
        </section>

        <section class="an-panel">
          <h3 class="an-panel-title">预算与资产</h3>
          <div v-if="data.finance.budget && data.finance.budget.total.limit > 0" class="an-budget">
            <div class="an-bar-top">
              <span>{{ data.finance.budget.period }} 总预算</span>
              <b :class="{ over: data.finance.budget.total.over }">
                ¥{{ data.finance.budget.total.spent.toFixed(0) }} / {{ data.finance.budget.total.limit.toFixed(0) }}
              </b>
            </div>
            <div class="an-bar">
              <i
                :class="{ over: data.finance.budget.total.over }"
                :style="{ width: Math.min(100, data.finance.budget.total.pct || 0) + '%' }"
              ></i>
            </div>
            <p class="an-budget-tip" :class="{ over: data.finance.budget.total.over }">
              {{ data.finance.budget.total.over ? '⚠️ 已超支' : `剩余 ¥${data.finance.budget.total.remaining.toFixed(2)}` }}
            </p>
          </div>
          <p class="an-asset">资产合计 <b>¥{{ data.finance.accounts_total.toFixed(2) }}</b></p>
          <p class="an-asset muted">本期垫付 <b>¥{{ data.finance.reimburse.toFixed(2) }}</b></p>
          <p class="an-asset muted">未收回垫付 <b>¥{{ data.finance.unreimbursed.toFixed(2) }}</b></p>
        </section>

        <section class="an-panel">
          <h3 class="an-panel-title">写作与结构</h3>
          <div class="an-writing">
            <div class="an-writing-cell">
              <span class="an-writing-num">{{ data.writing.total_chars }}</span>
              <span class="an-writing-cap">累计字数</span>
            </div>
            <div class="an-writing-cell">
              <span class="an-writing-num">{{ data.writing.avg_chars }}</span>
              <span class="an-writing-cap">篇均字数</span>
            </div>
            <div class="an-writing-cell">
              <span class="an-writing-num">{{ data.writing.streak }}</span>
              <span class="an-writing-cap">连续天数</span>
            </div>
            <div class="an-writing-cell">
              <span class="an-writing-num">{{ data.writing.coverage }}%</span>
              <span class="an-writing-cap">写作覆盖</span>
            </div>
          </div>
          <div class="an-progress">
            <span :style="{ width: data.writing.complete_rate + '%' }"></span>
          </div>
          <p class="an-writing-tip">三段（工作 / 问题 / 计划）齐全的日报占比 {{ data.writing.complete_rate }}%</p>
        </section>
      </div>
    </template>
  </div>
</template>
