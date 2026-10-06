<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, watch } from 'vue'
import type { CalLine, CalLineKind } from '@/api/calday'

const props = defineProps<{
  date: string
  dayNum: number
  inMonth: boolean
  isToday: boolean
  net: number | null
  lines: CalLine[]
  habitDone?: number
  habitTotal?: number
}>()

const emit = defineEmits<{ (e: 'change'): void; (e: 'dayclick'): void }>()

// 新建的行先用负数 id 占位；cid 是前端稳定键（服务端每次保存会重建 id，
// 不能用 line.id 作 :key，否则自动保存后整格文本域被销毁重建、丢焦点/跳动）。
let uid = -1
let cidSeq = 0
function nextCid(): string {
  return `c${++cidSeq}`
}
function ensureCid(line: CalLine): string {
  if (!line.cid) line.cid = nextCid()
  return line.cid
}
function newLine(kind: CalLineKind): CalLine {
  const line: CalLine = { id: uid--, date: props.date, sort: 0, kind, text: '', done: false }
  line.cid = nextCid()
  return line
}

const taEls: (HTMLTextAreaElement | null)[] = []
let pendingFocus: number | null = null
let pendingCaret: number | null = null

function setTa(i: number, el: unknown) {
  taEls[i] = (el as HTMLTextAreaElement) ?? null
}

