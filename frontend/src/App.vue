<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()

// name 用于侧边栏（收窄后只放短名），title 用于顶栏
const navItems = [
  { path: '/home', name: '日历', title: '日历', icon: '🗓', enabled: true },
  { path: '/daily', name: '日报', title: '日报', icon: '📝', enabled: true },
  { path: '/planpool', name: '日程', title: '日程', icon: '📋', enabled: true },
  { path: '/accounting', name: '记账', title: '记账', icon: '💰', enabled: true },
  { path: '/resources', name: '资料', title: '资料', icon: '📂', enabled: true },
  { path: '/articles', name: '文章', title: '文章', icon: '📚', enabled: true },
  { path: '/analysis', name: '报告', title: 'AI 报告分析', icon: '✨', enabled: true },
  { path: '/timer', name: '计时', title: '计时', icon: '⏱', enabled: true },
]

const currentTitle = computed(() => {
  const item = navItems.find((n) => n.path === route.path)
  return item ? item.title : 'MaWork'
})
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">Ma</span>
        <span class="brand-text">Work</span>
      </div>

      <nav class="nav">
        <component
          :is="item.enabled ? RouterLink : 'span'"
          v-for="item in navItems"
          :key="item.path"
          v-bind="item.enabled ? { to: item.path } : {}"
          class="nav-item"
          :class="{ active: route.path === item.path, disabled: !item.enabled }"
          :title="item.title"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-name">{{ item.name }}</span>
          <span v-if="!item.enabled" class="nav-badge">待</span>
        </component>
      </nav>

      <div class="sidebar-foot">个人工作操作系统</div>
    </aside>

    <main class="content">
      <header class="topbar">
        <h1 class="page-title">{{ currentTitle }}</h1>
        <span class="topbar-date">{{ new Date().toLocaleDateString('zh-CN') }}</span>
      </header>
      <div class="page-body">
        <RouterView />
      </div>
    </main>
  </div>
</template>
