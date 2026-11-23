<script setup lang="ts">
import { ref } from 'vue'
import { searchKnowledge } from '../api/knowledge'
import { useAuthStore } from '../stores/auth'
const props = defineProps<{ ticketId: number }>()
const auth = useAuthStore()
const result = ref<Awaited<ReturnType<typeof searchKnowledge>> | null>(null)
const busy = ref(false)
const errorMessage = ref('')
async function search() {
  result.value = null
  errorMessage.value = ''
  busy.value = true
  try { result.value = await searchKnowledge(auth.token, props.ticketId) }
  catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  } finally { busy.value = false }
}
</script>
<template>
  <section class="content-card similar-cases knowledge-matches">
    <h2>相关知识依据</h2>
    <p class="muted">查找已发布的产品说明和处理规范，并核对原文出处。</p>
    <el-button type="primary" :loading="busy" :disabled="busy" @click="search">检索知识文档</el-button>
    <p v-if="errorMessage" role="alert" class="error">{{ errorMessage }}</p>
    <template v-if="result">
      <p class="muted">索引时间：{{ new Date(result.indexed_at).toLocaleString() }} · {{ result.expanded ? '已补查同分类' : '同产品模块' }}</p>
      <p v-if="result.stale_count" class="error">发现 {{ result.stale_count }} 个失效候选，请重建知识索引。</p>
      <p v-if="!result.items.length">本次没有找到可用知识依据。</p>
      <article v-for="item in result.items" :key="item.chunk_id" class="record">
        <RouterLink :to="'/knowledge/' + item.document_id">{{ item.title }}</RouterLink>
        <p class="muted">{{ item.source_name }} · 第 {{ item.chunk_order }} 块 · 排序分数 {{ item.score.toFixed(4) }}</p>
        <p class="multiline">{{ item.content }}</p>
      </article>
      <p class="muted">分数只用于排序；检索结果仍需人工核实。</p>
    </template>
  </section>
</template>
