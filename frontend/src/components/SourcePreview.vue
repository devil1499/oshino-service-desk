<script setup lang="ts">
import { ElDrawer, ElSkeleton } from 'element-plus'
import 'element-plus/es/components/drawer/style/css'
import 'element-plus/es/components/skeleton/style/css'
import { onMounted, ref } from 'vue'
import { getTicket } from '../api/tickets'
import { getKnowledge, type KnowledgeDocument } from '../api/knowledge'
import { statusLabels, type TicketDetail } from '../api/models'
import { useAuthStore } from '../stores/auth'

const props = defineProps<{ kind: 'ticket' | 'knowledge'; id: number }>()
const emit = defineEmits<{ close: [] }>()
const auth = useAuthStore()
const ticket = ref<TicketDetail | null>(null)
const document = ref<KnowledgeDocument | null>(null)
const loading = ref(true)
const errorMessage = ref('')

onMounted(async () => {
  try {
    if (props.kind === 'ticket') ticket.value = await getTicket(auth.token, props.id)
    else document.value = await getKnowledge(auth.token, props.id)
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  } finally { loading.value = false }
})
</script>

<template>
  <el-drawer :model-value="true" :title="kind === 'ticket' ? '原工单预览' : '知识文档预览'" size="min(620px, 94vw)" @closed="emit('close')">
    <el-skeleton v-if="loading" :rows="8" animated />
    <p v-else-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
    <article v-else-if="ticket" class="source-preview">
      <p class="muted">{{ ticket.number }} · {{ statusLabels[ticket.status] }}</p>
      <h2>{{ ticket.title }}</h2>
      <h3>问题描述</h3><p class="multiline">{{ ticket.description }}</p>
      <h3>解决方案</h3><p class="multiline">{{ ticket.solution || '尚未填写解决方案' }}</p>
      <p class="muted">此处为原工单当前内容，仅供核实；关闭预览可继续处理当前工单。</p>
    </article>
    <article v-else-if="document" class="source-preview">
      <h2>{{ document.title }}</h2>
      <p class="muted">{{ document.source_name }} · 版本 {{ document.revision }} · {{ document.status }}</p>
      <p class="multiline">{{ document.content }}</p>
    </article>
  </el-drawer>
</template>
