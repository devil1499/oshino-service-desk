<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import {
  tierNames,
  levelNames,
  serviceStatus,
  serviceProducts,
  serviceList,
  serviceDetail,
  newService,
  serviceAction,
  type ServiceCard,
  type ServiceDetail,
} from '../api/service'

const auth = useAuthStore()
const customer = computed(() => auth.user?.role === 'customer')
const rows = ref<ServiceCard[]>([])
const selected = ref<ServiceDetail | null>(null)
const chatLog = ref<HTMLElement | null>(null)
const products = ref<{ id: number; name: string }[]>([])
const productId = ref(0)
const title = ref('')
const text = ref('')
const reason = ref('')
const priority = ref('P2')
const level = ref(1)
const tab = ref('all')
const keyword = ref('')
const page = ref(1)
const more = ref(false)
const busy = ref(false)
const error = ref('')
const dialog = ref<'handoff' | 'transfer' | 'resolve' | null>(null)
let timer: number | undefined
let disposed = false
let selectionVersion = 0
const visible = computed(() =>
  rows.value.filter(
    (row) =>
      (!keyword.value ||
        (row.title + row.customer_name).includes(keyword.value)) &&
      (tab.value === 'all' ||
        tab.value === row.status ||
        (tab.value === 'mine' && row.owner_id === auth.user?.id)),
  ),
)
const canHandle = computed(
  () =>
    selected.value &&
    (selected.value.owner_id === auth.user?.id || auth.user?.role === 'admin'),
)
const running = computed(() =>
  selected.value?.messages.some((m) => m.status === 'running'),
)
const events = computed(() => {
  if (!selected.value) return []
  return [
    ...selected.value.messages.map((m) => ({
      key: `m${m.id}`,
      customer: m.role === 'user',
      system: false,
      label:
        m.role === 'user' ? selected.value!.customer_name : 'Oshino 智能助手',
      text: m.content || '正在检索与生成回答…',
      time: m.created_at,
      sources: m.sources,
      failed: m.status === 'failed',
    })),
    ...selected.value.records.map((r) => ({
      key: `r${r.id}`,
      customer: r.kind === 'service_customer',
      system: !['service_customer', 'service_reply'].includes(r.kind),
      label: r.kind === 'service_reply' ? '人工客服' : '服务记录',
      text: r.content,
      time: r.created_at,
      sources: [],
      failed: false,
    })),
  ].sort((a, b) => Date.parse(a.time) - Date.parse(b.time))
})

// 只在打开会话或正在阅读最新消息时跟随滚动，保留翻看旧记录的位置。
watch(
  () => [selected.value?.id, events.value.length],
  async ([id], [previousId]) => {
    const log = chatLog.value
    const follow =
      id !== previousId ||
      !log ||
      log.scrollHeight - log.scrollTop - log.clientHeight < 100
    await nextTick()
    if (follow && chatLog.value)
      chatLog.value.scrollTop = chatLog.value.scrollHeight
  },
)

