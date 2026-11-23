<script setup lang="ts">
import { ElButton, ElCheckbox } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/checkbox/style/css'
import { onMounted, onUnmounted, ref } from 'vue'
import { adoptAssistance, generateAssistance, listAssistance, type Assistance } from '../api/assistance'
import { useAuthStore } from '../stores/auth'

const props = defineProps<{ ticketId: number; status: string; categories: Record<number, string> }>()
const emit = defineEmits<{ adopted: []; email: [draft: { id: number; subject: string; content: string }]; preview: [source: { kind: 'ticket' | 'knowledge'; id: number }] }>()
const auth = useAuthStore()
const current = ref<Assistance | null>(null)
const history = ref<Assistance[]>([])
const page = ref(1)
const solution = ref('')
const reply = ref('')
const confirmed = ref(false)
const busy = ref(false)
const generating = ref(false)
const elapsed = ref(0)
let timer: ReturnType<typeof setInterval> | undefined
onUnmounted(() => clearInterval(timer))
const errorMessage = ref('')
function select(run: Assistance) {
  current.value = run
  solution.value = run.final_solution ?? run.draft.steps.map((step, i) => `${i + 1}. ${step.instruction} [${step.source_ids.join(', ')}]`).join('\n')
  reply.value = run.final_reply ?? `主题：${run.draft.reply_subject}\n\n${run.draft.reply_body}`
  confirmed.value = false
}
async function load() {
  history.value = await listAssistance(auth.token, props.ticketId, page.value)
}
onMounted(async () => {
  try {
    await load()
    if (history.value[0]) select(history.value[0])
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  }
})
async function perform(action: 'generate' | 'adopt' | 'history') {
  if (busy.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    if (action === 'generate') {
      generating.value = true
      elapsed.value = 0
      const started = Date.now()
      timer = setInterval(() => { elapsed.value = Math.floor((Date.now() - started) / 1000) }, 1000)
      select(await generateAssistance(auth.token, props.ticketId))
      page.value = 1
      await load()
    } else if (action === 'adopt' && current.value) {
      select(await adoptAssistance(auth.token, props.ticketId, current.value.id, solution.value, reply.value))
      emit('adopted')
      await load()
    } else { await load() }
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  } finally { clearInterval(timer); generating.value = false; busy.value = false }
}
</script>

<template>
  <section class="panel assistance-panel">
    <div class="eyebrow">智能辅助 / 人工确认</div>
    <h2>AI 处理建议</h2>
    <p>基于真实检索依据生成，需人工核实；采用后保存处理记录和回复草稿。</p>
    <el-button type="primary" :disabled="busy || !['pending', 'processing'].includes(status)" @click="perform('generate')">生成处理建议</el-button>
    <p v-if="generating" role="status">正在生成，已等待 {{ elapsed }} 秒。{{ current ? '下方仍是上一次结果；完成后替换。' : '完成后显示新结果。' }}</p>
    <p v-else-if="busy" role="status">正在保存或读取记录……</p>
    <p v-if="errorMessage" role="alert" class="error">{{ errorMessage }}</p>
    <template v-if="current">
      <p class="muted">#{{ current.id }} · {{ current.model }} · {{ current.prompt_version }} · {{ current.duration_ms }} ms · {{ current.created_at }}</p>
      <h3>问题摘要与判断</h3>
      <p>{{ current.draft.summary }}</p><p>{{ current.draft.diagnosis }}</p>
      <p>建议分类：{{ categories[current.draft.category_id] }} · 建议优先级：{{ current.draft.priority }}</p>
      <p>{{ current.draft.reason }}</p>
      <ol><li v-for="(step, i) in current.draft.steps" :key="i">{{ step.instruction }} [{{ step.source_ids.join(', ') }}]</li></ol>
      <h3>风险</h3><p v-if="!current.draft.risks.length">模型未列出风险，请自行核实。</p>
      <ul><li v-for="item in current.draft.risks" :key="item">{{ item }}</li></ul>
      <h3>需要确认</h3><ul><li v-for="item in current.draft.confirmations" :key="item">{{ item }}</li></ul>
      <h3>参考来源快照</h3>
      <article v-for="source in current.sources" :key="source.source_id" class="assistance-source">
        <button class="text-button" type="button" @click="emit('preview', { kind: source.kind, id: source.entity_id })">[{{ source.source_id }}] {{ source.title }}</button>
        <p class="multiline">{{ source.content }}</p>
      </article>
      <h3>人工编辑并确认</h3>
      <p>以下编辑保存为采用记录；分类、优先级和已解决状态通过工单原有按钮确认。</p>
      <label class="field">处理方案<textarea v-model="solution" rows="6" maxlength="10000" style="width:100%" :disabled="busy || !!current.adopted_at" /></label>
      <label class="field">回复草稿<textarea v-model="reply" rows="6" maxlength="6000" style="width:100%" :disabled="busy || !!current.adopted_at" /></label>
      <p v-if="current.adopted_at">已于 {{ current.adopted_at }} 人工确认采用；回复可带入客户邮件，核对后再发送。</p>
      <template v-else>
        <p><el-checkbox v-model="confirmed" :disabled="busy">我已核对工单、引用依据和待确认信息，确认保存采用记录</el-checkbox></p>
        <el-button type="primary" :disabled="busy || !confirmed || !solution.trim() || !reply.trim() || !['pending', 'processing'].includes(status)" @click="perform('adopt')">确认采用并保存记录</el-button>
      </template>
      <p><el-button :disabled="busy || status === 'closed'" @click="emit('email', { id: current.id, subject: current.draft.reply_subject, content: current.final_reply ?? current.draft.reply_body })">带入客户邮件</el-button></p>
    </template>
    <h3>生成历史（每页10条）</h3>
    <p v-if="!history.length && !busy" class="muted">还没有生成记录。</p>
    <ul><li v-for="run in history" :key="run.id"><button class="text-button" type="button" :disabled="busy" @click="select(run)">#{{ run.id }} · {{ run.created_at }} · {{ run.adopted_at ? '已采用' : '未采用' }}</button></li></ul>
    <el-button :disabled="busy || page === 1" @click="page--; perform('history')">上一页</el-button>
    <el-button :disabled="busy || history.length < 10" @click="page++; perform('history')">下一页</el-button>
  </section>
</template>
