<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { importTickets } from '../api/imports'
import { listTickets } from '../api/tickets'
import type { NamedItem, Ticket } from '../api/models'
import AppIcon from '../components/AppIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useAuthStore } from '../stores/auth'
import { formatTime } from '../utils/format'

const props = defineProps<{ products: NamedItem[] }>()
const auth = useAuthStore()
const productNames = computed(() => new Map(props.products.map(item => [item.id, item.name])))
const rows = ref<Ticket[]>([])
const page = ref(1)
const total = ref(0)
const pageSize = ref(20)
const historyLoading = ref(false)
const historyError = ref('')
const uploadOpen = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const busy = ref(false)
const selectedFileName = ref('')
const result = ref<Awaited<ReturnType<typeof importTickets>> | null>(null)
const errorMessage = ref('')
let requestNumber = 0

async function loadHistory() {
  const currentRequest = ++requestNumber
  historyLoading.value = true
  historyError.value = ''
  try {
    const history = await listTickets(auth.token, { page: page.value, imported_only: true })
    if (currentRequest !== requestNumber) return
    rows.value = history.items
    total.value = history.total
    pageSize.value = history.page_size
  } catch (error) {
    if (!(error instanceof Error)) throw error
    if (currentRequest === requestNumber) historyError.value = error.message
  } finally {
    if (currentRequest === requestNumber) historyLoading.value = false
  }
}

function changePage(change: number) {
  page.value += change
  void loadHistory()
}

function openUpload() {
  selectedFileName.value = ''
  result.value = null
  errorMessage.value = ''
  uploadOpen.value = true
}
defineExpose({ openUpload })
onMounted(loadHistory)

function fileChanged() {
  selectedFileName.value = fileInput.value?.files?.[0]?.name ?? ''
  result.value = null
  errorMessage.value = ''
}

