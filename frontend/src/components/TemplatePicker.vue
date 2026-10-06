<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  listTemplates,
  createTemplate,
  deleteTemplate,
  type TemplateItem,
} from '@/api/template'

const props = defineProps<{ open: boolean; scope?: string | string[]; title?: string }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'apply', item: TemplateItem): void
}>()

const templates = ref<TemplateItem[]>([])
const sel = ref<TemplateItem | null>(null)
const loading = ref(false)

const newName = ref('')
const newContent = ref('')

/** 新建模板落在哪个 scope：多 scope 时取第一个 */
const createScope = computed(() => {
  const s = props.scope
  if (!s) return 'daily'
  return Array.isArray(s) ? s[0] : s
})

async function load() {
  loading.value = true
  try {
    const res = await listTemplates()
    const scopes = props.scope
      ? Array.isArray(props.scope)
        ? props.scope
        : [props.scope]
      : null
    templates.value = scopes
      ? res.templates.filter((t) => scopes.includes(t.scope))
      : res.templates
    sel.value = templates.value[0] ?? null
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      newName.value = ''
      newContent.value = ''
      load()
    }
  },
)

async function add() {
  const name = newName.value.trim()
  if (!name) return
  const t = await createTemplate(createScope.value, name, newContent.value)
  templates.value.push(t)
  sel.value = t
  newName.value = ''
  newContent.value = ''
}

async function remove(t: TemplateItem) {
  await deleteTemplate(t.id)
  templates.value = templates.value.filter((x) => x.id !== t.id)
  if (sel.value?.id === t.id) sel.value = templates.value[0] ?? null
}

function doApply() {
  if (!sel.value) return
  emit('apply', sel.value)
  emit('close')
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <transition name="gs-fade">
    <div v-if="open" class="gs-mask" @click.self="emit('close')">
      <div class="gs-panel">
        <div class="gs-bar">
          <span class="gs-title">{{ title || '模板库' }}</span>
          <button class="gs-close" aria-label="关闭" @click="emit('close')">✕</button>
        </div>

        <div class="gs-body">
          <div v-if="loading" class="gs-tip">加载中…</div>
          <template v-else>
            <div v-if="templates.length === 0" class="gs-tip">还没有模板，可在下方新建</div>

            <div
              v-for="t in templates"
              :key="t.id"
              class="tpl-item"
              :class="{ on: sel?.id === t.id }"
              @click="sel = t"
            >
              <span class="tpl-name">{{ t.name }}</span>
              <span v-if="t.builtin" class="tpl-tag">内置</span>
              <button
                v-if="!t.builtin"
                class="tpl-del"
                title="删除模板"
                @click.stop="remove(t)"
              >
                ✕
              </button>
            </div>

            <div v-if="sel" class="tpl-preview">{{ sel.content }}</div>

            <div class="tpl-add">
              <div class="tpl-add-title">保存为我的模板</div>
              <input v-model="newName" class="tpl-input" placeholder="模板名" />
              <textarea
                v-model="newContent"
                class="tpl-textarea"
                placeholder="模板内容（留空则新建空模板）"
              ></textarea>
              <button class="tpl-save" :disabled="!newName.trim()" @click="add">保存</button>
            </div>

            <div class="tpl-foot">
              <button class="tpl-apply" :disabled="!sel" @click="doApply">套用选中模板</button>
            </div>
          </template>
        </div>
      </div>
    </div>
  </transition>
</template>
