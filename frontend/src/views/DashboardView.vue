<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getDashboard } from '../api/dashboard'
import { getCatalog, type Catalog } from '../api/config'
import { statusLabels, statusSchema, prioritySchema } from '../api/models'
import { useAuthStore } from '../stores/auth'
import AppIcon from '../components/AppIcon.vue'

const auth = useAuthStore()
const products = ref<Catalog['products']>([])
const productId = ref<number | null>(null)
const metrics = ref<Awaited<ReturnType<typeof getDashboard>> | null>(null)
const busy = ref(false)
const errorMessage = ref('')
const statuses = statusSchema.options
const priorities = prioritySchema.options

async function refresh() {
  if (busy.value) return
  busy.value = true
  errorMessage.value = ''
  metrics.value = null
  try {
    metrics.value = await getDashboard(auth.token, productId.value)
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    products.value = (await getCatalog(auth.token)).products
    await refresh()
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  }
})
</script>

<template>
  <div class="page-heading">
    <div><div class="eyebrow">工作空间 / 真实数据</div><h1>工作概览</h1><p>查看当前工单分布与解决时长，所有指标来自数据库。</p></div>
    <RouterLink to="/tickets/new" class="button primary"><AppIcon name="plus" :size="18" />新建工单</RouterLink>
  </div>
  <div class="dashboard-filter panel">
    <label for="dashboard-product">产品范围</label>
    <select id="dashboard-product" v-model="productId" :disabled="busy" @change="refresh">
      <option :value="null">全部产品</option>
      <option v-for="product in products" :key="product.id" :value="product.id">{{ product.name }}{{ product.is_active ? '' : '（停用）' }}</option>
    </select>
    <button class="button outline" :disabled="busy" @click="refresh">{{ busy ? '正在读取…' : '刷新数据' }}</button>
    <span class="muted">筛选对下方全部指标生效</span>
  </div>
  <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
  <p v-if="busy" role="status">正在读取统计数据……</p>
  <template v-if="metrics">
    <div class="dashboard-metrics">
      <div class="dashboard-metric"><span>全部工单<AppIcon name="ticket" :size="19" /></span><strong>{{ metrics.total }}</strong><small>所选产品范围内的工单</small></div>
      <div class="dashboard-metric"><span>待处理<AppIcon name="clock" :size="19" /></span><strong>{{ metrics.by_status.pending }}</strong><small>等待受理与排查</small></div>
      <div class="dashboard-metric"><span>处理中<AppIcon name="pencil" :size="19" /></span><strong>{{ metrics.by_status.processing }}</strong><small>正在推进的客户问题</small></div>
      <div class="dashboard-metric"><span>平均解决时长<AppIcon name="check" :size="19" /></span><strong class="resolution-value">{{ metrics.average_resolution_hours === null ? '暂无样本' : `${metrics.average_resolution_hours} 小时` }}</strong><small>{{ metrics.resolution_samples }} 条有明确解决时间的工单</small></div>
    </div>
    <div class="dashboard-grid">
      <section class="panel"><div class="section-title"><h2>工单状态分布</h2><span>{{ metrics.total }} 条</span></div>
        <div class="status-chart">
          <div v-for="status in statuses" :key="status" class="chart-row"><span>{{ statusLabels[status] }}</span><div class="bar-track"><i :class="status" :style="{ width: `${metrics.by_status[status] / Math.max(metrics.total, 1) * 100}%` }" /></div><strong>{{ metrics.by_status[status] }}</strong></div>
        </div>
        <p class="chart-note">各状态数量之和等于当前工单总数。</p>
      </section>
      <section class="panel"><div class="section-title"><h2>优先级分布</h2><span>{{ metrics.total }} 条</span></div>
        <div class="priority-summary"><strong>{{ metrics.by_priority.P1 }}</strong><div><span>P1 紧急工单</span><small>包含所有处理状态</small></div></div>
        <div class="stacked-bar"><i v-for="priority in priorities" :key="priority" :class="priority" :style="{ flex: metrics.by_priority[priority] }" /></div>
        <div class="priority-legend"><span v-for="(priority, index) in priorities" :key="priority"><i :class="priority" />{{ priority }} {{ ['紧急', '高', '中', '低'][index] }}<b>{{ metrics.by_priority[priority] }}</b></span></div>
      </section>
    </div>
    <p v-if="metrics.total === 0" class="empty-note">当前范围还没有工单，可以新建工单或导入历史数据。</p>
    <p class="chart-note">解决时长 = 首次标记已解决的时间 − 创建时间。缺少实际解决时间的导入案例不参与平均值；关闭时间不替代解决时间。</p>
  </template>
</template>
