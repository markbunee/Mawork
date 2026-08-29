<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const navItems = [
  { path: '/home', name: '首页', icon: '🏠', enabled: true },
  { path: '/daily', name: '日报', icon: '📝', enabled: true },
  { path: '/accounting', name: '记账', icon: '💰', enabled: true },
  { path: '/planpool', name: '日程', icon: '🗓', enabled: true },
  { path: '/resources', name: '资料', icon: '📂', enabled: true },
  { path: '/articles', name: '文章', icon: '📚', enabled: true },
]

const currentTitle = computed(() => {
  const item = navItems.find((n) => n.path === route.path)
  return item ? item.name : 'MaWork'
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
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.enabled ? item.path : undefined"
          class="nav-item"
          :class="{ active: route.path === item.path, disabled: !item.enabled }"
          @click="item.enabled ? undefined : null"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-name">{{ item.name }}</span>
          <span v-if="!item.enabled" class="nav-badge">待</span>
        </RouterLink>
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
