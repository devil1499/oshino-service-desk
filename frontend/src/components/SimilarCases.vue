<script setup lang="ts">
import { ref } from 'vue'
import { findSimilarCases } from '../api/analysis'
import { useAuthStore } from '../stores/auth'

const props = defineProps<{ ticketId: number }>()
const auth = useAuthStore()
const result = ref<Awaited<ReturnType<typeof findSimilarCases>> | null>(null)
const busy = ref(false)
const errorMessage = ref('')

async function search() {
  busy.value = true
  result.value = null
  errorMessage.value = ''
  try {
    result.value = await findSimilarCases(auth.token, props.ticketId)
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="content-card similar-cases">
    <h2>相似历史案例</h2>
    <p>查找已解决或已关闭且有方案的历史工单，供人工参考。</p>
    <el-button type="primary" :loading="busy" :disabled="busy" @click="search">检索相似案例</el-button>
    <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
    <div v-if="result">
      <p class="muted">索引时间：{{ new Date(result.indexed_at).toLocaleString() }}。新增或修改的案例需重建索引后参与检索。</p>
      <p v-if="result.expanded">同产品模块的有效候选不足 5 条，已补查同分类案例。</p>
      <p v-if="result.stale_count > 0" class="error">已排除 {{ result.stale_count }} 条失效候选，请管理员重建索引。</p>
      <p v-if="result.items.length === 0">当前索引没有可返回的有效案例。</p>
      <article v-for="item in result.items" :key="item.id" class="record">
        <RouterLink :to="'/tickets/' + item.id">{{ item.number }} · {{ item.title }}</RouterLink>
        <p class="muted">{{ item.scope === 'module' ? '同产品模块' : '同分类补充' }} · 排序分数 {{ item.score.toFixed(4) }}</p>
        <p class="multiline">{{ item.solution }}</p>
      </article>
      <p class="muted">排序分数用于候选排序，不代表正确率或百分比。方案是否适用仍需核实。</p>
    </div>
  </section>
</template>
