<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'
import CenterNavigation from './components/CenterNavigation.vue'
const route = useRoute()
const mainContent = ref<HTMLElement | null>(null)
watch(() => route.fullPath, async () => {
  await nextTick()
  mainContent.value?.scrollTo({ top: 0 })
})
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <main v-if="route.meta.standalone" id="main-content" class="standalone" tabindex="-1"><RouterView /></main>
  <div v-else class="workspace-shell">
    <AppSidebar />
    <main id="main-content" ref="mainContent" class="page" tabindex="-1"><CenterNavigation /><RouterView :key="route.fullPath" /></main>
  </div>
</template>
