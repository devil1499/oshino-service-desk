<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { listKnowledge, type KnowledgeDocument } from '../api/knowledge'
import { useAuthStore } from '../stores/auth'
import { formatTime } from '../utils/format'

const auth = useAuthStore()
const documents = ref<KnowledgeDocument[]>([])
const query = ref('')
const status = ref('')
const page = ref(1)
const total = ref(0)
const busy = ref(false)
const errorMessage = ref('')
const statusLabels = { draft: '草稿', published: '已发布', disabled: '已停用' }

async function load() {
  busy.value = true
  errorMessage.value = ''
  try {
    const result = await listKnowledge(auth.token, page.value, query.value.trim(), status.value)
    documents.value = result.items
    total.value = result.total
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  } finally {
    busy.value = false
  }
}
function search() {
  page.value = 1
  void load()
}
function changePage(change: number) {
  page.value += change
  void load()
}
onMounted(load)
</script>

<template>
  <div class="page-heading">
    <div><div class="eyebrow">工作空间 / 团队知识</div><h1>知识库<span class="heading-count">{{ total }}</span></h1><p>把产品说明与处理规范，整理成有出处的知识依据。</p></div>
    <RouterLink v-if="auth.user?.role === 'admin'" to="/knowledge/new" class="button primary"><AppIcon name="plus" :size="18" />录入或上传文档</RouterLink>
  </div>
  <form class="knowledge-toolbar content-card" @submit.prevent="search">
    <label class="search-box"><AppIcon name="search" :size="18" /><input v-model="query" type="search" aria-label="搜索知识" maxlength="200" placeholder="搜索标题或正文关键词" /></label>
    <select v-if="auth.user?.role === 'admin'" v-model="status" aria-label="筛选文档状态" @change="search"><option value="">全部状态</option><option value="draft">草稿</option><option value="published">已发布</option><option value="disabled">已停用</option></select>
    <button class="button outline" :disabled="busy" type="submit">查询</button>
  </form>
  <p v-if="errorMessage" class="error error-panel" role="alert">{{ errorMessage }}</p>
  <p v-else-if="busy" role="status" class="muted">正在读取知识文档……</p>
  <template v-else>
    <section v-if="documents.length" class="knowledge-grid" aria-label="知识文档列表">
      <RouterLink v-for="document in documents" :key="document.id" :to="'/knowledge/' + document.id" class="knowledge-card">
        <div><span class="knowledge-state" :class="document.status">{{ statusLabels[document.status] }}</span><span class="muted">第 {{ document.revision }} 版 · {{ document.chunk_count }} 块</span></div>
        <h2>{{ document.title }}</h2><p>{{ document.content.slice(0, 130) }}</p>
        <footer><span>{{ document.source_name }}</span><time>{{ formatTime(document.updated_at) }}</time><AppIcon name="arrow-right" :size="16" /></footer>
      </RouterLink>
    </section>
    <section v-else class="panel empty-state"><AppIcon name="book" :size="32" /><h2>暂无符合条件的文档</h2><p>{{ auth.user?.role === 'admin' ? '可以调整搜索条件，或录入第一份产品说明。' : '管理员发布文档后，你可以在这里阅读。' }}</p></section>
    <div class="pagination"><span>共 {{ total }} 篇 · 第 {{ page }} / {{ Math.max(1, Math.ceil(total / 20)) }} 页</span><div><button class="pagination-button" :disabled="page === 1" @click="changePage(-1)">上一页</button><button class="pagination-button" :disabled="page * 20 >= total" @click="changePage(1)">下一页</button></div></div>
  </template>
  <p class="page-footnote"><span class="tiny-dot" />文档保存在数据库。发布后需建立知识索引，才能参与工单检索。</p>
</template>
