<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { getCatalog } from '../api/config'
import type { Catalog } from '../api/config'
import { listUsers } from '../api/users'
import { listTickets } from '../api/tickets'
import { statusSchema, prioritySchema, statusLabels } from '../api/models'
import type { Ticket, User } from '../api/models'
import { useAuthStore } from '../stores/auth'
import { formatTime } from '../utils/format'

const auth = useAuthStore()
const statuses = statusSchema.options
const priorities = prioritySchema.options
interface TicketListFilters {
  keyword: string
  status: 'all' | Ticket['status']
  priority: '' | Ticket['priority']
  product_id: '' | number
  module_id: '' | number
  category_id: '' | number
  owner_id: '' | number
  page: number
}
const filters = reactive<TicketListFilters>({
  keyword: '',
  status: 'all',
  priority: '',
  product_id: '',
  module_id: '',
  category_id: '',
  owner_id: '',
  page: 1,
})
const catalog = ref<Catalog>({
  products: [],
  modules: [],
  categories: [],
})
const users = ref<User[]>([])
const availableModules = computed(() =>
  catalog.value.modules.filter(
    (item) => !filters.product_id || item.product_id === filters.product_id,
  ),
)
// 名称只在资料变化时整理一次，桌面表格和手机卡片使用同一份结果。
const productNames = computed(
  () => new Map(catalog.value.products.map((product) => [product.id, product.name])),
)
const userNames = computed(() => new Map(users.value.map((user) => [user.id, user.display_name])))
const rows = ref<Ticket[]>([])
const total = ref(0)
const pageSize = ref(20)
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const loading = ref(true)
const error = ref('')
let requestNumber = 0
async function load() {
  const currentRequest = ++requestNumber
  loading.value = true
  error.value = ''
  try {
    const result = await listTickets(auth.token, {
      page: filters.page,
      keyword: filters.keyword.trim(),
      status: filters.status === 'all' ? undefined : filters.status,
      priority: filters.priority || undefined,
      product_id: filters.product_id || undefined,
      module_id: filters.module_id || undefined,
      category_id: filters.category_id || undefined,
      owner_id: filters.owner_id || undefined,
    })
    // 快速切换筛选时，较早的响应不能覆盖最近一次查询。
    if (currentRequest !== requestNumber) return
    rows.value = result.items
    total.value = result.total
    pageSize.value = result.page_size
  } catch (caught) {
    if (!(caught instanceof Error)) throw caught
    if (currentRequest !== requestNumber) return
    rows.value = []
    error.value = caught.message
  } finally {
    if (currentRequest === requestNumber) loading.value = false
  }
}
function search() {
  if (filters.page !== 1) {
    // 改变页码会触发下面的 watch，由它加载第一页。
    filters.page = 1
    return
  }
  void load()
}
function clearFilters() {
  Object.assign(filters, {
    keyword: '',
    status: 'all',
    priority: '',
    product_id: '',
    module_id: '',
    category_id: '',
    owner_id: '',
    page: 1,
  })
  void load()
}
watch(
  () => filters.product_id,
  () => {
    filters.module_id = ''
  },
)
watch(
  () => [
    filters.status,
    filters.priority,
    filters.product_id,
    filters.module_id,
    filters.category_id,
    filters.owner_id,
  ],
  search,
)
watch(
  () => filters.page,
  () => {
    void load()
  },
)
onMounted(async () => {
  try {
    const [config, members] = await Promise.all([getCatalog(auth.token), listUsers(auth.token)])
    catalog.value = config
    users.value = members
    await load()
  } catch (caught) {
    if (!(caught instanceof Error)) throw caught
    error.value = caught.message
    loading.value = false
  }
})
</script>