function autoSize(el: HTMLTextAreaElement | null) {
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

function resizeAll() {
  nextTick(() => taEls.forEach(autoSize))
}

function applyPendingFocus() {
  if (pendingFocus === null) return
  const idx = pendingFocus
  const caret = pendingCaret
  pendingFocus = null
  pendingCaret = null
  nextTick(() => {
    const el = taEls[idx]
    if (!el) return
    el.focus()
    const pos = caret === null ? el.value.length : caret
    el.setSelectionRange(pos, pos)
  })
}

// 仅在「结构变化」（增/删行、切换月份）时重算高度与回填焦点；
// 服务端保存会重建 line.id，但不能因此触发（cid 稳定），否则整格刷新、丢焦点。
watch(
  () => {
    props.lines.forEach(ensureCid)
    return props.lines.map((l) => l.cid).join(',')
  },
  () => {
    taEls.length = props.lines.length
    resizeAll()
    applyPendingFocus()
  },
  { immediate: true },
)

function onWindowResize() {
  taEls.forEach(autoSize)
}

onMounted(() => {
  window.addEventListener('resize', onWindowResize)
  resizeAll()
})

onBeforeUnmount(() => window.removeEventListener('resize', onWindowResize))

// ---------------------------------------------------------------------------
// 行操作
// ---------------------------------------------------------------------------
function changed() {
  resizeAll()
  emit('change')
}

function appendLine() {
  props.lines.push(newLine('text'))
  pendingFocus = props.lines.length - 1
  changed()
  applyPendingFocus()
}

function addLineAfter(i: number) {
  const kind: CalLineKind = props.lines[i].kind === 'task' ? 'task' : 'text'
  props.lines.splice(i + 1, 0, newLine(kind))
  pendingFocus = i + 1
  changed()
  applyPendingFocus()
}

function removeLine(i: number) {
  if (props.lines.length <= 1) {
    props.lines[0].text = ''
    changed()
    return
  }
  props.lines.splice(i, 1)
  pendingFocus = Math.max(0, i - 1)
  pendingCaret = taEls[pendingFocus]?.value.length ?? null
  changed()
  applyPendingFocus()
}

/** 行首退格：空行直接删除，非空行并入上一行 */
function mergeUp(i: number, el: HTMLTextAreaElement) {
  if (i === 0) return
  if (!el.value) {
    removeLine(i)
    return
  }
  const prev = props.lines[i - 1]
  const at = prev.text.length
  prev.text += el.value
  props.lines.splice(i, 1)
  pendingFocus = i - 1
  pendingCaret = at
  changed()
  applyPendingFocus()
}

function toTask(line: CalLine) {
  line.kind = 'task'
  line.done = false
  changed()
}

function toText(line: CalLine) {
  line.kind = 'text'
  line.done = false
  changed()
}

function toggleDone(line: CalLine) {
  line.done = !line.done
  changed()
}

// ---------------------------------------------------------------------------
// 输入
// ---------------------------------------------------------------------------
const TASK_PREFIXES: { re: RegExp; done: boolean }[] = [
  { re: /^已完成[-－:：]\s*/, done: true },
  { re: /^未完成[-－:：]\s*/, done: false },
  { re: /^\[x\]\s*/i, done: true },
  { re: /^\[\s?\]\s*/, done: false },
  { re: /^[-*+]\s+/, done: false },
]

/** 行首输入 - / [] / 已完成- 等标记时自动刷成任务 */
function tryBrush(line: CalLine, el: HTMLTextAreaElement) {
  if (line.kind !== 'text') return
  for (const p of TASK_PREFIXES) {
    const m = p.re.exec(line.text)
    if (!m) continue
    line.text = line.text.slice(m[0].length)
    line.kind = 'task'
    line.done = p.done
    nextTick(() => {
      const pos = line.text.length
      el.value = line.text
      autoSize(el)
      el.setSelectionRange(pos, pos)
    })
    return
  }
}

function onInput(line: CalLine, i: number) {
  const el = taEls[i]
  if (!el) return
  autoSize(el)
  tryBrush(line, el)
  changed()
}

function onKeydown(i: number, ev: KeyboardEvent) {
  const el = ev.target as HTMLTextAreaElement
  if (ev.isComposing) return

  if (ev.key === 'Enter' && !ev.shiftKey) {
    ev.preventDefault()
    addLineAfter(i)
    return
  }
  if (ev.key === 'Backspace' && i > 0 && el.selectionStart === 0 && el.selectionEnd === 0) {
    ev.preventDefault()
    mergeUp(i, el)
    return
  }
  if (ev.key === 'ArrowUp' && el.selectionStart === 0) {
    const t = taEls[i - 1]
    if (t) {
      ev.preventDefault()
      const pos = t.value.length
      t.focus()
      t.setSelectionRange(pos, pos)
    }
    return
  }
  if (ev.key === 'ArrowDown' && el.selectionStart === el.value.length) {
    const t = taEls[i + 1]
    if (t) {
      ev.preventDefault()
      t.focus()
      t.setSelectionRange(0, 0)
    }
    return
  }
  if (ev.key === 'Escape') {
    el.blur()
  }
}

function onPaste(ev: ClipboardEvent) {
  // 粘贴多行时按行拆分，保持一行一格
  const text = ev.clipboardData?.getData('text') ?? ''
  if (!text.includes('\n')) return
  ev.preventDefault()
  const rows = text.split(/\r?\n/).filter((r) => r.trim())
  if (!rows.length) return
  const el = ev.target as HTMLTextAreaElement
  const idx = Number((el.dataset.index as string) ?? -1)
  const line = props.lines[idx]
  if (!line) return
  line.text = rows[0]
  for (let k = 1; k < rows.length; k++) {
    const nl = newLine(line.kind)
    nl.text = rows[k]
    props.lines.splice(idx + k, 0, nl)
  }
  pendingFocus = idx + rows.length - 1
  changed()
  applyPendingFocus()
}
</script>

<template>
  <div class="cal-cell" :class="{ 'out-month': !inMonth, today: isToday }">
    <div class="cal-cell-head">
      <span class="cal-daynum" title="点击查看 / 打卡习惯" @click="emit('dayclick')">{{ dayNum }}</span>
      <span v-if="net !== null" class="cal-net" :class="net >= 0 ? 'pos' : 'neg'">
        {{ net >= 0 ? '+' : '' }}{{ net }}
      </span>
    </div>
    <div class="cal-lines">
      <!-- 习惯条目：与任务行同款方框，但整体红色；点击打卡 / 查看习惯 -->
      <div
        v-if="habitTotal"
        class="cal-line cal-habit-row"
        title="点击打卡 / 查看习惯"
        @click="emit('dayclick')"
      >
        <span class="cal-gutter">
          <span class="cal-habit-check" :class="{ on: (habitDone ?? 0) >= habitTotal }"></span>
        </span>
        <span class="cal-habit-label">习惯 {{ habitDone ?? 0 }}/{{ habitTotal }}</span>
      </div>

      <div
        v-for="(line, i) in lines"
        :key="line.cid"
        class="cal-line"
        :class="{ 'is-task': line.kind === 'task', 'is-done': line.kind === 'task' && line.done }"
      >
        <span class="cal-gutter">
          <span
            v-if="line.kind === 'task'"
            class="cal-check"
            :title="line.done ? '已完成，点击标为未完成' : '未完成，点击标为已完成'"
            @click="toggleDone(line)"
          ></span>
          <span v-else class="cal-dot" title="刷成任务" @click="toTask(line)"></span>
        </span>

        <textarea
          :ref="(el) => setTa(i, el)"
          v-model="line.text"
          class="cal-text"
          rows="1"
          spellcheck="false"
          :data-index="i"
          placeholder="输入…"
          @input="onInput(line, i)"
          @keydown="onKeydown(i, $event)"
          @paste="onPaste"
          @blur="changed"
        ></textarea>

        <button
          v-if="line.kind === 'task'"
          class="cal-untask"
          title="转回普通文本"
          @click="toText(line)"
        >
          ↺
        </button>
      </div>

      <div class="cal-add" title="新增一行" @click="appendLine">＋</div>
    </div>
  </div>
</template>