async function submit() {
  if (busy.value) return
  result.value = null
  errorMessage.value = ''
  const file = fileInput.value?.files?.[0]
  if (!file) {
    errorMessage.value = '请先选择 CSV 文件'
    return
  }
  if (file.size > 4 * 1024 * 1024) {
    errorMessage.value = 'CSV 不能超过 4 MiB'
    return
  }
  busy.value = true
  try {
    result.value = await importTickets(auth.token, file)
    page.value = 1
    await loadHistory()
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.name === 'TimeoutError'
      ? '上传等待超时，结果尚未确认。请先查询历史导入列表；再次上传时保留原来源编号。'
      : error.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="history-content">
    <div class="history-heading"><div><h2>已导入的历史工单</h2><p class="muted">查看 CSV 导入的工单，点击右上角“上传 CSV”添加资料。</p></div><button type="button" class="button primary" @click="openUpload"><AppIcon name="upload" :size="17" />上传 CSV</button></div>
    <div v-if="historyError" class="error error-panel" role="alert">{{ historyError }} <button type="button" class="text-button" @click="loadHistory">重新读取</button></div>
    <div v-else v-loading="historyLoading" :aria-busy="historyLoading">
      <el-table :data="rows" empty-text="还没有导入历史工单，请点击右上角“上传 CSV”。">
        <el-table-column prop="number" label="工单编号" min-width="130" />
        <el-table-column prop="title" label="问题标题" min-width="220" />
        <el-table-column label="产品" min-width="180"><template #default="{ row }">{{ productNames.get(row.product_id) }}</template></el-table-column>
        <el-table-column label="工单状态" min-width="120"><template #default="{ row }"><StatusBadge :status="row.status" /></template></el-table-column>
        <el-table-column label="导入时间" min-width="160"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column>
        <el-table-column label="操作" width="100"><template #default="{ row }"><RouterLink :to="'/tickets/' + row.id" class="text-button">查看</RouterLink></template></el-table-column>
      </el-table>
      <div class="pagination"><span>共 {{ total }} 条 · 第 {{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }} 页</span><div><button type="button" class="pagination-button" :disabled="historyLoading || page === 1" @click="changePage(-1)">上一页</button><button type="button" class="pagination-button" :disabled="historyLoading || page * pageSize >= total" @click="changePage(1)">下一页</button></div></div>
    </div>
    <p class="history-footnote muted">导入时间为 CSV 保存到系统的时间，不代表原问题发生或解决的时间。</p>

    <el-dialog v-model="uploadOpen" title="上传 CSV 历史工单" class="admin-import-dialog" width="min(940px, 94vw)" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" destroy-on-close>
      <div class="import-layout history-import-layout">
        <section aria-labelledby="import-title">
          <div class="section-heading"><span class="section-number">01</span><div><h2 id="import-title">选择 CSV 文件</h2><p>UTF-8 编码 · 最多 4 MiB · 最多 5000 条记录</p></div></div>
          <div class="import-downloads"><a class="button outline" href="/import-template.csv" download>下载空白模板</a><a class="text-button" href="/demo-tickets.csv" download>下载 40 条模拟案例</a></div>
          <form id="history-upload-form" @submit.prevent="submit">
            <div class="import-file-box"><AppIcon name="upload" :size="32" /><label for="import-file">选择要导入的历史工单文件</label><input id="import-file" ref="fileInput" type="file" accept=".csv,text/csv" :disabled="busy" @change="fileChanged" /><p v-if="selectedFileName" class="muted">已选择：{{ selectedFileName }}</p><small>Excel 工作簿（.xlsx）需另存为 CSV UTF-8。</small></div>
            <p class="muted">全部校验通过后，才会一起保存。</p>
          </form>
          <p v-if="errorMessage" class="error error-panel" role="alert">{{ errorMessage }}</p>
          <div v-if="result" class="import-result" role="status"><AppIcon name="check" :size="24" /><div><h2>成功导入 {{ result.imported }} 条工单</h2><p>工单及处理记录已保存，可关闭弹窗查看历史导入列表。</p></div></div>
          <p class="muted">网络超时不代表导入失败。请先关闭弹窗查看列表，再使用原来源编号重试，避免重复数据。</p>
        </section>
        <aside class="import-rules history-import-rules" aria-label="导入规则">
          <h2>导入前，核对这几项</h2>
          <ol><li><strong>先准备基础配置</strong><p>产品、模块、分类必须已存在且启用，名称与 CSV 完全一致。</p></li><li><strong>每条记录有唯一来源编号</strong><p>import_key 全库唯一，重复编号会被拒绝。</p></li><li><strong>状态和解决方案对应</strong><p>pending：待处理，方案留空。<br />resolved：已解决，方案必填。</p></li><li><strong>错误时整批不写入</strong><p>按提示修改第 N 条数据记录；描述内的换行不单独算一条记录。</p></li></ol>
          <details><summary>40 条样例需要哪些配置？</summary><p>产品：演示协作平台</p><p>模块：账号模块、账单模块、报表模块、集成模块</p><p>分类：账号权限、计费订阅、功能使用、配置集成、性能故障、服务不可用、数据问题</p></details>
        </aside>
      </div>
      <template #footer><button type="button" class="button outline" :disabled="busy" @click="uploadOpen = false">{{ result ? '完成' : '取消' }}</button><button v-if="!result" type="submit" form="history-upload-form" class="button primary" :disabled="busy || !selectedFileName">{{ busy ? '正在导入…' : '确认导入' }}</button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.history-content { padding-top: 25px; }
.history-heading { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 22px; }
.history-heading h2 { margin-bottom: 6px; }
.history-heading p, .history-footnote { font-size: 14px; margin-bottom: 0; }
.history-footnote { margin-top: 20px; }
.history-import-layout { grid-template-columns: minmax(0, 1.4fr) minmax(240px, 1fr); gap: 25px; }
.history-import-rules { padding-left: 23px; border-left: 1px solid var(--line); }
.history-import-layout .section-heading { margin-bottom: 22px; }
.history-import-layout p { line-height: 1.8; }
.history-import-layout .import-result { margin-bottom: 16px; }
.history-import-layout .import-result h2 { font-size: 17px; }
@media (max-width: 760px) { .history-import-layout { grid-template-columns: minmax(0, 1fr); }.history-import-rules { padding: 20px 0 0; border-left: 0; border-top: 1px solid var(--line); }.history-heading { align-items: flex-start; flex-direction: column; gap: 8px; } }
</style>

<style>
.admin-import-dialog.el-dialog { display: flex; flex-direction: column; max-height: 90dvh; margin: 5dvh auto; }
.admin-import-dialog .el-dialog__body { min-height: 0; overflow-y: auto; }
.admin-import-dialog .el-dialog__header, .admin-import-dialog .el-dialog__footer { flex-shrink: 0; }
</style>
