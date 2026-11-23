import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/service' },
    { path: '/service', component: () => import('../views/ServicePortalView.vue') },
    { path: '/service/rules', component: () => import('../views/ServiceInfoView.vue') },
    { path: '/service/products', component: () => import('../views/ServiceInfoView.vue') },
    { path: '/service/people', component: () => import('../views/PeopleView.vue') },
    { path: '/dashboard', component: () => import('../views/DashboardView.vue') },
    { path: '/qa', component: () => import('../views/KnowledgeChatView.vue') },
    { path: '/qa/evaluation', component: () => import('../views/QaEvaluationView.vue') },
    { path: '/admin/ai-service', component: () => import('../views/AiServiceView.vue'), meta: { admin: true } },
    { path: '/tickets', component: () => import('../views/TicketsView.vue') },
    { path: '/tickets/import', redirect: '/admin/imports' },
    { path: '/tickets/new', component: () => import('../views/TicketEditor.vue') },
    { path: '/tickets/:id(\\d+)/edit', component: () => import('../views/TicketEditor.vue') },
    { path: '/tickets/:id(\\d+)', component: () => import('../views/TicketDetailView.vue') },
    { path: '/knowledge', component: () => import('../views/KnowledgeView.vue') },
    { path: '/knowledge/new', component: () => import('../views/KnowledgeEditor.vue'), meta: { admin: true } },
    { path: '/knowledge/:id(\\d+)', component: () => import('../views/KnowledgeEditor.vue') },
    { path: '/health', component: () => import('../views/HealthView.vue'), meta: { public: true } },
    { path: '/login', component: () => import('../views/LoginView.vue'), meta: { public: true, standalone: true } },
    { path: '/admin', component: () => import('../views/AdminView.vue'), meta: { admin: true },
      beforeEnter: to => to.query.tab === 'imports' ? '/admin/imports' : to.query.tab === 'staff' ? '/service/people' : true },
    { path: '/admin/imports', component: () => import('../views/ImportPage.vue'), meta: { admin: true } },
    { path: '/:pathMatch(.*)*', component: () => import('../views/NotFoundView.vue'), meta: { public: true } },
  ],
})

router.beforeEach(async to => {
  const auth = useAuthStore()
  if (auth.token && !auth.user && to.path !== '/login') {
    try {
      await auth.restoreSession()
    } catch (error) {
      if (!(error instanceof Error)) throw error
      // 公开页面和连接检查不依赖登录，后端故障时仍允许访问。
      if (to.meta.public) return true
      return { path: '/login', query: { redirect: to.fullPath, session_error: `恢复登录失败：${error.message}` } }
    }
  }
  if (!to.meta.public && !auth.token) return { path: '/login', query: { redirect: to.fullPath } }
  if (auth.user?.role === 'customer' && !to.meta.public && !['/service', '/service/products', '/service/rules'].includes(to.path)) return '/service'
  if (auth.user && auth.user.role !== 'customer' && to.path === '/service/products') return '/service'
  if (to.meta.admin && auth.user?.role !== 'admin') return '/tickets'
})
