import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
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
  ],
})

export default router
