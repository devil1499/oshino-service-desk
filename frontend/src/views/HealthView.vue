<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getHealth } from '../api/health'
import type { HealthResponse } from '../api/health'

const isChecking = ref(false)
const healthStatus = ref<HealthResponse | null>(null)
const errorMessage = ref('')

async function checkHealth(): Promise<void> {
  isChecking.value = true
  healthStatus.value = null
  errorMessage.value = ''

  try {
    healthStatus.value = await getHealth()
  } catch (error) {
    if (!(error instanceof Error)) {
      throw error
    }

    errorMessage.value = error.message
  } finally {
    isChecking.value = false
  }
}

onMounted(checkHealth)
</script>

<template>
  <div class="page-heading"><div><div class="eyebrow">工作空间 / 服务状态</div><h1>连接检查</h1><p>确认当前页面能否连接到后台服务。</p></div><span class="source-badge live"><i />真实接口</span></div>
  <section class="panel health-panel">
    <div class="health-orb" :class="{ connected: healthStatus, failed: errorMessage }">{{ isChecking ? '…' : healthStatus ? '✓' : '!' }}</div>
    <h2>{{ isChecking ? '正在连接后台服务' : healthStatus ? '前后端连接成功' : '暂时无法连接后台' }}</h2>
    <p v-if="isChecking" role="status">正在检查……</p>
    <p v-else-if="errorMessage" role="alert" class="error">
      {{ errorMessage }}
    </p>
    <p v-else-if="healthStatus" role="status" class="success">
      前后端连接成功
    </p>

    <pre v-if="healthStatus" class="health-response">{{ JSON.stringify(healthStatus, null, 2) }}</pre>
    <button class="button primary" :disabled="isChecking" @click="checkHealth">
      {{ isChecking ? '检查中……' : '重新检查' }}
    </button>
    <p class="health-note">健康接口只验证 HTTP 链路，不代表数据库或后续业务功能已经就绪。</p>
  </section>
</template>
