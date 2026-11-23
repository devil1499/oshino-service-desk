<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { getAnalysis, startAnalysis, adoptAnalysis } from '../api/basicAnalysis'
import { useAuthStore } from '../stores/auth'
const props = defineProps<{ticketId:number;status:string;categories:Record<number,string>}>()
const emit = defineEmits<{adopted:[]}>()
const auth = useAuthStore()
const data = ref<Awaited<ReturnType<typeof getAnalysis>> | null>(null)
const errorMessage = ref('')
const busy = ref(false)
const loading = ref(false)
const confirmed = ref(false)
let timer:ReturnType<typeof setTimeout> | undefined
let disposed = false
const labels = {not_started:'尚未分析',pending:'等待分析',running:'正在分析',completed:'分析完成',failed:'分析失败'}
const analyzing = computed(() => !!data.value && ['pending', 'running'].includes(data.value.status))
async function load() {
  if (loading.value || disposed) return
  clearTimeout(timer)
  loading.value = true
  try {
    const result = await getAnalysis(auth.token,props.ticketId)
    if(disposed) return
    errorMessage.value = ''
    data.value=result
    if(['pending','running'].includes(result.status)) timer=setTimeout(load,1500)
  } catch(error) { if(!(error instanceof Error)) throw error; errorMessage.value=error.message }
  finally { loading.value = false }
}
function refresh() { clearTimeout(timer); void load() }
onMounted(load)
onUnmounted(()=>{disposed=true;clearTimeout(timer)})
async function act(action:'retry'|'adopt') {
  busy.value=true; errorMessage.value=''
  try {
    if(action==='retry') { await startAnalysis(auth.token,props.ticketId); confirmed.value=false }
    else { await adoptAnalysis(auth.token,props.ticketId); confirmed.value=false; emit('adopted') }
    clearTimeout(timer)
    await load()
  } catch(error) { if(!(error instanceof Error)) throw error; errorMessage.value=error.message }
  finally {busy.value=false}
}
</script>
<template>
  <section class="analysis-card" :aria-busy="analyzing || loading">
    <header class="module-heading">
      <div class="heading-with-icon"><span class="module-icon"><AppIcon name="search" /></span><div><span class="eyebrow">AI ASSISTANT</span><h2>工单基础分析</h2></div></div>
      <span v-if="data" class="state-pill" :class="data.status" role="status"><i />{{ labels[data.status] }}</span>
    </header>
    <p class="module-description">整理问题要点，辅助判断分类与处理优先级。</p>
    <div v-if="analyzing || (!data && loading)" class="analysis-skeleton" role="status">
      <span /><span /><span /><p>正在分析工单，完成后显示建议……</p>
    </div>
    <div v-if="data?.stale" class="feedback warning" role="status">工单内容已变化，请重新分析后再采用。</div>
    <p v-if="data?.error || errorMessage" class="feedback failure" role="alert">{{ data?.error || errorMessage }}</p>
    <div v-if="data?.result" class="analysis-content">
      <h3 class="field-caption">问题摘要</h3><p class="analysis-summary">{{ data.result.summary }}</p>
      <div class="analysis-tags"><span class="suggestion-tag">{{ categories[data.result.category_id] }}</span><span class="suggestion-tag priority" :class="data.result.priority">建议优先级 {{ data.result.priority }}</span></div>
      <div class="analysis-reason"><AppIcon name="info" :size="17" /><p>{{ data.result.reason }}</p></div>
    </div>
    <div v-else-if="data?.status === 'not_started'" class="empty-state compact"><AppIcon name="search" :size="24" /><p>这条历史工单尚未分析，可以手动开始。</p></div>
    <footer class="analysis-footer">
      <div v-if="data?.result" class="analysis-adoption">
        <p v-if="data.adopted_at" class="small-muted">已人工确认采用</p>
        <label v-else class="confirmation-line"><input v-model="confirmed" type="checkbox" :disabled="busy || data.stale || status==='closed'" /><span>我已核对分类和优先级建议</span></label>
        <button v-if="!data.adopted_at" class="button primary" :disabled="busy || loading || !confirmed || data.stale || status==='closed'" @click="act('adopt')">确认采用分类和优先级</button>
      </div>
      <div class="secondary-actions">
        <button class="button outline" :disabled="busy || loading || status==='closed' || !data || analyzing" @click="act('retry')">{{ data?.status==='not_started' ? '开始分析' : '重新分析' }}</button>
        <button class="text-button" :disabled="busy || loading" @click="refresh">刷新状态</button>
        <span class="small-muted">建议需人工核实后采用</span>
      </div>
    </footer>
  </section>
</template>
