<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AppIcon from './AppIcon.vue'
import { staffNavigation, centerFor } from '../navigation'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const navigation = computed(() => auth.user?.role === 'customer' ? [
  { to: '/service', label: '服务咨询', icon: 'assistant' },
  { to: '/service/products', label: '支持的产品', icon: 'grid' },
  { to: '/service/rules', label: '服务守则', icon: 'book' },
] as const : staffNavigation)
const name = computed(() => auth.user?.display_name ?? '演示访客')
function isActive(path: string) {
  if (auth.user?.role !== 'customer') {
    if (path === '/qa') return route.path === '/qa'
    if (path === '/service') return centerFor(route.path) === 'tickets'
    if (path === '/dashboard') return centerFor(route.path) === 'management'
  }
  return path === '/service' ? route.path === path : route.path.startsWith(path)
}

function signOut(): void {
  auth.signOut()
  void router.push('/login')
}
</script>

<template>
  <aside class="sidebar">
    <RouterLink to="/service" class="brand" aria-label="售后服务入口">
      <svg class="brand-mark" viewBox="0 0 34 34" aria-hidden="true">
        <rect x="2" y="8" width="13" height="13" rx="3" fill="#91b3ff" />
        <rect x="14" y="2" width="13" height="13" rx="3" fill="#b1c9f6" opacity=".5" />
        <rect x="17" y="17" width="12" height="12" rx="3" fill="#91b3ff" opacity=".6" />
      </svg>
      <span><strong>Oshino</strong><small>{{ auth.user?.role === 'customer' ? '用户服务中心' : '客服工作台' }}</small></span>
    </RouterLink>
    <div class="nav-section-label">工作空间</div>
    <nav class="workspace-nav" aria-label="主导航">
      <RouterLink v-for="item in navigation" :key="item.to" :to="item.to" class="nav-item"
        :class="{ active: isActive(item.to) }" :aria-current="isActive(item.to) ? 'page' : undefined">
        <AppIcon :name="item.icon" :size="19" /><span>{{ item.label }}</span>
      </RouterLink>
    </nav>
    <div class="sidebar-bottom">
      <div class="workspace-hint"><span class="tiny-dot" />工单、知识与智能助手 · 实时数据</div>
      <div class="sidebar-user">
        <span class="avatar">{{ name.slice(0, 1) }}</span>
        <span class="user-copy"><strong>{{ name }}</strong><small>{{ auth.user ? (auth.user.role === 'admin' ? '管理员' : auth.user.role === 'customer' ? ['', '青铜会员','铂金会员','王者会员','最强王者会员'][auth.user.customer_tier] : `L${auth.user.staff_level} ${['','普通客服','技术客服','售后主管'][auth.user.staff_level]}`) : '浏览本地示例' }}</small></span>
        <button v-if="auth.user" type="button" class="icon-button" aria-label="退出登录" title="退出登录" @click="signOut">
          <AppIcon name="logout" :size="18" />
        </button>
        <RouterLink v-else to="/login" class="sidebar-login">登录</RouterLink>
      </div>
    </div>
  </aside>
</template>
