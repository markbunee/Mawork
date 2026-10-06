<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { getReminders, type ReminderResult } from '@/api/reminder'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const loading = ref(false)
const result = ref<ReminderResult | null>(null)

async function load() {
  loading.value = true
  try {
    result.value = await getReminders()
  } catch {
    result.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) load()
  },
)

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
          <span class="gs-title">今日提醒</span>
          <button class="gs-close" aria-label="关闭" @click="emit('close')">✕</button>
        </div>

        <div class="gs-body">
          <div v-if="loading" class="gs-tip">加载中…</div>
          <div v-else-if="result && result.total === 0" class="gs-tip">
            今天没有待办提醒 🎉
          </div>
          <template v-else>
            <div v-for="g in result?.groups" :key="g.module" class="gs-group">
              <div class="gs-group-label">{{ g.module_label }}<span class="gs-group-n">{{ g.items.length }}</span></div>
              <RouterLink
                v-for="(it, i) in g.items"
                :key="g.module + '-' + i"
                class="gs-item"
                :to="{ path: it.route, query: it.query }"
                @click="emit('close')"
              >
                <span class="gs-item-title">{{ it.title }}</span>
                <span v-if="it.detail" class="gs-item-sub">{{ it.detail }}</span>
              </RouterLink>
            </div>
          </template>
        </div>
      </div>
    </div>
  </transition>
</template>
