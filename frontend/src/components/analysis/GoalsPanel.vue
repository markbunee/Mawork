<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  checkinGoal,
  createGoal,
  createKeyResult,
  deleteGoal,
  deleteKeyResult,
  goalCategoryHints,
  listGoalLogs,
  listGoals,
  listKeyResults,
  keyResultsByWeek,
  updateGoal,
  updateKeyResult,
  type Goal,
  type GoalIn,
  type GoalLog,
  type GoalRollup,
  type KeyResult,
  type KeyResultIn,
} from '@/api/insight'

const goals = ref<Goal[]>([])
const archived = ref(false)
const loading = ref(false)

// 周计划联动：本周挂载的关键结果（目标 → KR → 周计划 的最后一环）
const weekKey = ref('')
const weekKRs = ref<KeyResult[]>([])

// 表单
const formOpen = ref(false)
const editingId = ref<number | null>(null)
const form = ref<GoalIn>({
  title: '',
  category: '存钱',
  metric: '元',
  start_value: 0,
  target: 0,
  current: 0,
  deadline: '',
  note: '',
})

// 推进
const checkinOpen = ref(false)
const checkinTarget = ref<Goal | null>(null)
const checkinForm = ref({ delta: 0, note: '', log_date: todayStr() })

// 日志
const logsOpen = ref(false)
const logsTitle = ref('')
const logs = ref<GoalLog[]>([])

