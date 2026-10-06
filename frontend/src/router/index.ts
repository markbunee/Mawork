import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn } from '@/utils/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      redirect: '/home',
    },
    {
      path: '/home',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
    },
    {
      path: '/daily',
      name: 'daily',
      component: () => import('@/views/DailyView.vue'),
    },
    {
      path: '/accounting',
      name: 'accounting',
      component: () => import('@/views/AccountingView.vue'),
    },
    {
      path: '/planpool',
      name: 'planpool',
      component: () => import('@/views/PlanpoolView.vue'),
    },
    {
      path: '/articles',
      name: 'articles',
      component: () => import('@/views/ArticlesView.vue'),
    },
    {
      // 知识中心：资料 + 文章合并入口（?tab=articles 直达文章，其余默认文件）
      path: '/knowledge',
      name: 'knowledge',
      component: () => import('@/views/KnowledgeView.vue'),
    },
    {
      path: '/resources',
      name: 'resources',
      component: () => import('@/views/ResourcesView.vue'),
    },
    {
      path: '/analysis',
      name: 'analysis',
      component: () => import('@/views/AnalysisView.vue'),
    },
    {
      path: '/timer',
      name: 'timer',
      component: () => import('@/views/TimerView.vue'),
    },
    {
      path: '/habit',
      name: 'habit',
      component: () => import('@/views/HabitView.vue'),
    },
    {
      // 用户管理：不进侧边栏/胶囊 Tab，入口在管理员的账户弹层里
      path: '/users',
      name: 'users',
      component: () => import('@/views/UserManageView.vue'),
    },
  ],
})

// 全局守卫：未登录一律跳登录页；已登录则不再停留在登录页
router.beforeEach((to) => {
  const logged = isLoggedIn()
  if (to.meta.public) {
    return logged && to.path === '/login' ? { path: '/home' } : true
  }
  if (!logged) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