<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">客户支持 / 工单管理</div>
      <h1>
        工单管理
        <span class="heading-count">{{ total }}</span>
      </h1>
      <p>每一个问题，都有清晰的下一步。</p>
    </div>
    <RouterLink to="/tickets/new" class="button primary">
      <AppIcon name="plus" :size="18" />
      新建工单
    </RouterLink>
  </div>
  <p v-if="error" class="error" role="alert">
    {{ error }}
  </p>
  <section class="panel list-panel" aria-label="工单列表">
    <div class="list-toolbar">
      <div class="status-tabs" aria-label="工单状态筛选">
        <button
          :class="{ active: filters.status === 'all' }"
          :aria-pressed="filters.status === 'all'"
          @click="filters.status = 'all'"
        >
          全部工单
          <span>{{ total }}</span>
        </button>
        <button
          v-for="status in statuses"
          :key="status"
          :class="{ active: filters.status === status }"
          :aria-pressed="filters.status === status"
          @click="filters.status = status"
        >
          {{ statusLabels[status] }}
        </button>
      </div>
      <div class="list-filters">
        <label class="search-box">
          <AppIcon name="search" :size="17" />
          <input
            v-model="filters.keyword"
            type="search"
            @keydown.enter="search"
            aria-label="搜索工单"
            placeholder="搜索标题或问题描述"
          />
        </label>
        <select v-model="filters.priority" aria-label="筛选优先级">
          <option value="">全部优先级</option>
          <option v-for="priority in priorities" :key="priority">
            {{ priority }}
          </option>
        </select>
        <select v-model="filters.product_id" aria-label="筛选产品">
          <option value="">全部产品</option>
          <option v-for="product in catalog.products" :key="product.id" :value="product.id">
            {{ product.name }}
          </option>
        </select>
        <button class="button outline" :disabled="loading" @click="search">查询</button>
        <button class="text-button" @click="clearFilters">重置</button>
        <select v-model="filters.module_id" aria-label="筛选模块">
          <option value="">全部模块</option>
          <option v-for="item in availableModules" :key="item.id" :value="item.id">
            {{ item.name }}
          </option>
        </select>
        <select v-model="filters.category_id" aria-label="筛选分类">
          <option value="">全部分类</option>
          <option v-for="item in catalog.categories" :key="item.id" :value="item.id">
            {{ item.name }}
          </option>
        </select>
        <select v-model="filters.owner_id" aria-label="筛选负责人">
          <option value="">全部负责人</option>
          <option v-for="item in users" :key="item.id" :value="item.id">
            {{ item.display_name }}
          </option>
        </select>
      </div>
    </div>
    <p v-if="loading" role="status" class="panel">正在加载工单……</p>
    <div v-else-if="rows.length" class="table-scroll">
      <table class="ticket-table">
        <thead>
          <tr>
            <th>工单 / 问题描述</th>
            <th>状态</th>
            <th>优先级</th>
            <th>产品</th>
            <th>负责人</th>
            <th>更新时间</th>
            <th><span class="sr-only">查看详情</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ticket in rows" :key="ticket.id">
            <td class="ticket-title-cell">
              <RouterLink :to="`/tickets/${ticket.id}`" class="ticket-title">
                {{ ticket.title }}
              </RouterLink>
              <div class="ticket-sub">
                <span>{{ ticket.number }}</span>
                <i />
                {{ ticket.customer_name }}
              </div>
            </td>
            <td><StatusBadge :status="ticket.status" /></td>
            <td>
              <span class="priority" :class="ticket.priority">
                <i />
                {{ ticket.priority }}
              </span>
            </td>
            <td class="cell-muted">{{ productNames.get(ticket.product_id) }}</td>
            <td>
              <span class="owner-cell">
                <span class="avatar small">{{ '·' }}</span>
                {{ ticket.owner_id === null ? '等待接单' : userNames.get(ticket.owner_id) }}
              </span>
            </td>
            <td class="cell-muted time-cell">{{ formatTime(ticket.updated_at) }}</td>
            <td>
              <RouterLink
                :to="`/tickets/${ticket.id}`"
                class="icon-button"
                :aria-label="`查看${ticket.number}详情`"
              >
                <AppIcon name="arrow-right" :size="17" />
              </RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="ticket-cards">
        <RouterLink
          v-for="ticket in rows"
          :key="ticket.id"
          :to="`/tickets/${ticket.id}`"
          class="ticket-mobile-card"
        >
          <span class="ticket-sub">
            {{ ticket.number }}
            <span class="priority" :class="ticket.priority">
              <i />
              {{ ticket.priority }}
            </span>
          </span>
          <strong>{{ ticket.title }}</strong>
          <span class="mobile-card-meta">
            <StatusBadge :status="ticket.status" />
            <span>{{ productNames.get(ticket.product_id) }}</span>
            <AppIcon name="arrow-right" :size="16" />
          </span>
        </RouterLink>
      </div>
    </div>
    <div v-else-if="!error" class="empty-state">
      <AppIcon name="search" :size="32" />
      <h3>没有找到匹配的工单</h3>
      <p>换个关键词，或清除筛选条件再试试。</p>
      <button class="button outline" @click="clearFilters">清除筛选</button>
    </div>
    <footer class="pagination">
      <span>共 {{ total }} 条 · 第 {{ filters.page }} / {{ pages }} 页</span>
      <div>
        <button
          class="pagination-button"
          :disabled="loading || filters.page <= 1"
          @click="filters.page--"
        >
          上一页
        </button>
        <span class="page-number">{{ filters.page }}</span>
        <button
          class="pagination-button"
          :disabled="loading || filters.page >= pages"
          @click="filters.page++"
        >
          下一页
        </button>
      </div>
    </footer>
  </section>
  <p class="page-footnote">
    <span class="tiny-dot" />
    工单从数据库读取；当前阶段的关闭操作需要人工确认已回复客户。
  </p>
</template>
