<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { centerFor, centerTabs } from '../navigation'

const route = useRoute()
const auth = useAuthStore()
const center = computed(() => centerFor(route.path))
const tabs = computed(() =>
  auth.user ? centerTabs(center.value, auth.user.role) : [],
)
function active(path: string) {
  return (
    route.path === path ||
    (path === '/tickets' && route.path.startsWith('/tickets/'))
  )
}
</script>

<template>
  <nav v-if="tabs.length" class="center-navigation" aria-label="中心功能">
    <RouterLink
      v-for="tab in tabs"
      :key="tab.to"
      :to="tab.to"
      :class="{ selected: active(tab.to) }"
      :aria-current="active(tab.to) ? 'page' : undefined"
    >
      {{ tab.label }}
    </RouterLink>
  </nav>
</template>

<style scoped>
.center-navigation {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  margin-bottom: 24px;
  background: #fff;
  border: 1px solid #dce5f0;
  border-radius: 12px;
}
.center-navigation a {
  padding: 10px 16px;
  border-radius: 8px;
  color: #60738d;
  text-decoration: none;
}
.center-navigation a:hover {
  background: #f1f5fc;
}
.center-navigation a.selected {
  color: #245ee0;
  background: #eaf1ff;
  font-weight: 600;
}
.center-navigation a:focus-visible {
  outline: 2px solid #245ee0;
  outline-offset: 2px;
}
</style>