async function refresh() {
  await run(async () => {
    await loadList()
    if (selected.value) await choose(selected.value.id)
  })
  window.clearTimeout(timer)
  void poll()
}
async function loadList() {
  const result = await serviceList(auth.token, page.value)
  rows.value = result.items
  more.value = result.has_more
}
async function choose(id: number) {
  const version = ++selectionVersion
  try {
    const result = await serviceDetail(auth.token, id)
    if (version === selectionVersion) {
      selected.value = result
      priority.value = result.priority ?? 'P2'
      level.value = result.required_level
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取失败'
  }
}
async function run(action: () => Promise<void>) {
  busy.value = true
  error.value = ''
  try {
    await action()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '操作失败'
  } finally {
    busy.value = false
  }
}
async function create() {
  await run(async () => {
    const row = await newService(auth.token, productId.value, title.value)
    page.value = 1
    await loadList()
    await choose(row.id)
    title.value = ''
  })
}
async function act(action: string, body?: unknown) {
  const id = selected.value?.id
  if (!id) return
  await run(async () => {
    await serviceAction(auth.token, id, action, body)
    dialog.value = null
    reason.value = ''
    await choose(id)
    await loadList()
  })
}
function openDialog(value: 'handoff' | 'transfer' | 'resolve') {
  dialog.value = value
  reason.value = value === 'handoff' ? (selected.value?.title ?? '') : ''
  level.value = selected.value?.required_level ?? 1
}
async function submitDialog() {
  if (dialog.value === 'handoff')
    await act('handoff', {
      description: reason.value,
      priority: priority.value,
    })
  else if (dialog.value === 'transfer')
    await act('transfer', { text: reason.value, level: level.value })
  else if (dialog.value === 'resolve')
    await act('resolve', { text: reason.value })
}
async function send() {
  if (!selected.value || !text.value.trim()) return
  if (
    customer.value &&
    selected.value.status === 'ai' &&
    text.value.trim() === '转人工'
  ) {
    openDialog('handoff')
    return
  }
  const id = selected.value.id
  const bodyText = text.value.trim()
  await run(async () => {
    try {
      await serviceAction(
        auth.token,
        id,
        selected.value!.status === 'ai' ? 'ai' : 'reply',
        selected.value!.status === 'ai'
          ? { text: bodyText, request_id: crypto.randomUUID() }
          : { text: bodyText },
      )
      text.value = ''
    } finally {
      await choose(id)
    }
  })
}
async function older() {
  if (!selected.value?.messages.length) return
  const id = selected.value.id
  await run(async () => {
    const result = await serviceDetail(
      auth.token,
      id,
      selected.value!.messages[0]!.id,
    )
    if (selected.value?.id === id) {
      selected.value.messages = [...result.messages, ...selected.value.messages]
      selected.value.has_older = result.has_older
    }
  })
}
async function changePage(delta: number) {
  page.value += delta
  await run(loadList)
}
function back() {
  selectionVersion++
  selected.value = null
  dialog.value = null
  void run(loadList)
}
async function poll() {
  if (disposed) return
  try {
    if (!busy.value && selected.value && selected.value.status !== 'closed') {
      const id = selected.value.id
      const result = await serviceDetail(auth.token, id)
      if (selected.value?.id === id) {
        const olderMessages = selected.value.messages.filter(
          (m) => result.messages.length && m.id < result.messages[0]!.id,
        )
        selected.value = {
          ...result,
          messages: [...olderMessages, ...result.messages],
          has_older: olderMessages.length
            ? selected.value.has_older
            : result.has_older,
        }
      }
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取进度失败'
    return
  }
  if (!disposed) timer = window.setTimeout(poll, 4000)
}
onMounted(async () => {
  await run(async () => {
    if (customer.value) products.value = await serviceProducts(auth.token)
    await loadList()
  })
  void poll()
})
onUnmounted(() => {
  disposed = true
  selectionVersion++
  window.clearTimeout(timer)
})
</script>

<template>
  <div class="service-page">
    <header class="service-heading">
      <div>
        <div class="eyebrow">Oshino 数码售后 · 本地演示</div>
        <h1>{{ customer ? '服务咨询' : '客服工作台' }}</h1>
        <p>
          {{
            customer
              ? '对话记录与处理进度，随时可查。'
              : '先处理严重问题，再按客户等级与等待时间排序。'
          }}
        </p>
      </div>
      <RouterLink to="/service/rules" class="button outline">{{
        customer ? '用户守则' : '客服守则'
      }}</RouterLink>
    </header>
    <div v-if="error" class="error error-panel" role="alert">
      {{ error }} <button @click="refresh">重新连接</button>
    </div>
    <template v-if="!selected">
      <form v-if="customer" class="service-new" @submit.prevent="create">
        <div>
          <h2>开始一次咨询</h2>
          <p>先选择产品，智能助手会查找相关使用与售后资料。</p>
        </div>
        <label
          >咨询产品<select v-model.number="productId" required>
            <option :value="0" disabled>请选择产品</option>
            <option v-for="p in products" :key="p.id" :value="p.id">
              {{ p.name }}
            </option>
          </select></label
        ><label
          >问题简述<input
            v-model="title"
            required
            maxlength="100"
            placeholder="如：耳机无法连接手机" /></label
        ><button class="button primary" :disabled="busy || !productId">
          开始咨询 →
        </button>
      </form>
      <div v-else class="service-stats">
        <div
          v-for="item in [
            ['pending', '待接单'],
            ['processing', '处理中'],
            ['resolved', '待客户确认'],
            ['closed', '已完成'],
          ]"
          :key="item[0]"
        >
          <span>{{ item[1] }} · 本页</span
          ><strong>{{
            rows.filter((r) => r.status === item[0]).length
          }}</strong>
        </div>
      </div>
      <section class="service-table-card">
        <div class="service-toolbar">
          <div class="service-tabs">
            <button
              v-for="item in [
                ['all', customer ? '全部咨询' : '全部工单'],
                ['pending', '待接单'],
                ['mine', '我的处理'],
                ['processing', '处理中'],
                ['resolved', '待确认'],
              ]"
              v-show="item[0] !== 'mine' || !customer"
              :key="item[0]"
              :class="{ selected: tab === item[0] }"
              @click="tab = item[0]!"
            >
              {{ item[1] }}
            </button>
          </div>
          <input v-model="keyword" placeholder="搜索本页问题、客户…" /><button
            class="button outline"
            :disabled="busy"
            @click="run(loadList)"
          >
            刷新
          </button>
        </div>
        <table class="service-table">
          <thead>
            <tr>
              <th>工单 / 问题</th>
              <th>优先级</th>
              <th>客户等级</th>
              <th>状态</th>
              <th>处理客服</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in visible" :key="row.id">
              <td>
                <strong>{{ row.title }}</strong
                ><small
                  >{{
                    row.ticket_id
                      ? `T${String(row.ticket_id).padStart(6, '0')}`
                      : '智能咨询'
                  }}
                  · {{ row.product_name }}</small
                >
              </td>
              <td>
                <span
                  v-if="row.priority"
                  class="service-priority"
                  :class="row.priority"
                  >{{ row.priority }}</span
                ><span v-else>—</span>
              </td>
              <td>
                <span
                  class="service-tier"
                  :class="`tier-${row.customer_tier}`"
                  >{{ tierNames[row.customer_tier] }}</span
                >
              </td>
              <td>{{ serviceStatus[row.status] }}</td>
              <td>
                {{
                  row.owner_name
                    ? `${row.owner_name} · L${row.staff_level}`
                    : row.status === 'ai'
                      ? '智能助手'
                      : `等待 L${row.required_level} 及以上客服`
                }}
              </td>
              <td>
                <button
                  class="button outline"
                  :disabled="busy"
                  @click="choose(row.id)"
                >
                  {{ customer ? '继续沟通' : '查看 / 接单' }}
                </button>
              </td>
            </tr>
            <tr v-if="!visible.length">
              <td colspan="6" class="service-empty">暂无符合条件的记录</td>
            </tr>
          </tbody>
        </table>
        <footer class="service-pagination">
          <button :disabled="page === 1 || busy" @click="changePage(-1)">
            上一页</button
          ><span>第 {{ page }} 页 · 每页最多 50 条</span
          ><button :disabled="!more || busy" @click="changePage(1)">
            下一页
          </button>
        </footer>
      </section>
      <div v-if="!customer" class="service-levels">
        <h2>客服分级与转交</h2>
        <span v-for="n in [1, 2, 3]" :key="n"
          ><b>L{{ n }} {{ levelNames[n] }}</b
          >{{
            [
              '',
              '日常咨询与基础排查',
              '技术故障与复杂排查',
              '投诉处理与售后协调',
            ][n]
          }}</span
        >
        <p>换客服沿用原工单和记录，接单后可提交处理结果或说明原因转交。</p>
      </div>
    </template>
    <template v-else>
      <button class="service-back" @click="back">
        ← 返回{{ customer ? '我的咨询' : '工单队列' }}
      </button>
      <div class="service-conversation-layout">
        <section class="service-chat">
          <header>
            <h2>{{ selected.title }}</h2>
            <span class="service-state">{{
              serviceStatus[selected.status]
            }}</span>
          </header>
          <div ref="chatLog" class="service-chat-log">
            <button v-if="selected.has_older" @click="older">
              读取更早的咨询
            </button>
            <p v-if="!events.length" class="service-empty">
              描述问题，智能助手将根据产品知识为您解答。
            </p>
            <article
              v-for="event in events"
              :key="event.key"
              :class="[
                'service-event',
                {
                  'from-customer': event.customer,
                  'is-system': event.system,
                  'is-failed': event.failed,
                },
              ]"
            >
              <small
                >{{ event.label }} ·
                {{
                  new Date(event.time).toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                }}</small
              >
              <p>{{ event.text }}</p>
              <details v-for="source in event.sources" :key="source.source_id">
                <summary>{{ source.source_id }} · {{ source.title }}</summary>
                {{ source.content }}
              </details>
            </article>
          </div>
          <form
            v-if="
              selected.status !== 'closed' &&
              (customer || (canHandle && selected.status === 'processing'))
            "
            class="service-composer"
            @submit.prevent="send"
          >
            <textarea
              v-model="text"
              :disabled="busy || running"
              maxlength="2000"
              placeholder="输入消息，继续沟通…"
              required
            />
            <div>
              <span>{{
                selected.status === 'ai'
                  ? '可以输入“转人工”，或点击右侧按钮。'
                  : selected.status === 'pending'
                    ? '正在等待客服，您可以继续补充问题。'
                    : '消息保存在当前服务会话中。'
              }}</span
              ><button
                class="button primary"
                :disabled="busy || running || !text.trim()"
              >
                {{ busy ? '处理中…' : '发送' }}
              </button>
            </div>
          </form>
        </section>
        <aside class="service-summary">
          <section>
            <div class="service-product-art">
              <svg viewBox="0 0 160 100" aria-hidden="true">
                <rect
                  x="35"
                  y="48"
                  width="90"
                  height="45"
                  rx="20"
                  fill="#dae6f4"
                  stroke="#acbfd8"
                />
                <path d="M36 63h88" stroke="#acbfd8" />
                <rect
                  x="54"
                  y="19"
                  width="13"
                  height="40"
                  rx="6"
                  fill="#fff"
                  stroke="#acbfd8"
                />
                <ellipse
                  cx="58"
                  cy="19"
                  rx="16"
                  ry="12"
                  fill="#fff"
                  stroke="#acbfd8"
                />
                <rect
                  x="94"
                  y="19"
                  width="13"
                  height="40"
                  rx="6"
                  fill="#fff"
                  stroke="#acbfd8"
                />
                <ellipse
                  cx="103"
                  cy="19"
                  rx="16"
                  ry="12"
                  fill="#fff"
                  stroke="#acbfd8"
                />
              </svg>
            </div>
            <h2>{{ selected.product_name }}</h2>
            <p class="muted">虚构产品 · 毕业设计演示</p>
            <dl>
              <dt>工单编号</dt>
              <dd>
                {{
                  selected.ticket_id
                    ? `T${String(selected.ticket_id).padStart(6, '0')}`
                    : '尚未转人工'
                }}
              </dd>
              <dt>客户等级</dt>
              <dd>{{ tierNames[selected.customer_tier] }}</dd>
              <dt>优先级</dt>
              <dd>{{ selected.priority ?? '尚未定级' }}</dd>
              <dt>当前客服</dt>
              <dd>{{ selected.owner_name ?? '尚未接入' }}</dd>
              <dt>处理级别</dt>
              <dd>L{{ selected.required_level }}</dd>
            </dl>
            <div class="service-progress">
              <span :class="{ done: selected.status !== 'ai' }">① 智能咨询</span
              ><span
                :class="{
                  done: ['resolved', 'closed'].includes(selected.status),
                }"
                >② 人工处理</span
              ><span :class="{ done: selected.status === 'closed' }"
                >③ 确认结果</span
              >
            </div>
          </section>
          <section class="service-actions">
            <template v-if="customer"
              ><button
                v-if="selected.status === 'ai'"
                class="button primary"
                :disabled="busy || running"
                @click="openDialog('handoff')"
              >
                转人工服务</button
              ><button
                v-if="['processing', 'resolved'].includes(selected.status)"
                class="button outline"
                :disabled="busy"
                @click="openDialog('transfer')"
              >
                申请更换客服</button
              ><button
                v-if="selected.status === 'resolved'"
                class="button primary"
                :disabled="busy"
                @click="act('confirm')"
              >
                确认问题已解决
              </button></template
            ><template v-else
              ><button
                v-if="selected.status === 'pending'"
                class="button primary"
                :disabled="busy"
                @click="act('claim')"
              >
                接入这个工单</button
              ><template v-if="canHandle && selected.status === 'processing'"
                ><label
                  >核定严重程度<select v-model="priority">
                    <option v-for="p in ['P1', 'P2', 'P3', 'P4']" :key="p">
                      {{ p }}
                    </option>
                  </select></label
                ><button
                  class="button outline"
                  :disabled="busy"
                  @click="act('priority', { priority })"
                >
                  更新优先级</button
                ><button
                  class="button outline"
                  :disabled="busy"
                  @click="openDialog('transfer')"
                >
                  转交 / 升级</button
                ><button
                  class="button primary"
                  :disabled="busy"
                  @click="openDialog('resolve')"
                >
                  提交处理结果
                </button></template
              ></template
            >
            <p>更换客服后，已有记录会完整保留。</p>
          </section>
        </aside>
      </div>
    </template>
    <div v-if="dialog" class="service-modal-backdrop">
      <form class="service-modal" @submit.prevent="submitDialog">
        <h2>
          {{
            dialog === 'handoff'
              ? '转人工服务'
              : dialog === 'transfer'
                ? '说明转交原因'
                : '提交处理结果'
          }}
        </h2>
        <label
          >{{
            dialog === 'handoff'
              ? '问题描述与已尝试步骤'
              : dialog === 'transfer'
                ? '不满意原因或需要升级的事项'
                : '已完成的处理与结果'
          }}<textarea
            v-model="reason"
            required
            maxlength="4000"
            rows="5"
          /></label
        ><label v-if="dialog === 'handoff'"
          >问题严重程度<select v-model="priority">
            <option value="P1">P1 · 严重风险或大范围故障</option>
            <option value="P2">P2 · 核心功能无法使用</option>
            <option value="P3">P3 · 部分功能异常</option>
            <option value="P4">P4 · 普通咨询</option></select
          ><small>客服接入后会核实严重程度。</small></label
        ><label v-if="dialog === 'transfer' && !customer"
          >需要的客服等级<select v-model.number="level">
            <option v-for="n in [1, 2, 3]" :key="n" :value="n">
              L{{ n }} {{ levelNames[n] }}
            </option>
          </select></label
        >
        <footer>
          <button
            type="button"
            class="button outline"
            :disabled="busy"
            @click="dialog = null"
          >
            取消</button
          ><button class="button primary" :disabled="busy">确认提交</button>
        </footer>
      </form>
    </div>
  </div>
