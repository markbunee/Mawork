<script setup lang="ts">
/**
 * 知识中心：把「资料库」与「文章」合并为一个入口。
 *
 * 设计意图（来自 Ardot 设计稿 MaWork 统计重设计稿 · 手机版·知识）：
 * 资料与文章都是「写下来、随时回看」的知识资产，原来拆成两个一级入口会显得散，
 * 因此合并为一个「知识」入口，内部用分段切换在「文件 / 文章」之间切换。
 *
 * 实现方式：复用 ResourcesView 与 ArticlesView 两个既有页面，
 * 只在外层加切换条，不复制任何业务逻辑。
 */
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ResourcesView from '@/views/ResourcesView.vue'
import ArticlesView from '@/views/ArticlesView.vue'
import SegmentedControl from '@/components/common/SegmentedControl.vue'
import '@/styles/knowledge.css'

const route = useRoute()
const router = useRouter()

/** 两个子模块的 key */
type TabKey = 'files' | 'articles'
const TAB = 'knowledge-tab'

const tabs: { key: TabKey; label: string }[] = [
  { key: 'files', label: '文件' },
  { key: 'articles', label: '文章' },
]

// 允许通过 /knowledge?tab=articles 直达，也记住用户上次的选择
const stored = route.query.tab
const initial: TabKey = stored === 'articles' ? 'articles' : 'files'
const active = ref<TabKey>(initial)

try {
  window.localStorage.setItem(TAB, active.value)
} catch {
  // 隐私模式下 localStorage 不可用，忽略即可
}

// 同步到 URL，刷新后仍停在同一模块；组件回调是 string，这里收窄为 TabKey
function select(key: string) {
  const next: TabKey = key === 'articles' ? 'articles' : 'files'
  if (active.value === next) return
  active.value = next
  try {
    window.localStorage.setItem(TAB, key)
  } catch {
    // 同上
  }
  void router.replace({ path: '/knowledge', query: { tab: key } })
}
</script>

<template>
  <div class="knowledge">
    <!-- 通用分段控件：指示块宽度按项数自动计算 -->
    <SegmentedControl
      :items="tabs"
      :model-value="active"
      aria-label="知识模块切换"
      @update:model-value="select"
    />

    <!-- 保留各自滚动容器：两个子页都是 flex 布局，直接嵌进来即可 -->
    <div class="kn-body">
      <ResourcesView v-show="active === 'files'" />
      <ArticlesView v-show="active === 'articles'" />
    </div>
  </div>
</template>
