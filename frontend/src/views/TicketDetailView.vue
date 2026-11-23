<script setup lang="ts">
import AssistancePanel from '../components/AssistancePanel.vue'
import BasicAnalysisPanel from '../components/BasicAnalysisPanel.vue'
import EmailPanel from '../components/EmailPanel.vue'
import SourcePreview from '../components/SourcePreview.vue'
import SimilarCases from '../components/SimilarCases.vue'
import KnowledgeMatches from '../components/KnowledgeMatches.vue'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { statusLabels, statusSchema } from '../api/models'
import type { TicketDetail, User } from '../api/models'
import { getCatalog } from '../api/config'
import type { Catalog } from '../api/config'
import { listUsers } from '../api/users'
import { getTicket, startTicket, addNote, resolveTicket, closeTicket } from '../api/tickets'
import { useAuthStore } from '../stores/auth'
import { formatTime } from '../utils/format'

const route = useRoute()
const auth = useAuthStore()
const ticketId = Number(route.params.id)
const ticket = ref<TicketDetail | null>(null)
const catalog = ref<Catalog>({
  products: [],
  modules: [],
  categories: [],
})
const users = ref<User[]>([])
const statuses = statusSchema.options
const content = ref('')
const solution = ref('')
const resolveOpen = ref(false)
const replyConfirmed = ref(false)
const error = ref('')
const loading = ref(true)
const busy = ref(false)
const preview = ref<{ kind: 'ticket' | 'knowledge'; id: number } | null>(null)
const activeTab = ref<'records' | 'assistance' | 'email'>('records')
const tabs = [
  { id: 'records', label: '处理记录' },
  { id: 'assistance', label: 'AI 建议' },
  { id: 'email', label: '客户邮件' },
] as const
function onTabKeydown(event: KeyboardEvent, index: number) {
  let next = index
  if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
  else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = tabs.length - 1
  else return
  event.preventDefault()
  const target = tabs[next]
  if (!target) return
  activeTab.value = target.id
  const buttons = (event.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
  void nextTick(() => buttons?.[next]?.focus())
}
const emailDraft = ref<{ id: number; subject: string; content: string } | null>(null)
function openEmail(draft: { id: number; subject: string; content: string }) {
  emailDraft.value = draft
  activeTab.value = 'email'
}
const categoryNames = computed(() => Object.fromEntries(catalog.value.categories.map(item => [item.id, item.name])))

// computed 会随工单和基础资料变化重新计算，模板只负责显示结果。
const productName = computed(
  () => catalog.value.products.find((item) => item.id === ticket.value?.product_id)?.name,
)
const moduleName = computed(
  () => catalog.value.modules.find((item) => item.id === ticket.value?.module_id)?.name,
)
const categoryName = computed(
  () => catalog.value.categories.find((item) => item.id === ticket.value?.category_id)?.name,
)
const userNames = computed(() => new Map(users.value.map((user) => [user.id, user.display_name])))
const actionLabels = {
  pending: '开始处理',
  processing: '标记已解决',
  resolved: '关闭工单',
  closed: '已关闭',
}

onMounted(async () => {
  try {
    const [detail, config, members] = await Promise.all([
      getTicket(auth.token, ticketId),
      getCatalog(auth.token),
      listUsers(auth.token),
    ])
    catalog.value = config
    users.value = members
    ticket.value = detail
  } catch (caught) {
    if (!(caught instanceof Error)) throw caught
    error.value = caught.message
  } finally {
    loading.value = false
  }
})
// 共用提交状态和错误提示；成功后用后端返回的完整工单更新页面。
async function perform(action: () => Promise<TicketDetail>): Promise<boolean> {
  if (busy.value) return false
  error.value = ''
  busy.value = true
  try {
    ticket.value = await action()
    return true
  } catch (caught) {
    if (!(caught instanceof Error)) throw caught
    error.value = caught.message
    return false
  } finally {
    busy.value = false
  }
}

async function addRecord() {
  if (await perform(() => addNote(auth.token, ticketId, content.value))) content.value = ''
}

async function primaryAction() {
  const status = ticket.value?.status
  if (status === 'processing') {
    resolveOpen.value = true
    return
  }
  if (status === 'pending') {
    await perform(() => startTicket(auth.token, ticketId))
    return
  }
  if (status === 'resolved' && replyConfirmed.value) {
    await perform(() => closeTicket(auth.token, ticketId))
  }
}

async function resolve() {
  if (await perform(() => resolveTicket(auth.token, ticketId, solution.value)))
    resolveOpen.value = false
}
</script>

<template>
  <template v-if="ticket">
    <div class="breadcrumb">
      <RouterLink to="/tickets">工单管理</RouterLink>
      <span>/</span>
      <span>{{ ticket.number }}</span>
    </div>
    <div class="detail-layout">
      <article class="ticket-detail">
        <div class="detail-top">
          <span class="ticket-code">{{ ticket.number }}</span>
          <RouterLink
            v-if="ticket.status !== 'closed'"
            :to="`/tickets/${ticket.id}/edit`"
            class="button outline"
          >
            编辑工单
          </RouterLink>
          <button
            :disabled="busy || (ticket.status === 'resolved' && !replyConfirmed)"
            v-if="ticket.status !== 'closed'"
            class="button primary"
            @click="primaryAction"
          >
            {{ actionLabels[ticket.status] }}
            <AppIcon name="arrow-right" :size="16" />
          </button>
          <span v-else class="closed-label">
            <AppIcon name="check" :size="17" />
            已归档，只读
          </span>
        </div>
        <h1 class="detail-title">{{ ticket.title }}</h1>
        <p class="detail-subtitle">
          创建于 {{ formatTime(ticket.created_at) }}
          <span>客户：{{ ticket.customer_name }} · {{ ticket.customer_email }}</span>
        </p>
        <div class="ticket-facts">
          <div>
            <small>当前状态</small>
            <StatusBadge :status="ticket.status" />
          </div>
          <div>
            <small>优先级</small>
            <span class="priority" :class="ticket.priority">
              <i />
              {{ ticket.priority }}
            </span>
          </div>
          <div>
            <small>所属产品</small>
            <span>{{ productName }}</span>
          </div>
          <div>
            <small>负责人</small>
            <span>{{ ticket.owner_id === null ? '等待接单' : userNames.get(ticket.owner_id) }}</span>
          </div>
        </div>
        <p v-if="error && !resolveOpen" class="error error-panel" role="alert">
          {{ error }}
        </p>
        <label v-if="ticket.status === 'resolved'" class="confirm-reply">
          <input v-model="replyConfirmed" type="checkbox" />
          我已人工回复客户，确认关闭此工单
        </label>
        <section class="detail-section">
          <h2>问题描述</h2>
          <p class="multiline description">{{ ticket.description }}</p>
          <dl class="detail-meta">
            <dt>问题分类</dt>
            <dd>{{ categoryName }}</dd>
            <dt>所属模块</dt>
            <dd>{{ moduleName }}</dd>
          </dl>
        </section>
        <section v-if="ticket.solution" class="solution-box">
          <h2>
            <AppIcon name="check" :size="18" />
            解决方案
          </h2>
          <p class="multiline">{{ ticket.solution }}</p>
        </section>
        <BasicAnalysisPanel :key="`analysis-${ticket.id}`" :ticket-id="ticket.id" :status="ticket.status"
          :categories="categoryNames" @adopted="perform(() => getTicket(auth.token, ticketId))" />
        <nav class="detail-tabs" role="tablist" aria-label="工单详情分区">
          <button v-for="(tab, index) in tabs" :key="tab.id" type="button" role="tab" :class="{ active: activeTab === tab.id }"
            :aria-selected="activeTab === tab.id" :aria-controls="`ticket-panel-${tab.id}`" :tabindex="activeTab === tab.id ? 0 : -1"
            @click="activeTab = tab.id" @keydown="onTabKeydown($event, index)">{{ tab.label }}</button>
        </nav>
        <section id="ticket-panel-records" v-show="activeTab === 'records'" role="tabpanel" class="detail-section">
          <div class="section-title">
            <h2>处理记录</h2>
            <span>{{ ticket.records.length }} 条动态</span>
          </div>
          <ol class="timeline">
            <li v-for="record in ticket.records" :key="record.id">
              <span class="timeline-dot" />
              <span class="avatar">{{ '·' }}</span>
              <div>
                <div class="record-heading">
                  <strong>{{ userNames.get(record.author_id) }}</strong>
                  <time>{{ formatTime(record.created_at) }}</time>
                </div>
                <p class="multiline">{{ record.content }}</p>
              </div>
            </li>
          </ol>
        </section>
        <form v-if="ticket.status !== 'closed'" v-show="activeTab === 'records'" class="record-form" @submit.prevent="addRecord">
          <label for="record-content"><h2>添加处理记录</h2></label>
          <div class="composer">
            <textarea
              id="record-content"
              v-model="content"
              rows="3"
              maxlength="10000"
              placeholder="记录排查进展、沟通结果或下一步计划……"
              required
            />
            <footer>
              <span>记录将保存到数据库</span>
              <button type="submit" class="button primary" :disabled="busy || !content.trim()">
                添加记录
              </button>
            </footer>
          </div>
        </form>
        <p v-else-if="activeTab === 'records'" class="readonly-note">此工单已关闭，问题描述、解决方案和处理记录均保留供查看。</p>
        <AssistancePanel id="ticket-panel-assistance" v-show="activeTab === 'assistance'" role="tabpanel" :key="ticket.id" :ticket-id="ticket.id" :status="ticket.status"
          :categories="categoryNames" @adopted="perform(() => getTicket(auth.token, ticketId))"
          @email="openEmail" @preview="preview = $event" />
        <EmailPanel id="ticket-panel-email" v-show="activeTab === 'email'" role="tabpanel" :key="`email-${ticket.id}`" :ticket-id="ticket.id"
          :status="ticket.status" :draft="emailDraft" />
      </article>
      <aside class="detail-reference-stack">
        <SimilarCases :key="ticket.id" :ticket-id="ticket.id" />
        <KnowledgeMatches :key="ticket.id" :ticket-id="ticket.id" />
        <section class="reference-rail">
          <h2>处理指引</h2>
          <p class="rail-caption">按顺序完成处理，所有状态变化都留有记录。</p>
          <div class="workflow">
            <h3>处理流程</h3>
            <ol>
              <li
                v-for="(status, index) in statuses"
                :key="status"
                :class="{
                  done: statuses.indexOf(ticket.status) > index,
                  current: ticket.status === status,
                }"
              >
                <span>{{ statuses.indexOf(ticket.status) > index ? '✓' : index + 1 }}</span>
                {{ statusLabels[status] }}
              </li>
            </ol>
          </div>
          <p class="rail-footnote">
            工单与处理记录已保存到数据库。历史案例仅供参考，采用方案前请核对当前问题。
          </p>
        </section>
      </aside>
    </div>
    <SourcePreview v-if="preview" :key="`${preview.kind}-${preview.id}`" :kind="preview.kind" :id="preview.id" @close="preview = null" />
    <el-dialog
      v-model="resolveOpen"
      title="保存解决方案"
      width="min(560px, 92vw)"
      :close-on-click-modal="false"
    >
      <p class="muted">填写已采取的措施和处理结果，再将工单标记为已解决。</p>
      <label class="field" for="solution-content">
        <span>解决方案</span>
        <textarea
          id="solution-content"
          v-model="solution"
          rows="6"
          maxlength="10000"
          placeholder="说明问题原因、解决步骤和核对结果"
        />
      </label>
      <p v-if="error" role="alert" class="error">
        {{ error }}
      </p>
      <template #footer>
        <button class="button outline" @click="resolveOpen = false">取消</button>
        <button class="button primary" :disabled="busy || !solution.trim()" @click="resolve">
          保存并标记已解决
        </button>
      </template>
    </el-dialog>
  </template>
  <section v-else class="empty-state panel">
    <h1>{{ loading ? '正在读取工单……' : '无法加载工单' }}</h1>
    <p v-if="error" role="alert">
      {{ error }}
    </p>
    <RouterLink to="/tickets" class="button primary">返回工单列表</RouterLink>
  </section>
</template>
