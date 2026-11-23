<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { listEmails, sendEmail, type EmailInput, type EmailRecord } from '../api/email'
import { ApiError } from '../api/http'
import { useAuthStore } from '../stores/auth'
import { useUnsavedChanges } from '../composables/useUnsavedChanges'
import AppIcon from './AppIcon.vue'
const props=defineProps<{ticketId:number;status:string;draft:{id:number;subject:string;content:string}|null}>()
const auth=useAuthStore()
const recipient=ref('')
const subject=ref('工单处理回复')
const content=ref('')
const assistanceId=ref<number|null>(null)
const confirmed=ref(false)
const busy=ref(false)
const errorMessage=ref('')
const records=ref<EmailRecord[]>([])
const page=ref(1)
const pending=ref<EmailInput|null>(null)
const checking=ref(false)
const lockedResult=ref(false)
const historyOpen=ref(false)
const resultStatus=ref<EmailRecord['status']|null>(null)
const initialDraft=ref(JSON.stringify(['', '工单处理回复', '']))
const dirty=computed(()=>!lockedResult.value && JSON.stringify([recipient.value,subject.value,content.value])!==initialDraft.value)
useUnsavedChanges(()=>dirty.value || !!pending.value)
const recipientError=computed(()=>errorMessage.value.includes('recipient') || errorMessage.value.includes('收件') || errorMessage.value.includes('测试邮箱') ? errorMessage.value : '')
const labels={sending:'发送中',accepted:'SMTP 已接受，需核查收件箱',failed:'SMTP 明确拒绝',unknown:'结果不确定，请核查邮箱'}
watch(()=>props.draft,draft=>{
  if(!draft || pending.value || lockedResult.value) return
  if(dirty.value && !window.confirm('邮件中有尚未发送的编辑内容，是否替换为所选建议？')) return
  subject.value=draft.subject;content.value=draft.content;assistanceId.value=draft.id;confirmed.value=false
})
async function load(){
  try{records.value=await listEmails(auth.token,props.ticketId,page.value)}
  catch(error){if(!(error instanceof Error))throw error;errorMessage.value=error.message}
}
onMounted(load)
function newMessage(){
  lockedResult.value=false;confirmed.value=false;content.value='';assistanceId.value=null;errorMessage.value=''
  resultStatus.value=null
  initialDraft.value=JSON.stringify([recipient.value,subject.value,''])
}
async function submit(){
  busy.value=true;errorMessage.value=''
  // 请求失败时保留原 UUID 和正文，再次确认只查询原投递结果。
  if(!pending.value) pending.value={request_id:crypto.randomUUID(),recipient:recipient.value,subject:subject.value,
    content:content.value,confirmed:true,assistance_id:assistanceId.value}
  try{
    const result=await sendEmail(auth.token,props.ticketId,pending.value)
    resultStatus.value=result.status
    historyOpen.value=true
    checking.value=['sending','unknown'].includes(result.status)
    lockedResult.value=true
    if(!checking.value) pending.value=null
    confirmed.value=false;page.value=1
    await load()
  }catch(error){
    if(!(error instanceof Error))throw error
    errorMessage.value=error.message
    if(error instanceof ApiError && [401,403,409,422,503].includes(error.status)){pending.value=null;confirmed.value=false}
  }
  finally{busy.value=false}
}
</script>
<template>
  <section class="mail-workspace">
    <header class="module-heading"><div class="heading-with-icon"><span class="module-icon"><AppIcon name="pencil" /></span><div><span class="eyebrow">CUSTOMER REPLY</span><h2>客户邮件</h2></div></div><span class="subtle-tag">测试邮箱</span></header>
    <p class="module-description">编辑最终回复，核对后发送。请填写已配置的测试邮箱，不能直接发送给客户。</p>
    <form class="mail-editor" @submit.prevent="submit">
      <fieldset :disabled="busy || !!pending || lockedResult || status==='closed'">
        <div class="mail-field"><label for="mail-recipient">收件人</label><input id="mail-recipient" v-model="recipient" required type="email" :aria-invalid="!!recipientError" :aria-describedby="recipientError?'recipient-error':undefined" placeholder="填写已配置的测试邮箱" @input="confirmed=false;errorMessage=''" /></div>
        <p v-if="recipientError" id="recipient-error" class="field-error" role="alert">{{ recipientError }}</p>
        <div class="mail-field"><label for="mail-subject">主题</label><input id="mail-subject" v-model="subject" required maxlength="200" placeholder="一句话说明处理结果" @input="confirmed=false" /></div>
        <div class="mail-body"><div class="body-caption"><label for="mail-content">最终正文</label><span>{{ content.length }} / 10000</span></div><textarea id="mail-content" v-model="content" required maxlength="10000" rows="10" placeholder="在这里编写回复，也可以从 AI 建议带入草稿，再核对和修改。" @input="confirmed=false" /></div>
        <div class="mail-confirm"><label class="confirmation-line"><input v-model="confirmed" type="checkbox" /><span>我已核对收件人、主题及正文，确认向该测试邮箱发送</span></label></div>
      </fieldset>
      <div class="mail-sendbar"><span class="small-muted">{{ assistanceId ? `来源：AI 建议 #${assistanceId}` : '人工撰写 · 纯文本回复' }}</span><button class="button primary" :disabled="busy || status==='closed' || (lockedResult && !pending) || (!pending && !confirmed)">{{ busy?'正在发送…':pending?'使用原请求确认发送结果':'确认发送邮件' }}<AppIcon name="arrow-right" :size="17" /></button></div>
    </form>
    <p v-if="resultStatus" class="feedback" :class="resultStatus==='accepted'?'success':resultStatus==='failed'?'failure':'warning'" role="status">{{ labels[resultStatus] }}。{{ resultStatus==='accepted'?'请核查收件箱、垃圾箱及退信。':'请先核查发送记录和邮箱。' }}</p>
    <p v-if="pending" class="feedback warning">原请求已锁定；再次提交只核查这次结果，不会重新投递。结果不确定时请先核查邮箱。</p>
    <p v-if="errorMessage && !recipientError" class="feedback failure" role="alert">{{ errorMessage }}</p>
    <button v-if="lockedResult && !checking" class="button outline" :disabled="busy" @click="newMessage">开始撰写另一封邮件</button>
    <details :open="historyOpen" class="mail-history" @toggle="historyOpen=($event.target as HTMLDetailsElement).open">
      <summary><span>发送记录 <span class="small-muted">第 {{ page }} 页 · {{ records.length }} 条</span></span><AppIcon name="chevron-down" :size="16" /></summary>
      <div class="history-body"><button class="text-button" :disabled="busy" @click="load">刷新发送记录</button>
        <div v-if="!records.length" class="empty-state compact"><AppIcon name="clock" :size="24" /><p>暂无发送记录，确认发送后可在这里追溯。</p></div>
        <details v-for="record in records" :key="record.id" class="delivery-record">
          <summary><span><strong>{{ record.subject }}</strong><small>{{ record.recipient }} · {{ record.created_at }}</small></span><span class="state-pill" :class="record.status">{{ labels[record.status] }}</span></summary>
          <div class="delivery-body"><p class="multiline">{{ record.content }}</p><p v-if="record.error" class="feedback failure">{{ record.error }}</p><p class="small-muted">{{ record.message_id }} · 建议记录 {{ record.assistance_id ?? '手工撰写' }}</p></div>
        </details>
        <div class="history-pagination"><button class="button outline" :disabled="busy || page===1" @click="page--;load()">上一页</button><span class="small-muted">第 {{ page }} 页</span><button class="button outline" :disabled="busy || records.length<10" @click="page++;load()">下一页</button></div>
      </div>
    </details>
    <p class="privacy-note"><AppIcon name="info" :size="16" />SMTP 接受不代表最终送达；超时或断线不会自动重发。</p>
  </section>
</template>
