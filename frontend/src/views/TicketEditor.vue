<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { getCatalog } from '../api/config'
import type { Catalog } from '../api/config'
import { listUsers } from '../api/users'
import { createTicket, getTicket, updateTicket } from '../api/tickets'
import type { TicketInput, User } from '../api/models'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const ticketId = route.params.id ? Number(route.params.id) : null
const priorities = ['P1', 'P2', 'P3', 'P4'] as const
const catalog = ref<Catalog>({
  products: [],
  modules: [],
  categories: [],
})
const users = ref<User[]>([])
// 新建时下拉框尚未选择，用 undefined 表示；提交前再检查必填项。
interface TicketForm {
  title: string
  description: string
  customer_name: string
  customer_email: string
  product_id: number | undefined
  module_id: number | undefined
  category_id: number | undefined
  owner_id: number | undefined
  priority: TicketInput['priority'] | undefined
}
const form = reactive<TicketForm>({
  title: '',
  description: '',
  customer_name: '',
  customer_email: '',
  product_id: undefined,
  module_id: undefined,
  category_id: undefined,
  owner_id: undefined,
  priority: undefined,
})
const modules = computed(() =>
  catalog.value.modules.filter((item) => item.product_id === form.product_id),
)
const error = ref('')
const loading = ref(true)
const loaded = ref(false)
const isClosed = ref(false)
const submitting = ref(false)
let initialFormSnapshot = ''
let saved = false
onBeforeRouteLeave(() => {
  if (saved || !loaded.value) return true
  const hasUnsavedChanges = JSON.stringify(form) !== initialFormSnapshot
  if (!hasUnsavedChanges) return true
  return window.confirm('未保存的修改将丢失，确定离开吗？')
})
onMounted(async () => {
  try {
    const [config, members] = await Promise.all([getCatalog(auth.token), listUsers(auth.token)])
    catalog.value = config
    users.value = members
    if (ticketId !== null) {
      const ticket = await getTicket(auth.token, ticketId)
      form.title = ticket.title
      form.description = ticket.description
      form.customer_name = ticket.customer_name
      form.customer_email = ticket.customer_email
      form.product_id = ticket.product_id
      form.module_id = ticket.module_id
      form.category_id = ticket.category_id
      form.owner_id = ticket.owner_id ?? undefined
      form.priority = ticket.priority
      isClosed.value = ticket.status === 'closed'
    }
    initialFormSnapshot = JSON.stringify(form)
    loaded.value = true
  } catch (caught) {
    if (!(caught instanceof Error)) throw caught
    error.value = caught.message
  } finally {
    loading.value = false
  }
})

