<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getCatalog } from '../api/config'
import { changeKnowledge, getKnowledge, saveKnowledge, uploadKnowledge, type DocumentInput, type KnowledgeDocument } from '../api/knowledge'
import AppIcon from '../components/AppIcon.vue'
import { useUnsavedChanges } from '../composables/useUnsavedChanges'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const document = ref<KnowledgeDocument | null>(null)
const catalog = ref<Awaited<ReturnType<typeof getCatalog>> | null>(null)
const form = reactive<DocumentInput>({ title: '', content: '', product_id: 0, module_id: 0, category_id: 0 })
const modules = computed(() => catalog.value?.modules.filter(item => item.product_id === form.product_id && item.is_active))
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const mode = ref<'upload' | 'manual'>('upload')
const dragging = ref(false)
const fileError = ref('')
const proofread = ref(false)
const savedSnapshot = ref(JSON.stringify(['', '', 0, 0, 0]))
const ready = ref(false)
const busy = ref(false)
const errorMessage = ref('')
const notice = ref('')
const statusLabels = { draft: '草稿', published: '已发布', disabled: '已停用' }
function inputSnapshot() {
  return JSON.stringify([form.title, form.content, form.product_id, form.module_id, form.category_id])
}
const hasUnsavedChanges = computed(() => ready.value && (inputSnapshot() !== savedSnapshot.value || file.value !== null))
const currentStep = computed(() => document.value?.status === 'published' ? 3 : document.value || mode.value === 'manual' ? 2 : 1)
useUnsavedChanges(() => hasUnsavedChanges.value || busy.value)
watch(inputSnapshot, () => { proofread.value = false })

