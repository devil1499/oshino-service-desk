<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getCatalog } from '../api/config'
import type { NamedItem } from '../api/models'
import { useAuthStore } from '../stores/auth'
import ImportView from './ImportView.vue'

const auth = useAuthStore()
const products = ref<NamedItem[]>([])
const loading = ref(true)
const error = ref('')
async function load() {
  loading.value = true
  error.value = ''
  try {
    products.value = (await getCatalog(auth.token)).products
  } catch (e) {
    if (!(e instanceof Error)) throw e
    error.value = e.message
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>
<template>
  <header class="page-heading">
    <div>
      <h1>历史导入</h1>
      <p>上传 CSV，查看已导入的历史工单。</p>
    </div>
  </header>
  <p v-if="error" role="alert" class="error error-panel">
    {{ error }} <button class="text-button" @click="load">重新读取</button>
  </p>
  <section v-loading="loading" class="panel import-page">
    <ImportView v-if="!loading && !error" :products="products" />
  </section>
</template>
<style scoped>
.import-page {
  padding: 24px;
  min-height: 300px;
}
</style>
