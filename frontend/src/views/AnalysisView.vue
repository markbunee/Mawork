<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getDashboard, type Dashboard } from '@/api/insight'
import {
  computeRange,
  presetLabels,
  previousRange,
  shiftAnchor,
  type RangePreset,
} from '@/utils/dateRange'
import OverviewTab from '@/components/analysis/OverviewTab.vue'
import TrendTab from '@/components/analysis/TrendTab.vue'
import GoalsPanel from '@/components/analysis/GoalsPanel.vue'
import ReviewPanel from '@/components/analysis/ReviewPanel.vue'
import ReportTree from '@/components/analysis/ReportTree.vue'
import SegmentedControl from '@/components/common/SegmentedControl.vue'

type TabKey = 'overview' | 'trend' | 'goals' | 'review' | 'report'

const tabs: { key: TabKey; label: string; icon: string }[] = [
  { key: 'overview', label: '概览', icon: '📊' },
  { key: 'trend', label: '趋势', icon: '📈' },
  { key: 'goals', label: '目标', icon: '🎯' },
  { key: 'review', label: '复盘', icon: '🪞' },
  { key: 'report', label: '报告库', icon: '📁' },
]

const tab = ref<TabKey>('overview')
const TAB_KEY = 'mawork:analysis:tab'

const presetList = (Object.keys(presetLabels) as RangePreset[]).map((k) => ({
  key: k,
  label: presetLabels[k],
}))

const preset = ref<RangePreset>('week')
const anchor = ref<Date>(new Date())
const custom = ref(false)
const from = ref('')
const to = ref('')

const data = ref<Dashboard | null>(null)
const prev = ref<Dashboard | null>(null)
const loading = ref(false)
const reportRef = ref<InstanceType<typeof ReportTree> | null>(null)
const goalsRef = ref<InstanceType<typeof GoalsPanel> | null>(null)

const range = computed(() =>
  custom.value && from.value && to.value
    ? {
        from: from.value,
        to: to.value,
        label: `${from.value} ~ ${to.value}`,
      }
    : computeRange(preset.value, anchor.value),
)

function applyPreset(p: RangePreset) {
  preset.value = p
  custom.value = false
  anchor.value = new Date()
}

function shift(dir: number) {
  anchor.value = shiftAnchor(preset.value, anchor.value, dir)
}

function useTodayAnchor() {
  anchor.value = new Date()
}

async function load() {
  if (tab.value === 'goals' || tab.value === 'report' || tab.value === 'review') return
  loading.value = true
  try {
    const r = range.value
    const prevR = previousRange(preset.value, anchor.value)
    const [cur, before] = await Promise.all([
      getDashboard(r.from, r.to),
      getDashboard(prevR.from, prevR.to),
    ])
    data.value = cur
    prev.value = before
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

async function onReviewSaved() {
  tab.value = 'report'
  await nextTick()
  await reportRef.value?.reload()
}


function onCustomChange() {
  if (from.value && to.value && from.value <= to.value) {
    custom.value = true
  }
}

watch([tab, () => range.value.from, () => range.value.to], load)
// post-flush：等 DOM 打补丁后再拿 reportRef，否则切到报告库时 ref 仍为 null
watch(
  tab,
  (t) => {
    try {
      localStorage.setItem(TAB_KEY, t)
    } catch {
      /* 忽略存储异常 */
    }
    if (t === 'report') void reportRef.value?.reload()
    if (t === 'goals') void goalsRef.value?.load()
  },
  { flush: 'post' },
)

onMounted(() => {
  try {
    const saved = localStorage.getItem(TAB_KEY)
    if (saved === 'overview' || saved === 'trend' || saved === 'goals' || saved === 'review' || saved === 'report') {
      tab.value = saved
    }
  } catch {
    /* 忽略存储异常 */
  }
  const r = computeRange('week', anchor.value)
  from.value = r.from
  to.value = r.to
  void load()
  // 初次若停在报告库 tab，等一帧让 ReportTree 挂载后再初始化
  void nextTick().then(() => reportRef.value?.init())
})
</script>

<template>
  <div class="an">
    <!-- 时间维度 -->
    <div class="an-range">
      <div class="an-presets">
        <button
          v-for="p in presetList"
          :key="p.key"
          class="an-preset"
          :class="{ on: !custom && preset === p.key }"
          @click="applyPreset(p.key)"
        >{{ p.label }}</button>
      </div>

      <div class="an-range-nav">
        <button class="an-btn" title="上一区间" @click="shift(-1)">‹</button>
        <input
          v-model="from"
          type="date"
          class="an-date"
          @change="onCustomChange"
        />
        <span class="an-range-sep">~</span>
        <input v-model="to" type="date" class="an-date" @change="onCustomChange" />
        <button class="an-btn" title="下一区间" @click="shift(1)">›</button>
        <button class="an-btn" @click="useTodayAnchor">今天</button>
        <button class="an-btn primary" :disabled="loading" @click="load">
          {{ loading ? '汇总中…' : '重新汇总' }}
        </button>
      </div>

      <div class="an-range-label">{{ range.label }}</div>
    </div>

    <!-- Tab：通用分段控件（指示块宽度按项数自动计算） -->
    <div class="an-tabs-bar">
      <SegmentedControl v-model="tab" :items="tabs" aria-label="复盘模块切换" />
    </div>

    <div class="an-body">
      <OverviewTab v-if="tab === 'overview'" :data="data" :prev="prev" :loading="loading" />
      <TrendTab v-else-if="tab === 'trend'" :data="data" />
      <GoalsPanel v-else-if="tab === 'goals'" ref="goalsRef" />
      <ReviewPanel v-else-if="tab === 'review'" @saved="onReviewSaved" />
      <ReportTree v-else ref="reportRef" />
    </div>

    <!-- workspaces 备份列表 / 一键回滚 -->
  </div>
</template>

<style scoped>
/* 备份/导出入口已下线，此处只剩分段控件本身 */
.an-tabs-bar {
  display: flex;
  align-items: center;
  margin-bottom: 14px;
}
</style>
