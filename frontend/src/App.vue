<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { getUsername, isAdmin } from '@/utils/auth'
import { logout } from '@/api/auth'
import { getReminders } from '@/api/reminder'
import GlobalSearch from '@/components/GlobalSearch.vue'
import ReminderPanel from '@/components/ReminderPanel.vue'
import BackupPanel from '@/components/BackupPanel.vue'

const route = useRoute()
const router = useRouter()

// 全局搜索（横切能力 E1）
const searchOpen = ref(false)
function onGlobalKey(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    searchOpen.value = !searchOpen.value
  }
}

// 数据备份（横切能力 E5）
const backupOpen = ref(false)

// 提醒通知（横切能力 E4）
const reminderOpen = ref(false)
const reminderCount = ref(0)
async function refreshReminderCount() {
  try {
    const r = await getReminders()
    reminderCount.value = r.total
  } catch {
    reminderCount.value = 0
  }
}

onMounted(() => {
  window.addEventListener('keydown', onGlobalKey)
  refreshReminderCount()
})
onUnmounted(() => window.removeEventListener('keydown', onGlobalKey))

const isLoginPage = computed(() => route.path === '/login')
const username = computed(() => getUsername())
const admin = computed(() => isAdmin())
const roleLabel = computed(() => (admin.value ? '管理员' : '成员'))

function onLogout() {
  logout()
  router.replace('/login')
}

// 一级导航：按「使用频率 + 功能归属」合并为 6 个入口，避免入口过散。
//  - 今天：日历 + 习惯打卡 + 写日报快捷 + 本周概览（见 HomeView）
//  - 知识：资料库 + 文章合并入口（见 KnowledgeView，tab 切换）
//  - 计时 / 习惯 / 资料 / 文章 不再单列，从页内进入（今天侧栏 / 知识页内切换）
const navItems = [
  { path: '/home', name: '今天', title: '今天', enabled: true },
  { path: '/daily', name: '日报', title: '日报', enabled: true },
  { path: '/planpool', name: '日程', title: '日程', enabled: true },
  { path: '/accounting', name: '记账', title: '记账', enabled: true },
  { path: '/analysis', name: '复盘', title: '复盘中心', enabled: true },
  { path: '/knowledge', name: '知识', title: '知识', enabled: true },
]

// 次级页面：仍可访问，但不占一级入口（从页内进入：今天侧栏 / 知识页内切换）
const secondaryItems = [
  { path: '/timer', name: '计时', title: '计时' },
  { path: '/habit', name: '习惯', title: '习惯培养' },
  { path: '/resources', name: '资料库', title: '资料库' },
  { path: '/articles', name: '文章', title: '文章' },
]

// 手机端胶囊 Tab：6 个一级入口全部平铺（符合移动端 3–6 个顶层入口）
const accountOpen = ref(false)

const currentTitle = computed(() => {
  if (route.path === '/users') return '用户管理'
  const item = navItems.find((n) => n.path === route.path)
  if (item) return item.title
  const sub = secondaryItems.find((n) => n.path === route.path)
  return sub ? sub.title : 'MaWork'
})

/**
 * 激活态归属：二级页面（计时/习惯/资料/文章）也要点亮对应的一级入口，
 * 否则从「更多」进入后侧边栏会一个都不亮，失去方位感。
 */
const activeNavPath = computed(() => {
  if (navItems.some((n) => n.path === route.path)) return route.path
  const owner: Record<string, string> = {
    '/resources': '/knowledge',
    '/articles': '/knowledge',
    '/timer': '/planpool',
    '/habit': '/home',
  }
  return owner[route.path] ?? route.path
})

/** 顶栏副标题：今天页显示周次（更有信息量），其余显示日期 */
const todayLabel = computed(() =>
  new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }),
)

/** ISO 周序号，用于「今天」页副标题 */
function isoWeek(d: Date): number {
  const t = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  t.setDate(t.getDate() + 3 - ((t.getDay() + 6) % 7))
  const first = new Date(t.getFullYear(), 0, 4)
  return 1 + Math.round(((t.getTime() - first.getTime()) / 86400000 - 3 + ((first.getDay() + 6) % 7)) / 7)
}
const homeSubLabel = computed(() => {
  const d = new Date()
  const wd = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()]
  return `${d.getMonth() + 1}月${d.getDate()}日 ${wd} · 第${isoWeek(d)}周`
})
const pageSubLabel = computed(() => (route.path === '/home' ? homeSubLabel.value : todayLabel.value))