async function submit() {
  if (submitting.value) return
  error.value = ''
  if (
    form.product_id === undefined ||
    form.module_id === undefined ||
    form.category_id === undefined ||
    form.priority === undefined
  ) {
    error.value = '请选择产品、模块、分类和优先级'
    return
  }
  const body: TicketInput = {
    title: form.title,
    description: form.description,
    customer_name: form.customer_name,
    customer_email: form.customer_email,
    product_id: form.product_id,
    module_id: form.module_id,
    category_id: form.category_id,
    priority: form.priority,
  }
  submitting.value = true
  try {
    let ticket
    if (ticketId === null) {
      ticket = await createTicket(auth.token, body)
    } else {
      if (form.owner_id === undefined) {
        error.value = '请选择负责人'
        return
      }
      ticket = await updateTicket(auth.token, ticketId, { ...body, owner_id: form.owner_id })
    }
    saved = true
    await router.push(`/tickets/${ticket.id}`)
  } catch (caught) {
    if (!(caught instanceof Error)) throw caught
    error.value = caught.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="breadcrumb">
    <RouterLink to="/tickets">工单管理</RouterLink>
    <span>/</span>
    <span>{{ ticketId ? '编辑工单' : '新建工单' }}</span>
  </div>
  <div class="page-heading">
    <div>
      <h1>{{ ticketId ? '编辑工单' : '新建工单' }}</h1>
      <p>把问题描述清楚，处理就有了好的起点。</p>
    </div>
  </div>
  <p v-if="loading" role="status">正在读取表单资料……</p>
  <p v-if="error && !loaded" class="error" role="alert">
    {{ error }}
  </p>
  <form v-if="loaded && !isClosed" class="panel editor-panel" @submit.prevent="submit">
    <div class="section-heading">
      <span class="section-number">01</span>
      <div>
        <h2>问题信息</h2>
        <p>描述遇到的问题，并为它选择合适的分类。</p>
      </div>
    </div>
    <div class="field-grid">
      <label class="field full" for="ticket-title">
        <span>
          工单标题
          <em>*</em>
        </span>
        <input
          id="ticket-title"
          v-model="form.title"
          maxlength="200"
          required
          placeholder="一句话概括客户遇到的问题"
        />
      </label>
      <label class="field full" for="ticket-description">
        <span>
          问题描述
          <em>*</em>
        </span>
        <textarea
          id="ticket-description"
          v-model="form.description"
          rows="6"
          maxlength="10000"
          required
          placeholder="建议描述：问题现象、出现时间、复现步骤以及已尝试的方法。请勿填写密码或密钥。"
        />
        <small>{{ form.description.length }} / 10000</small>
      </label>
      <label class="field" for="ticket-product">
        <span>
          所属产品
          <em>*</em>
        </span>
        <select
          id="ticket-product"
          v-model="form.product_id"
          required
          @change="form.module_id = undefined"
        >
          <option :value="undefined" disabled>选择产品</option>
          <option
            v-for="product in catalog.products"
            :key="product.id"
            :value="product.id"
            :disabled="!product.is_active"
          >
            {{ product.name }}
          </option>
        </select>
      </label>
      <label class="field" for="ticket-module">
        <span>
          所属模块
          <em>*</em>
        </span>
        <select id="ticket-module" v-model="form.module_id" :disabled="!form.product_id" required>
          <option :value="undefined" disabled>选择产品后选择模块</option>
          <option
            v-for="item in modules"
            :key="item.id"
            :value="item.id"
            :disabled="!item.is_active"
          >
            {{ item.name }}
          </option>
        </select>
      </label>
      <label class="field" for="ticket-category">
        <span>
          问题分类
          <em>*</em>
        </span>
        <select id="ticket-category" v-model="form.category_id" required>
          <option :value="undefined" disabled>选择问题分类</option>
          <option
            v-for="category in catalog.categories"
            :key="category.id"
            :value="category.id"
            :disabled="!category.is_active"
          >
            {{ category.name }}
          </option>
        </select>
      </label>
      <label class="field" for="ticket-priority">
        <span>
          优先级
          <em>*</em>
        </span>
        <select id="ticket-priority" v-model="form.priority" required>
          <option :value="undefined" disabled>选择优先级</option>
          <option v-for="(priority, index) in priorities" :key="priority" :value="priority">
            {{ priority }} · {{ ['紧急', '高', '中', '低'][index] }}
          </option>
        </select>
      </label>
    </div>
    <div class="section-heading with-border">
      <span class="section-number">02</span>
      <div>
        <h2>客户信息</h2>
        <p>填写客户联系信息，本阶段不会自动发送邮件。</p>
      </div>
    </div>
    <div class="field-grid">
      <label class="field" for="customer-name">
        <span>
          客户姓名
          <em>*</em>
        </span>
        <input
          id="customer-name"
          v-model="form.customer_name"
          maxlength="100"
          placeholder="客户称呼"
          required
        />
      </label>
      <label class="field" for="customer-email">
        <span>
          客户邮箱
          <em>*</em>
        </span>
        <input
          id="customer-email"
          v-model="form.customer_email"
          type="email"
          maxlength="320"
          placeholder="customer@example.com"
          required
        />
        <small>仅保存联系信息，不会自动发送邮件。</small>
      </label>
    </div>
    <label v-if="ticketId" class="field">
      <span>负责人</span>
      <select v-model="form.owner_id" required>
        <option v-for="user in users" :key="user.id" :value="user.id" :disabled="!user.is_active">
          {{ user.display_name }}
        </option>
      </select>
    </label>
    <p v-if="error" class="error" role="alert">
      {{ error }}
    </p>
    <div class="form-footer">
      <span>创建后为待处理，负责人为当前登录用户。</span>
      <div class="actions">
        <RouterLink to="/tickets" class="button outline">取消</RouterLink>
        <button type="submit" class="button primary" :disabled="submitting">
          {{ submitting ? '保存中……' : '保存工单' }}
        </button>
      </div>
    </div>
  </form>
  <p v-if="isClosed" class="panel">
    工单已关闭，只能查看。
    <RouterLink :to="`/tickets/${ticketId}`">返回详情</RouterLink>
  </p>
</template>
