<script setup lang="ts">
import { computed, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import { ElMessage } from 'element-plus'
import { getReview, type ReviewResult, type ReviewScope } from '@/api/insight'
import { saveFile } from '@/api/analysis'
import { iso } from '@/utils/dateRange'

const md = new MarkdownIt({ html: false, linkify: true })

const scopeLabels: Record<ReviewScope, string> = {
  week: '周复盘',
  month: '月复盘',
  quarter: '季复盘',
  year: '年复盘',
}
const scopeList = (Object.keys(scopeLabels) as ReviewScope[]).map((k) => ({
  key: k,
  label: scopeLabels[k],
}))

const scope = ref<ReviewScope>('week')
const anchor = ref(iso(new Date()))
const result = ref<ReviewResult | null>(null)
const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)
const content = ref('')
const viewMode = ref<'code' | 'preview'>('preview')

const rendered = computed(() => md.render(content.value))

/** 按 scope 切换锚点时给出可读的区间提示 */
const anchorHint = computed(() => {
  const d = new Date(`${anchor.value}T00:00:00`)
  if (scope.value === 'week') {
    const dow = d.getDay()
    const mon = new Date(d.getFullYear(), d.getMonth(), d.getDate() - (dow === 0 ? 6 : dow - 1))
    const sun = new Date(mon.getFullYear(), mon.getMonth(), mon.getDate() + 6)
    return `所在周：${iso(mon)} ~ ${iso(sun)}`
  }
  if (scope.value === 'month') return `所在月：${anchor.value.slice(0, 7)}`
  if (scope.value === 'quarter') return `所在季：Q${Math.floor(d.getMonth() / 3) + 1}`
  return `所在年：${anchor.value.slice(0, 4)}`
})

const emit = defineEmits<{ (e: 'saved'): void }>()

async function generate() {
  loading.value = true
  try {
    const r = await getReview(scope.value, anchor.value)
    result.value = r
    content.value = r.content
    dirty.value = false
    viewMode.value = 'preview'
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '生成失败')
  } finally {
    loading.value = false
  }
}

async function saveToLibrary() {
  const r = result.value
  if (!r) return
  if (!confirm(`保存到报告库：${r.folder}/${r.filename}\n若已存在同名文件将被覆盖，确定吗？`)) return
  saving.value = true
  try {
    await saveFile(`${r.folder}/${r.filename}`, content.value)
    dirty.value = false
    ElMessage.success('已保存到报告库')
    emit('saved')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  } finally {
    saving.value = false
  }
}

function shift(dir: number) {
  const d = new Date(`${anchor.value}T00:00:00`)
  const map: Record<ReviewScope, number> = { week: 7, month: 1, quarter: 3, year: 1 }
  if (scope.value === 'month' || scope.value === 'quarter') {
    d.setMonth(d.getMonth() + dir * map[scope.value])
  } else if (scope.value === 'year') {
    d.setFullYear(d.getFullYear() + dir)
  } else {
    d.setDate(d.getDate() + dir * map[scope.value])
  }
  anchor.value = iso(d)
}

async function copyText() {
  try {
    await navigator.clipboard.writeText(content.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('浏览器不允许复制，请手动选择文本')
  }
}
</script>

<template>
  <div class="an-review">
    <div class="an-review-bar">
      <div class="an-scopes">
        <button
          v-for="s in scopeList"
          :key="s.key"
          class="an-scope"
          :class="{ on: scope === s.key }"
          @click="scope = s.key"
        >{{ s.label }}</button>
      </div>
      <div class="an-review-nav">
        <button class="an-btn" @click="shift(-1)">‹ 上一期</button>
        <input v-model="anchor" type="date" class="an-date" />
        <span class="an-anchor-hint">{{ anchorHint }}</span>
        <button class="an-btn" @click="shift(1)">下一期 ›</button>
      </div>
      <button class="an-btn primary" :disabled="loading" @click="generate">
        {{ loading ? '生成中…' : '生成复盘' }}
      </button>
    </div>

    <div v-if="!result" class="an-empty-box">
      选择周期后点「生成复盘」，系统会根据这段时间里的<b>记账 / 专注 / 任务 / 习惯 / 日报 / 目标</b>真实数据，
      自动产出一份带提问引导的复盘报告。
    </div>

    <template v-else>
      <div class="an-review-head">
        <div class="an-review-title">{{ result.title }}</div>
        <div class="an-review-ops">
          <span v-if="dirty" class="an-dirty">已修改</span>
          <button
            class="an-btn"
            @click="viewMode = viewMode === 'code' ? 'preview' : 'code'"
          >{{ viewMode === 'code' ? '预览' : '编辑' }}</button>
          <button class="an-btn" @click="copyText">复制</button>
          <button class="an-btn primary" :disabled="saving" @click="saveToLibrary">
            {{ saving ? '保存中…' : '保存到报告库' }}
          </button>
        </div>
      </div>

      <textarea
        v-if="viewMode === 'code'"
        v-model="content"
        class="an-review-input"
        spellcheck="false"
        @input="dirty = true"
      ></textarea>
      <div v-else class="md-body an-review-md" v-html="rendered"></div>
    </template>
  </div>
</template>