/** 头像取用户名首字，取不到时回退品牌字 */
const avatarText = computed(() => {
  const u = username.value?.trim()
  return u ? u.slice(0, 1).toUpperCase() : 'M'
})
</script>

<template>
  <!-- 登录页：只渲染登录界面，不套主框架 -->
  <RouterView v-if="isLoginPage" />

  <template v-else>
    <!-- 手机端顶栏（桌面隐藏，桌面走 .topbar） -->
    <header class="m-appbar">
      <div class="m-appbar-inner">
        <div class="m-appbar-text">
          <h1 class="m-appbar-title">{{ currentTitle }}</h1>
          <span class="m-appbar-sub">{{ pageSubLabel }}</span>
        </div>
        <button class="m-appbar-backup" aria-label="备份" @click="backupOpen = true">备份</button>
        <button class="m-appbar-bell" aria-label="提醒" @click="reminderOpen = true">
          提醒<span v-if="reminderCount > 0" class="m-bell-badge">{{ reminderCount }}</span>
        </button>
        <button class="m-appbar-search" aria-label="搜索" @click="searchOpen = true">搜索</button>
        <button class="m-avatar" aria-label="账户" @click="accountOpen = true">
          {{ avatarText }}
        </button>
      </div>
    </header>

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
            :class="{ active: activeNavPath === item.path, disabled: !item.enabled }"
            :title="item.title"
          >
            <span class="nav-name">{{ item.name }}</span>
            <span v-if="!item.enabled" class="nav-badge">待</span>
          </component>
        </nav>

        <div class="sidebar-foot">个人工作操作系统</div>
      </aside>

      <main class="content">
        <header class="topbar">
          <div class="topbar-left">
            <h1 class="page-title">{{ currentTitle }}</h1>
            <span class="page-sub">{{ pageSubLabel }}</span>
          </div>
          <div class="topbar-right">
            <button class="topbar-bell" aria-label="提醒" title="今日提醒" @click="reminderOpen = true">
              提醒<span v-if="reminderCount > 0" class="bell-badge">{{ reminderCount }}</span>
            </button>
            <button class="topbar-search" aria-label="搜索" title="搜索 (Ctrl/⌘ + K)" @click="searchOpen = true">搜索</button>
            <span class="topbar-date">{{ new Date().toLocaleDateString('zh-CN') }}</span>
            <span v-if="username" class="topbar-user">{{ username }}</span>
            <RouterLink v-if="admin" class="topbar-link" to="/users">用户管理</RouterLink>
            <button class="logout-btn" @click="onLogout">退出</button>
          </div>
        </header>
        <div class="page-body">
          <RouterView />
        </div>
      </main>
    </div>

    <!-- 手机端底部胶囊 Tab 栏（桌面隐藏） -->
    <nav class="m-tabbar">
      <div class="m-tabbar-pill">
          <RouterLink
            v-for="item in navItems"
            :key="item.path"
            class="m-tab"
            :class="{ on: activeNavPath === item.path }"
            :to="item.path"
          >
            <span class="m-tab-label">{{ item.name }}</span>
          </RouterLink>
      </div>
    </nav>

    <!-- 手机端账户弹层：退出登录的落点（顶栏不塞按钮，保持干净） -->
    <div v-if="accountOpen" class="m-mask" @click="accountOpen = false">
      <div class="m-sheet" @click.stop>
        <div class="m-sheet-grab"></div>
        <div class="m-account">
          <div class="m-account-avatar">{{ avatarText }}</div>
          <div>
            <div class="m-account-name">{{ username || '未登录' }}</div>
            <div class="m-account-sub">MaWork · {{ roleLabel }}</div>
          </div>
        </div>
        <RouterLink v-if="admin" class="m-sheet-btn" to="/users" @click="accountOpen = false">
          用户管理
        </RouterLink>
        <button class="m-sheet-btn danger" @click="onLogout">退出登录</button>
        <button class="m-sheet-btn" @click="accountOpen = false">取消</button>
      </div>
    </div>

    <!-- 全局搜索弹层（横切能力 E1） -->
    <GlobalSearch :open="searchOpen" @close="searchOpen = false" />

    <!-- 今日提醒弹层（横切能力 E4） -->
    <ReminderPanel :open="reminderOpen" @close="reminderOpen = false" />

    <!-- 数据备份弹层（横切能力 E5） -->
    <BackupPanel :open="backupOpen" @close="backupOpen = false" />
  </template>
</template>