function setDocument(value: KnowledgeDocument) {
  document.value = value
  Object.assign(form, { title: value.title, content: value.content, product_id: value.product_id,
    module_id: value.module_id, category_id: value.category_id })
  savedSnapshot.value = inputSnapshot()
  proofread.value = false
}
onMounted(async () => {
  try {
    if (route.params.id) setDocument(await getKnowledge(auth.token, Number(route.params.id)))
    if (auth.user?.role === 'admin') catalog.value = await getCatalog(auth.token)
    ready.value = true
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  }
})
function clearFile() {
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
}
function chooseFile(selected: File) {
  fileError.value = ''
  notice.value = ''
  const extension = selected.name.split('.').pop()?.toLowerCase()
  if (!extension || !['md', 'txt', 'pdf', 'jpg', 'jpeg', 'png'].includes(extension)) {
    clearFile()
    fileError.value = '请选择 MD、TXT、PDF、JPG 或 PNG 文件。'
    return
  }
  const limit = ['md', 'txt'].includes(extension) ? 256 * 1024 : 10 * 1024 * 1024
  if (selected.size > limit) {
    clearFile()
    fileError.value = '文本最多 256 KiB，PDF 和图片最多 10 MiB。'
    return
  }
  file.value = selected
  mode.value = 'upload'
}
function selectFile(event: Event) {
  const selected = (event.target as HTMLInputElement).files?.[0]
  if (selected) chooseFile(selected)
}
function dropFile(event: DragEvent) {
  dragging.value = false
  if (busy.value) return
  if (event.dataTransfer?.files.length !== 1) {
    fileError.value = '每次请选择一个资料文件。'
    return
  }
  chooseFile(event.dataTransfer.files[0]!)
}
function useManualInput() {
  clearFile()
  fileError.value = ''
  mode.value = 'manual'
}
function fileSize(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MiB` : `${Math.ceil(bytes / 1024)} KiB`
}
async function save() {
  busy.value = true
  errorMessage.value = ''
  notice.value = ''
  try {
    const created = document.value === null
    const saved = file.value && created && mode.value === 'upload'
      ? await uploadKnowledge(auth.token, form, file.value)
      : await saveKnowledge(auth.token, form, document.value?.id)
    setDocument(saved)
    clearFile()
    if (created) {
      busy.value = false
      await router.replace('/knowledge/' + saved.id)
    }
    notice.value = '草稿已保存，请校对正文后发布。'
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  } finally {
    busy.value = false
  }
}
async function changeStatus(action: 'publish' | 'disable') {
  if (!document.value) return
  busy.value = true
  notice.value = ''
  errorMessage.value = ''
  try {
    setDocument(await changeKnowledge(auth.token, document.value.id, action))
    notice.value = action === 'publish'
      ? '已发布并生成分块。建立知识索引后即可用于工单检索。'
      : '文档已停用，后续检索立即排除此文档。'
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="page-heading"><div><div class="eyebrow">知识库 / 文档资料</div><h1>{{ document?.title ?? '新增知识文档' }}</h1><p>先核对内容与归属，再发布为团队可用的知识。</p></div><RouterLink to="/knowledge" class="button outline">返回知识列表</RouterLink></div>
  <p v-if="errorMessage" role="alert" class="error error-panel">{{ errorMessage }}</p>
  <p v-if="notice" role="status" class="success knowledge-notice">{{ notice }}</p>
  <p v-if="!ready && !errorMessage" role="status" class="muted">正在读取文档……</p>
  <ol v-if="ready && auth.user?.role === 'admin'" class="knowledge-steps" aria-label="知识导入步骤">
    <li v-for="(label, index) in ['选择资料', '校对正文', '发布入库']" :key="label" :class="{ active: currentStep === index + 1, complete: currentStep > index + 1 }" :aria-current="currentStep === index + 1 ? 'step' : undefined"><span>{{ index + 1 }}</span>{{ label }}</li>
  </ol>
  <div v-if="ready" class="knowledge-editor-layout">
    <section class="content-card knowledge-document">
      <div v-if="document" class="knowledge-document-meta"><span class="knowledge-state" :class="document.status">{{ statusLabels[document.status] }}</span><span>第 {{ document.revision }} 版 · {{ document.chunk_count }} 个分块</span><span>来源：{{ document.source_name }}</span></div>
      <form v-if="auth.user?.role === 'admin' && catalog" @submit.prevent="save">
        <fieldset class="knowledge-form-fields" :disabled="busy">
        <label class="field" for="knowledge-title"><span>文档标题</span><input id="knowledge-title" v-model="form.title" required maxlength="200" placeholder="例如：账号登录与 E401 排查规范" /></label>
        <div class="knowledge-fields">
          <label class="field" for="knowledge-product"><span>所属产品</span><select id="knowledge-product" v-model.number="form.product_id" required @change="form.module_id = 0"><option disabled :value="0">请选择产品</option><option v-for="item in catalog.products.filter(x => x.is_active)" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label class="field" for="knowledge-module"><span>所属模块</span><select id="knowledge-module" v-model.number="form.module_id" required><option disabled :value="0">请选择模块</option><option v-for="item in modules" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label class="field" for="knowledge-category"><span>问题分类</span><select id="knowledge-category" v-model.number="form.category_id" required><option disabled :value="0">请选择分类</option><option v-for="item in catalog.categories.filter(x => x.is_active)" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
        </div>
        <div v-if="!document" class="knowledge-upload">
          <div class="knowledge-mode"><button type="button" :class="{ selected: mode === 'upload' }" @click="mode = 'upload'">上传文件</button><button type="button" :class="{ selected: mode === 'manual' }" @click="useManualInput">手工录入</button></div>
          <div v-if="mode === 'upload'" class="knowledge-drop-zone" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="dropFile">
            <AppIcon name="book" :size="28" /><strong>拖拽资料到这里</strong><span>支持 PDF、JPG、PNG、Markdown 和 TXT</span>
            <input ref="fileInput" class="knowledge-file-input" type="file" accept=".md,.txt,.pdf,.jpg,.jpeg,.png" aria-label="选择知识文件" @change="selectFile" />
            <small>PDF / 图片 ≤ 10 MiB；文本 ≤ 256 KiB</small>
          </div>
          <div v-if="file" class="knowledge-selected-file"><span>{{ file.name }} · {{ fileSize(file.size) }}</span><button type="button" class="text-button" @click="clearFile">移除文件</button></div>
          <p v-if="fileError" class="error" role="alert">{{ fileError }}</p>
          <p class="muted">文本 PDF 直接提取；扫描 PDF 和图片使用 OCR。识别后先存草稿，原文件只用于临时解析。</p>
        </div>
        <label v-if="document || mode === 'manual'" class="field" for="knowledge-content"><span>文档正文 · {{ form.content.length }} / 100000</span><textarea id="knowledge-content" v-model="form.content" required rows="18" maxlength="100000" placeholder="逐项核对产品名称、错误码、数字和操作步骤。" /></label>
        <p v-if="busy" class="muted" role="status">{{ file ? '正在提取资料文字，最多等待 180 秒……' : '正在保存……' }}</p>
        <div class="form-footer"><span class="muted">保存后先核对正文，再确认发布。新增或修改后需要重建知识索引。</span><button class="button primary" type="submit" :disabled="busy || !form.product_id || !form.module_id || !form.category_id || (!document && mode === 'upload' && !file)">{{ busy ? '正在处理……' : !document && mode === 'upload' ? '识别并创建草稿' : '保存草稿' }}</button></div>
        </fieldset>
      </form>
      <template v-else-if="document"><h2>{{ document.title }}</h2><div class="article-content multiline">{{ document.content }}</div></template>
    </section>
    <aside class="reference-rail knowledge-publish-guide">
      <AppIcon name="book" :size="24" /><h2>{{ auth.user?.role === 'admin' ? '发布与检索' : '阅读说明' }}</h2>
      <p>已发布文档供客服阅读。建立索引后，相关片段会出现在工单的知识检索结果中。</p>
      <template v-if="auth.user?.role === 'admin'">
        <ol><li>选择资料或手工录入并保存草稿。</li><li>对照原文校对正文和分类，保存修改。</li><li>确认发布并生成分块，再更新知识索引。</li></ol>
        <p v-if="hasUnsavedChanges" class="error">有尚未保存的修改，请先保存草稿再发布或停用。</p>
        <div v-if="document" class="knowledge-status-actions"><label class="knowledge-proofread"><input v-model="proofread" type="checkbox" :disabled="busy || hasUnsavedChanges || document.status === 'published'" />我已对照原资料核对正文，确认发布</label><button class="button primary" :disabled="busy || hasUnsavedChanges || !proofread || document.status === 'published'" @click="changeStatus('publish')">发布已保存正文</button><button class="button outline" :disabled="busy || hasUnsavedChanges || document.status === 'disabled'" @click="changeStatus('disable')">停用文档</button></div>
      </template>
      <p class="muted">当前按 500 字符分块、80 字符重叠。新增或修改内容后，需要重建知识索引。</p>
    </aside>
  </div>
</template>
