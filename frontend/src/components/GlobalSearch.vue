<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { globalSearch, type SearchItem, type SearchResult } from '@/api/search'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const router = useRouter()
const query = ref('')
const result = ref<SearchResult | null>(null)
const loading = ref(false)
const activeIndex = ref(-1)
const inputEl = ref<HTMLInputElement | null>(null)

let timer: number | undefined

// 打开时聚焦输入框
watch(
  () => props.open,
  (v) => {
    if (v) {
      query.value = ''
      result.value = null
      activeIndex.value = -1
      nextTick(() => inputEl.value?.focus())
    }
  },
)

function runSearch() {
  const q = query.value.trim()
  if (!q) {
    result.value = null
    return
  }
  loading.value = true
  globalSearch(q, 10)
    .then((res) => {
      result.value = res
      activeIndex.value = -1
    })
    .catch(() => {
      result.value = { q, total: 0, groups: [] }
    })
    .finally(() => {
      loading.value = false
    })
}

function onInput() {
  if (timer) window.clearTimeout(timer)
  timer = window.setTimeout(runSearch, 300)
}

// 收集所有结果项，便于键盘上下选择
function flatItems(): SearchItem[] {
  const r = result.value
  if (!r) return []
  return r.groups.flatMap((g) => g.items)
}

function go(item: SearchItem) {
  emit('close')
  router.push({ path: item.route, query: item.query })
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    emit('close')
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    const n = flatItems().length
    if (n) activeIndex.value = (activeIndex.value + 1) % n
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    const n = flatItems().length
    if (n) activeIndex.value = (activeIndex.value - 1 + n) % n
    return
  }
  if (e.key === 'Enter') {
    const items = flatItems()
    if (activeIndex.value >= 0 && items[activeIndex.value]) go(items[activeIndex.value])
    return
  }
}

// 命中高亮：按查询词切分
function highlight(text: string, q: string): { t: string; hit: boolean }[] {
  const query = q.trim()
  if (!query) return [{ t: text, hit: false }]
  const parts: { t: string; hit: boolean }[] = []
  const lower = text.toLowerCase()
  const ql = query.toLowerCase()
  let i = 0
  while (i < text.length) {
    const idx = lower.indexOf(ql, i)
    if (idx < 0) {
      parts.push({ t: text.slice(i), hit: false })
      break
    }
    if (idx > i) parts.push({ t: text.slice(i, idx), hit: false })
    parts.push({ t: text.slice(idx, idx + query.length), hit: true })
    i = idx + query.length
  }
  return parts
}

// 全局序号 → 用于高亮当前选中项
function globalIndex(groupIdx: number, itemIdx: number): number {
  const r = result.value
  if (!r) return -1
  let base = 0
  for (let g = 0; g < groupIdx; g++) base += r.groups[g].items.length
  return base + itemIdx
}
</script>

<template>
  <div v-if="open" class="gs-mask" @click.self="emit('close')">
    <div class="gs-panel" role="dialog" aria-label="全局搜索">
      <div class="gs-bar">
        <span class="gs-icon">🔍</span>
        <input
          ref="inputEl"
          v-model="query"
          class="gs-input"
          type="text"
          placeholder="搜索日报 / 文章 / 记账 / 日程 / 计时 / 资料…"
          @input="onInput"
          @keydown="onKeydown"
        />
        <button class="gs-close" title="关闭 (Esc)" @click="emit('close')">✕</button>
      </div>

      <div class="gs-body">
        <div v-if="loading" class="gs-tip">搜索中…</div>
        <div v-else-if="!query.trim()" class="gs-tip">输入关键词，跨全部模块检索</div>
        <div v-else-if="result && result.total === 0" class="gs-tip">
          没有匹配「{{ query }}」的结果
        </div>

        <template v-else-if="result">
          <div v-for="(g, gi) in result.groups" :key="g.module" class="gs-group">
            <div class="gs-group-label">{{ g.label }} <span class="gs-group-n">{{ g.items.length }}</span></div>
            <button
              v-for="(item, ii) in g.items"
              :key="item.id"
              class="gs-item"
              :class="{ on: globalIndex(gi, ii) === activeIndex }"
              @click="go(item)"
              @mousemove="activeIndex = globalIndex(gi, ii)"
            >
              <div class="gs-item-title">
                <template v-for="(p, i) in highlight(item.title, query)" :key="i">
                  <mark v-if="p.hit">{{ p.t }}</mark><template v-else>{{ p.t }}</template>
                </template>
              </div>
              <div class="gs-item-sub">{{ item.subtitle }}</div>
              <div v-if="item.snippet" class="gs-item-snippet">
                <template v-for="(p, i) in highlight(item.snippet, query)" :key="i">
                  <mark v-if="p.hit">{{ p.t }}</mark><template v-else>{{ p.t }}</template>
                </template>
              </div>
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
