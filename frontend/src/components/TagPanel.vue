<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { getTagItems, listAllTags, type TagItemsResult, type TagStat } from '@/api/tag'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const tags = ref<TagStat[]>([])
const loading = ref(false)
const activeTag = ref('')
const detail = ref<TagItemsResult | null>(null)
const detailLoading = ref(false)

async function loadList() {
  loading.value = true
  try {
    const res = await listAllTags()
    tags.value = res.tags
  } finally {
    loading.value = false
  }
}

async function openTag(t: string) {
  if (activeTag.value === t) {
    activeTag.value = ''
    detail.value = null
    return
  }
  activeTag.value = t
  detailLoading.value = true
  try {
    detail.value = await getTagItems(t)
  } finally {
    detailLoading.value = false
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      activeTag.value = ''
      detail.value = null
      loadList()
    }
  },
)

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

/** 字号随次数递增，形成标签云效果 */
function sizeOf(count: number): number {
  if (count >= 12) return 17
  if (count >= 6) return 15
  if (count >= 3) return 14
  return 13
}
</script>

<template>
  <transition name="gs-fade">
    <div v-if="open" class="gs-mask" @click.self="emit('close')">
      <div class="gs-panel">
        <div class="gs-bar">
          <span class="gs-title">标签中台</span>
          <button class="gs-close" aria-label="关闭" @click="emit('close')">✕</button>
        </div>

        <div class="gs-body">
          <div v-if="loading" class="gs-tip">加载中…</div>
          <div v-else-if="tags.length === 0" class="gs-tip">
            还没有标签。在日报 / 文章 / 任务里写 #标签 即可自动收录。
          </div>

          <template v-else>
            <div class="tag-cloud">
              <button
                v-for="t in tags"
                :key="t.tag"
                class="tag-pill"
                :class="{ on: activeTag === t.tag }"
                :style="{ fontSize: sizeOf(t.count) + 'px' }"
                @click="openTag(t.tag)"
              >
                #{{ t.tag }}<span class="tag-pill-n">{{ t.count }}</span>
              </button>
            </div>

            <div v-if="activeTag" class="tag-detail">
              <div class="tag-detail-head">#{{ activeTag }}</div>
              <div v-if="detailLoading" class="gs-tip">加载中…</div>
              <template v-else-if="detail">
                <div v-for="g in detail.groups" :key="g.module" class="gs-group">
                  <div class="gs-group-label">
                    {{ g.module_label }}<span class="gs-group-n">{{ g.items.length }}</span>
                  </div>
                  <RouterLink
                    v-for="(it, i) in g.items"
                    :key="g.module + '-' + i"
                    class="gs-item"
                    :to="{ path: it.route, query: it.query }"
                    @click="emit('close')"
                  >
                    <span class="gs-item-title">{{ it.title }}</span>
                    <span class="gs-item-sub">{{ it.subtitle }}</span>
                  </RouterLink>
                </div>
              </template>
            </div>
          </template>
        </div>
      </div>
    </div>
  </transition>
</template>