</template>

<style scoped>
.service-page {
  color: #20334f;
}
.service-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 28px;
}
.service-heading h1 {
  margin: 8px 0;
  font-size: 32px;
}
.service-heading p {
  color: #65758b;
}
.service-new,
.service-table-card,
.service-levels,
.service-chat,
.service-summary section {
  background: white;
  border: 1px solid #dce5f0;
  border-radius: 14px;
}
.service-new {
  padding: 26px;
  display: grid;
  grid-template-columns: 1.4fr 1fr 1.4fr auto;
  gap: 20px;
  align-items: end;
  margin-bottom: 24px;
}
.service-new h2 {
  font-size: 21px;
  margin: 0 0 10px;
}
.service-new p {
  font-size: 14px;
  color: #68798e;
}
.service-page label {
  display: grid;
  gap: 10px;
}
.service-page input,
.service-page select,
.service-page textarea {
  width: 100%;
  background: #f9fbfe;
  border: 1px solid #d5dfeb;
  border-radius: 7px;
  padding: 12px;
  font: inherit;
  color: #233752;
}
.service-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}
.service-stats div {
  background: white;
  border: 1px solid #e1e8f1;
  border-radius: 12px;
  padding: 24px;
  border-left: 4px solid #4b82dc;
}
.service-stats span {
  color: #6a7a8e;
}
.service-stats strong {
  display: block;
  font-size: 32px;
  margin-top: 12px;
}
.service-toolbar {
  padding: 22px;
  display: flex;
  gap: 14px;
  align-items: center;
  border-bottom: 1px solid #e4eaf2;
}
.service-toolbar input {
  max-width: 260px;
  margin-left: auto;
}
.service-tabs {
  display: flex;
  gap: 12px;
}
.service-tabs button {
  background: none;
  border: 0;
  padding: 12px 6px;
  color: #66778c;
  white-space: nowrap;
}
.service-tabs button.selected {
  color: #245ee0;
  border-bottom: 3px solid #245ee0;
}
.service-table {
  width: 100%;
  border-collapse: collapse;
}
.service-table th {
  text-align: left;
  background: #f5f8fc;
  color: #718098;
  font-size: 14px;
}
.service-table th,
.service-table td {
  padding: 19px;
  border-bottom: 1px solid #e7edf4;
}
.service-table td small {
  display: block;
  color: #74839a;
  margin-top: 7px;
}
.service-table td strong {
  font-weight: 600;
}
.service-priority,
.service-tier {
  border-radius: 5px;
  padding: 5px 9px;
  font-size: 14px;
  white-space: nowrap;
}
.P1 {
  background: #ffe3e3;
  color: #c83339;
}
.P2 {
  background: #fff0d8;
  color: #b86205;
}
.P3,
.P4 {
  background: #e6efff;
  color: #245ee0;
}
.tier-1 {
  background: #f5e7de;
  color: #976140;
}
.tier-2 {
  background: #e7eff9;
  color: #456b97;
}
.tier-3,
.tier-4 {
  background: #fff0ce;
  color: #946418;
}
.service-pagination {
  display: flex;
  justify-content: flex-end;
  gap: 20px;
  padding: 22px;
}
.service-pagination button,
.service-back {
  background: transparent;
  border: 0;
  color: #245ee0;
}
.service-empty {
  padding: 42px;
  text-align: center;
  color: #7a899d;
}
.service-levels {
  margin-top: 22px;
  padding: 24px;
}
.service-levels h2 {
  font-size: 19px;
}
.service-levels span {
  display: inline-flex;
  flex-direction: column;
  gap: 8px;
  margin-right: 45px;
  color: #66778d;
}
.service-levels b {
  color: #243956;
}
.service-levels p {
  color: #7a899b;
  margin-bottom: 0;
}
.service-back {
  margin-bottom: 20px;
  font-size: 16px;
}
.service-conversation-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 22px;
}
.service-chat {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: calc(100dvh - 270px);
  min-height: 530px;
}
.service-chat header {
  padding: 22px;
  border-bottom: 1px solid #e4ebf3;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.service-chat h2 {
  font-size: 21px;
  margin: 0;
}
.service-state {
  color: #19865d;
  background: #e4f5ed;
  padding: 7px 12px;
  border-radius: 6px;
}
.service-chat-log {
  padding: 25px;
  min-height: 0;
  overflow: auto;
  flex: 1;
}
.service-event {
  margin-bottom: 20px;
  max-width: 85%;
  font-size: 16px;
}
.service-event small {
  color: #6e7f95;
}
.service-event p {
  background: #f1f5fa;
  border-radius: 12px;
  padding: 16px;
  margin: 8px 0;
  white-space: pre-wrap;
  line-height: 1.8;
}
.service-event.from-customer {
  margin-left: auto;
}
.service-event.from-customer p {
  background: #e6efff;
}
.service-event.is-system {
  max-width: 100%;
  text-align: center;
}
.service-event.is-system p {
  background: #eef5ff;
  color: #3968ac;
  font-size: 14px;
}
.service-event.is-failed p {
  background: #fff0ee;
  color: #b43c30;
}
.service-event details {
  font-size: 14px;
  color: #527499;
  white-space: pre-wrap;
  margin-top: 8px;
}
.service-composer {
  padding: 20px;
  border-top: 1px solid #e4ebf3;
}
.service-composer textarea {
  resize: vertical;
  min-height: 90px;
}
.service-composer > div {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  gap: 10px;
}
.service-composer span {
  font-size: 13px;
  color: #71819a;
}
.service-summary section {
  padding: 22px;
  margin-bottom: 20px;
}
.service-product-art {
  height: 100px;
  background: #f2f6fc;
  border-radius: 10px;
  text-align: center;
}
.service-product-art svg {
  height: 100px;
}
.service-summary h2 {
  font-size: 19px;
}
.service-summary dl {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 15px;
  font-size: 14px;
}
.service-summary dt {
  color: #73839a;
}
.service-summary dd {
  margin: 0;
}
.service-progress {
  display: flex;
  gap: 8px;
  font-size: 12px;
  margin-top: 30px;
  color: #71839c;
}
.service-progress .done {
  color: #21865e;
}
.service-actions {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.service-actions p {
  font-size: 14px;
  color: #708098;
}
.service-modal-backdrop {
  position: fixed;
  inset: 0;
  background: #0b203766;
  z-index: 100;
  display: grid;
  place-items: center;
}
.service-modal {
  background: white;
  padding: 30px;
  border-radius: 16px;
  width: min(540px, 90vw);
  display: grid;
  gap: 22px;
}
.service-modal h2 {
  margin: 0;
}
.service-modal footer {
  display: flex;
  justify-content: flex-end;
  gap: 14px;
}
.service-modal small {
  color: #6f8095;
}
@media (max-width: 1100px) {
  .service-new {
    grid-template-columns: 1fr 1fr;
  }
  .service-conversation-layout {
    grid-template-columns: minmax(0, 1fr) 270px;
  }
  .service-toolbar {
    flex-wrap: wrap;
  }
  .service-table-card {
    overflow: auto;
  }
}
</style>