function todayStr(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function daysLeft(deadline: string): number | null {
  if (!deadline) return null
  const a = new Date(`${deadline}T00:00:00`).getTime()
  const b = new Date(`${todayStr()}T00:00:00`).getTime()
  return Math.round((a - b) / 86400000)
}

const activeCount = computed(() => goals.value.filter((g) => !g.archived).length)
const doneCount = computed(() => goals.value.filter((g) => g.done && !g.archived).length)

async function load() {
  loading.value = true
  try {
    const res = await listGoals(archived.value)
    goals.value = res.goals
    // 本周 KR 失败不阻塞目标列表
    try {
      const wk = await keyResultsByWeek()
      weekKey.value = wk.week
      weekKRs.value = wk.items
    } catch {
      weekKRs.value = []
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.value = {
    title: '',
    category: '存钱',
    metric: '元',
    start_value: 0,
    target: 0,
    current: 0,
    deadline: '',
    note: '',
  }
  formOpen.value = true
}

function openEdit(g: Goal) {
  editingId.value = g.id
  form.value = {
    title: g.title,
    category: g.category,
    metric: g.metric,
    start_value: g.start_value,
    target: g.target,
    current: g.current,
    deadline: g.deadline,
    note: g.note,
  }
  formOpen.value = true
}

async function submitForm() {
  if (!form.value.title?.trim()) {
    ElMessage.warning('请填写目标名')
    return
  }
  if (!form.value.target) {
    ElMessage.warning('请填写目标值')
    return
  }
  try {
    if (editingId.value) {
      await updateGoal(editingId.value, form.value)
      ElMessage.success('已更新')
    } else {
      await createGoal(form.value)
      ElMessage.success('已创建')
    }
    formOpen.value = false
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  }
}

function openCheckin(g: Goal) {
  checkinTarget.value = g
  checkinForm.value = { delta: 0, note: '', log_date: todayStr() }
  checkinOpen.value = true
}

async function submitCheckin() {
  if (!checkinTarget.value) return
  try {
    await checkinGoal(checkinTarget.value.id, checkinForm.value)
    ElMessage.success('已记录推进')
    checkinOpen.value = false
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '推进失败')
  }
}

async function openLogs(g: Goal) {
  try {
    const res = await listGoalLogs(g.id)
    logs.value = res.logs
    logsTitle.value = g.title
    logsOpen.value = true
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  }
}

async function toggleArchive(g: Goal) {
  try {
    await updateGoal(g.id, { archived: !g.archived })
    ElMessage.success(g.archived ? '已恢复' : '已归档')
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  }
}

async function remove(g: Goal) {
  try {
    await ElMessageBox.confirm(`确定删除目标「${g.title}」吗？推进记录会一并删除。`, '删除目标', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteGoal(g.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

// ---------------------------------------------------------------------------
// 关键结果 KR（横切能力 E7）：目标 → KR → 周计划
// ---------------------------------------------------------------------------
const krOpen = ref(false)
const krGoal = ref<Goal | null>(null)
const krRollup = ref<GoalRollup | null>(null)
const krLoading = ref(false)
const krEditingId = ref<number | null>(null)
const krForm = ref<KeyResultIn>(blankKR())

function blankKR(): KeyResultIn {
  return {
    title: '',
    metric: krGoal.value?.metric ?? '',
    start_value: 0,
    target: 0,
    current: 0,
    weight: 1,
    week: '',
    deadline: '',
    note: '',
  }
}

async function reloadKR() {
  if (!krGoal.value) return
  krRollup.value = await listKeyResults(krGoal.value.id)
}

async function openKR(g: Goal) {
  krGoal.value = g
  krEditingId.value = null
  krForm.value = blankKR()
  krOpen.value = true
  krLoading.value = true
  try {
    krRollup.value = await listKeyResults(g.id)
  } catch {
    ElMessage.error('加载关键结果失败')
  } finally {
    krLoading.value = false
  }
}

async function submitKR() {
  if (!krGoal.value) return
  if (!krForm.value.title?.trim()) {
    ElMessage.warning('请填写关键结果名')
    return
  }
  if (!krForm.value.target) {
    ElMessage.warning('请填写目标值')
    return
  }
  try {
    if (krEditingId.value) {
      await updateKeyResult(krEditingId.value, krForm.value)
      ElMessage.success('已更新')
    } else {
      await createKeyResult(krGoal.value.id, krForm.value)
      ElMessage.success('已添加')
    }
    krEditingId.value = null
    krForm.value = blankKR()
    await reloadKR()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  }
}

function editKR(k: KeyResult) {
  krEditingId.value = k.id
  krForm.value = {
    title: k.title,
    metric: k.metric,
    start_value: k.start_value,
    target: k.target,
    current: k.current,
    weight: k.weight,
    week: k.week,
    deadline: k.deadline,
    note: k.note,
  }
}

async function removeKR(k: KeyResult) {
  try {
    await ElMessageBox.confirm(`删除关键结果「${k.title}」？`, '删除关键结果', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await deleteKeyResult(k.id)
  ElMessage.success('已删除')
  if (krEditingId.value === k.id) {
    krEditingId.value = null
    krForm.value = blankKR()
  }
  await reloadKR()
}

onMounted(load)
defineExpose({ load })
</script>

<template>
  <div class="an-goals">
    <div class="an-goals-head">
      <div class="an-goals-stat">
        进行中 <b>{{ activeCount }}</b> · 已达成 <b>{{ doneCount }}</b>
      </div>
      <div class="an-goals-actions">
        <label class="an-switch">
          <input v-model="archived" type="checkbox" @change="load" />
          <span>显示已归档</span>
        </label>
        <button class="an-btn primary" @click="openCreate">＋ 新建目标</button>
      </div>
    </div>

    <!-- 周计划联动：本周要推进的关键结果 -->
    <div v-if="weekKRs.length" class="an-week-kr">
      <div class="an-week-kr-head">
        本周关键结果<span class="an-week-kr-key">{{ weekKey }}</span>
      </div>
      <div v-for="k in weekKRs" :key="k.id" class="an-week-kr-item">
        <span class="an-week-kr-title">{{ k.title }}</span>
        <span class="an-week-kr-goal">{{ k.goal_title || '目标' }}</span>
        <span class="an-week-kr-pct">{{ Math.round(k.pct) }}%</span>
      </div>
    </div>

    <div v-if="loading && !goals.length" class="an-loading">加载中…</div>
    <div v-else-if="!goals.length" class="an-empty-box">
      还没有目标。设定「存钱 / 读书 / 减重 / 专注」之类的 KPI，这里会显示进度环。
    </div>

    <div v-else class="an-goal-grid">
      <div v-for="g in goals" :key="g.id" class="an-goal" :class="{ dim: g.archived, reached: g.done }">
        <div
          class="an-ring"
          :style="{ '--p': g.pct }"
        >
          <span class="an-ring-num">{{ Math.round(g.pct) }}<i>%</i></span>
        </div>
        <div class="an-goal-body">
          <div class="an-goal-title">
            <span class="an-goal-cat">{{ g.category || '目标' }}</span>
            {{ g.title }}
            <span v-if="g.done" class="an-goal-badge">已达成</span>
            <span v-else-if="g.archived" class="an-goal-badge muted">已归档</span>
          </div>
          <div class="an-goal-metric">
            <b>{{ g.current }}</b><span class="sep">/</span>{{ g.target }}{{ g.metric }}
            <span v-if="daysLeft(g.deadline) !== null" class="an-goal-ddl" :class="{ near: (daysLeft(g.deadline) ?? 99) <= 7 && !g.done }">
              · 截止 {{ g.deadline }}（剩 {{ daysLeft(g.deadline) }} 天）
            </span>
          </div>
          <p v-if="g.note" class="an-goal-note">{{ g.note }}</p>
          <div class="an-goal-ops">
            <button class="an-btn" @click="openKR(g)">关键结果</button>
            <button class="an-btn" @click="openCheckin(g)">推进</button>
            <button class="an-btn" @click="openLogs(g)">记录</button>
            <button class="an-btn" @click="openEdit(g)">编辑</button>
            <button class="an-btn" @click="toggleArchive(g)">{{ g.archived ? '恢复' : '归档' }}</button>
            <button class="an-btn danger" @click="remove(g)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 新建 / 编辑 -->
    <el-dialog v-model="formOpen" :title="editingId ? '编辑目标' : '新建目标'" width="92%">
      <div class="an-form">
        <label class="an-field">
          <span>目标名</span>
          <input v-model="form.title" placeholder="如：年底前存下旅行基金" />
        </label>
        <div class="an-field-row">
          <label class="an-field">
            <span>分类</span>
            <select v-model="form.category">
              <option v-for="c in goalCategoryHints" :key="c" :value="c">{{ c }}</option>
            </select>
          </label>
          <label class="an-field">
            <span>单位</span>
            <input v-model="form.metric" placeholder="元 / 本 / kg / 小时" />
          </label>
        </div>
        <div class="an-field-row">
          <label class="an-field">
            <span>起始值</span>
            <input v-model.number="form.start_value" type="number" step="0.01" />
          </label>
          <label class="an-field">
            <span>目标值</span>
            <input v-model.number="form.target" type="number" step="0.01" />
          </label>
          <label class="an-field">
            <span>当前值</span>
            <input v-model.number="form.current" type="number" step="0.01" />
          </label>
        </div>
        <label class="an-field">
          <span>截止日</span>
          <input v-model="form.deadline" type="date" />
        </label>
        <label class="an-field">
          <span>备注</span>
          <textarea v-model="form.note" rows="2" placeholder="为什么这个目标重要？"></textarea>
        </label>
        <p class="an-form-tip">反向目标（如「减重 78 → 70kg」）：起始值大于目标值即可，进度自动反向计算。</p>
      </div>
      <template #footer>
        <button class="an-btn" @click="formOpen = false">取消</button>
        <button class="an-btn primary" @click="submitForm">保存</button>
      </template>
    </el-dialog>

    <!-- 推进 -->
    <el-dialog v-model="checkinOpen" title="记录推进" width="92%">
      <div v-if="checkinTarget" class="an-form">
        <p class="an-checkin-title">
          {{ checkinTarget.title }}：当前 {{ checkinTarget.current }}{{ checkinTarget.metric }}，
          距目标还差 {{ checkinTarget.remaining }}{{ checkinTarget.metric }}
        </p>
        <div class="an-field-row">
          <label class="an-field">
            <span>推进量</span>
            <input v-model.number="checkinForm.delta" type="number" step="0.01" placeholder="可为负数" />
          </label>
          <label class="an-field">
            <span>日期</span>
            <input v-model="checkinForm.log_date" type="date" />
          </label>
        </div>
        <label class="an-field">
          <span>说明</span>
          <input v-model="checkinForm.note" placeholder="这次推进来自哪里？" />
        </label>
      </div>
      <template #footer>
        <button class="an-btn" @click="checkinOpen = false">取消</button>
        <button class="an-btn primary" @click="submitCheckin">记录</button>
      </template>
    </el-dialog>

    <!-- 关键结果 KR（横切能力 E7） -->
    <el-dialog v-model="krOpen" :title="`关键结果 · ${krGoal?.title ?? ''}`" width="92%">
      <div v-if="krGoal" class="an-kr">
        <div class="an-kr-head">
          <span v-if="krRollup && krRollup.kr_count">
            加权汇总进度 <b>{{ krRollup.pct }}%</b>（{{ krRollup.kr_count }} 项 KR）
          </span>
          <span v-else>还没有关键结果，先加一条 KR 吧</span>
        </div>

        <div v-if="krLoading" class="an-empty">加载中…</div>
        <ul v-else-if="krRollup?.krs.length" class="an-kr-list">
          <li v-for="k in krRollup.krs" :key="k.id">
            <div class="an-kr-main">
              <span class="an-kr-title">{{ k.title }}</span>
              <span class="an-kr-metric">
                {{ k.current }}/{{ k.target }}{{ k.metric }} · {{ Math.round(k.pct) }}%
              </span>
            </div>
            <div class="an-kr-bar">
              <div class="an-kr-fill" :style="{ width: Math.min(100, Math.max(0, k.pct)) + '%' }"></div>
            </div>
            <div class="an-kr-meta">
              <span v-if="k.week">周计划 {{ k.week }}</span>
              <span v-if="k.deadline">截止 {{ k.deadline }}</span>
              <span>权重 {{ k.weight }}</span>
            </div>
            <div class="an-kr-ops">
              <button class="an-btn" @click="editKR(k)">编辑</button>
              <button class="an-btn danger" @click="removeKR(k)">删除</button>
            </div>
          </li>
        </ul>
        <p v-else class="an-empty">还没有关键结果</p>

        <div class="an-kr-form">
          <div class="an-kr-form-title">{{ krEditingId ? '编辑关键结果' : '新增关键结果' }}</div>
          <label class="an-field">
            <span>关键结果</span>
            <input v-model="krForm.title" placeholder="如：每月定投 2000 元" />
          </label>
          <div class="an-field-row">
            <label class="an-field">
              <span>起始值</span>
              <input v-model.number="krForm.start_value" type="number" step="0.01" />
            </label>
            <label class="an-field">
              <span>目标值</span>
              <input v-model.number="krForm.target" type="number" step="0.01" />
            </label>
            <label class="an-field">
              <span>当前值</span>
              <input v-model.number="krForm.current" type="number" step="0.01" />
            </label>
          </div>
          <div class="an-field-row">
            <label class="an-field">
              <span>单位</span>
              <input v-model="krForm.metric" placeholder="元 / 本 / kg" />
            </label>
            <label class="an-field">
              <span>权重</span>
              <input v-model.number="krForm.weight" type="number" step="0.1" />
            </label>
            <label class="an-field">
              <span>周计划 (YYYY-Www)</span>
              <input v-model="krForm.week" placeholder="如 2026-W38" />
            </label>
          </div>
          <label class="an-field">
            <span>截止日</span>
            <input v-model="krForm.deadline" type="date" />
          </label>
          <label class="an-field">
            <span>备注</span>
            <textarea v-model="krForm.note" rows="2" placeholder="衡量标准 / 数据来源"></textarea>
          </label>
          <div class="an-kr-ops">
            <button v-if="krEditingId" class="an-btn" @click="krEditingId = null; krForm = blankKR()">
              取消编辑
            </button>
            <button class="an-btn primary" @click="submitKR">
              {{ krEditingId ? '保存' : '添加' }}
            </button>
          </div>
        </div>
      </div>
      <template #footer>
        <button class="an-btn" @click="krOpen = false">关闭</button>
      </template>
    </el-dialog>

    <!-- 推进记录 -->
    <el-dialog v-model="logsOpen" :title="`推进记录 · ${logsTitle}`" width="92%">
      <ul v-if="logs.length" class="an-logs">
        <li v-for="l in logs" :key="l.id">
          <span class="an-log-date">{{ l.log_date }}</span>
          <span class="an-log-delta" :class="{ minus: l.delta < 0 }">{{ l.delta > 0 ? '+' : '' }}{{ l.delta }}</span>
          <span class="an-log-value">→ {{ l.value }}</span>
          <span class="an-log-note">{{ l.note }}</span>
        </li>
      </ul>
      <p v-else class="an-empty">还没有推进记录</p>
    </el-dialog>
  </div>
</template>
