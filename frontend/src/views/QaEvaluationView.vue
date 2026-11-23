<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { z } from 'zod'
import { useAuthStore } from '../stores/auth'
import { getCatalog } from '../api/config'
import type { NamedItem } from '../api/models'
import {
  createEvaluation,
  evaluationCaseInput,
  getEvaluation,
  listEvaluations,
  listEvaluationReferences,
  runNextCase,
  saveReview,
} from '../api/qaEvaluation'
import type {
  EvaluationRun,
  EvaluationSummary,
  EvaluationReview,
} from '../api/qaEvaluation'
import { formatTime } from '../utils/format'
import QaRunDetails from '../components/QaRunDetails.vue'
import { formatTokenUsage } from '../utils/qaRunFormat'

const auth = useAuthStore()
const products = ref<NamedItem[]>([])
const runs = ref<EvaluationSummary[]>([])
const run = ref<EvaluationRun | null>(null)
const selectedIndex = ref(0)
const runTarget = ref<{ conversationId: number; messageId: number } | null>(
  null,
)
const listPage = ref(1)
const total = ref(0)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const running = ref(false)
const stopRequested = ref(false)
const createOpen = ref(false)
const title = ref('耳机知识问答评测')
const productId = ref<number>()
const mode = ref<'demo' | 'custom'>('demo')
const customJson = ref('')
const references = ref<Awaited<
  ReturnType<typeof listEvaluationReferences>
> | null>(null)
const referencePage = ref(1)
const selectedCase = computed(() => run.value?.cases[selectedIndex.value])
const selectedResult = computed(() =>
  run.value?.results.find((item) => item.case_index === selectedIndex.value),
)
const review = reactive<
  Omit<EvaluationReview, 'correctness'> & { correctness: number | null }
>({ correctness: null, covered_points: [], citation_support: null, note: '' })
const reviewStarted = ref(false)
const behaviorNames: Record<string, string> = {
  answered: '回答',
  clarification: '追问',
  insufficient: '依据不足',
  failed: '运行失败',
  blocked: '版本变化',
  running: '运行中',
}
const previous = computed(() =>
  run.value
    ? runs.value.find(
        (item) =>
          item.id < run.value!.id &&
          item.suite_signature === run.value!.suite_signature,
      )
    : undefined,
)
const metricCards = computed(() => {
  if (!run.value) return []
  const m = run.value.metrics
  return [
    {
      key: 'correctness',
      label: '正确性 · 人工',
      value: m.correctness,
      count: m.reviewed,
    },
    {
      key: 'completeness',
      label: '要点完整性 · 人工',
      value: m.completeness,
      count: m.reviewed,
    },
    {
      key: 'citation_support',
      label: '引用支持度 · 人工',
      value: m.citation_support,
      count: m.citation_samples,
    },
    {
      key: 'behavior_match',
      label: '预期行为匹配',
      value: m.behavior_match,
      count: m.behavior_samples,
    },
    {
      key: 'retrieval_recall',
      label: '参考块召回率',
      value: m.retrieval_recall,
      count: m.retrieval_samples,
    },
    {
      key: 'retrieval_hit',
      label: '参考块命中率',
      value: m.retrieval_hit,
      count: m.retrieval_samples,
    },
  ] as const
})
const canReview = computed(
  () =>
    selectedResult.value &&
    ['answered', 'clarification', 'insufficient'].includes(
      selectedResult.value.status,
    ),
)

function percent(value: number | null | undefined) {
  return value == null ? '未评测' : `${(value * 100).toFixed(1)}%`
}
async function refreshList() {
  const result = await listEvaluations(auth.token, listPage.value)
  runs.value = result.items
  total.value = result.total
}
async function load() {
  busy.value = true
  error.value = ''
  try {
    products.value = (await getCatalog(auth.token)).products.filter(
      (item) => item.is_active,
    )
    await refreshList()
  } catch (e) {
    if (!(e instanceof Error)) throw e
    error.value = e.message
  } finally {
    busy.value = false
  }
}
onMounted(load)
onBeforeUnmount(() => {
  stopRequested.value = true
})

async function selectRun(id: number) {
  busy.value = true
  error.value = ''
  try {
    run.value = await getEvaluation(auth.token, id)
    selectedIndex.value = 0
  } catch (e) {
    if (!(e instanceof Error)) throw e
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function create() {
  if (productId.value === undefined) return
  busy.value = true
  error.value = ''
  try {
    const cases =
      mode.value === 'custom'
        ? z
            .array(evaluationCaseInput)
            .min(1)
            .max(50)
            .parse(JSON.parse(customJson.value))
        : undefined
    run.value = await createEvaluation(auth.token, {
      product_id: productId.value,
      title: title.value,
      cases,
    })
    createOpen.value = false
    selectedIndex.value = 0
    listPage.value = 1
    await refreshList()
    notice.value = '题集与知识版本已冻结；点击运行后才会调用模型。'
  } catch (e) {
    if (!(e instanceof Error)) throw e
    error.value =
      e instanceof SyntaxError
        ? '题集不是合法 JSON 数组，请检查格式。'
        : e instanceof z.ZodError
          ? `题集格式错误：${e.issues.map((issue) => issue.path.join('.') + ' ' + issue.message).join('；')}`
          : e.message
  } finally {
    busy.value = false
  }
}
async function execute(all: boolean) {
  if (!run.value || running.value) return
  running.value = true
  stopRequested.value = false
  error.value = ''
  notice.value = ''
  const id = run.value.id
  try {
    do {
      run.value = await runNextCase(auth.token, id)
      selectedIndex.value = Math.max(0, run.value.processed - 1)
    } while (all && !stopRequested.value && run.value.state !== 'completed')
    await refreshList()
    notice.value =
      run.value.state === 'completed'
        ? '本批已执行完，请逐题人工评阅。'
        : '已暂停，可从下一题继续。'
  } catch (e) {
    if (!(e instanceof Error)) throw e
    error.value = `${e.message}。请刷新结果确认当前题状态，不要重复创建评测。`
  } finally {
    running.value = false
  }
}
async function refreshRun() {
  if (!run.value) return
  busy.value = true
  error.value = ''
  try {
    run.value = await getEvaluation(auth.token, run.value.id)
    await refreshList()
  } catch (e) {
    if (!(e instanceof Error)) throw e
    error.value = e.message
  } finally {
    busy.value = false
  }
}
watch([selectedIndex, () => run.value?.id], () => {
  reviewStarted.value = false
})
function startReview() {
  const saved = selectedResult.value?.review
  Object.assign(
    review,
    saved
      ? {
          correctness: saved.correctness,
          covered_points: [...saved.covered_points],
          citation_support: saved.citation_support,
          note: saved.note,
        }
      : {
          correctness: null,
          covered_points: [],
          citation_support: null,
          note: '',
        },
  )
  reviewStarted.value = true
}
async function submitReview() {
  if (!run.value || review.correctness === null) return
  busy.value = true
  error.value = ''
  try {
    run.value = await saveReview(
      auth.token,
      run.value.id,
      selectedIndex.value,
      { ...review, correctness: review.correctness },
    )
    reviewStarted.value = false
    await refreshList()
    notice.value = '人工评阅已保存。'
  } catch (e) {
    if (!(e instanceof Error)) throw e
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function pageRuns(delta: number) {
  busy.value = true
  error.value = ''
  try {
    listPage.value += delta
    await refreshList()
  } catch (e) {
    if (!(e instanceof Error)) throw e
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function loadReferences(delta = 0) {
  if (productId.value === undefined) return
  busy.value = true
  error.value = ''
  try {
    referencePage.value += delta
    references.value = await listEvaluationReferences(
      auth.token,
      productId.value,
      referencePage.value,
    )
  } catch (e) {
    if (!(e instanceof Error)) throw e
    error.value = e.message
  } finally {
    busy.value = false
  }
}
watch(productId, () => {
  references.value = null
  referencePage.value = 1
})
function exportReport() {
  if (!run.value) return
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(run.value, null, 2)], {
      type: 'application/json',
    }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = `qa-evaluation-${run.value.id}.json`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <header class="page-heading">
    <div>
      <h1>回答评测</h1>
      <p>固定题集运行，逐题核对依据；正确性、完整性和引用支持度由人工评阅。</p>
    </div>
    <button
      class="button primary"
      :disabled="running || busy"
      @click="createOpen = !createOpen"
    >
      新建评测
    </button>
  </header>
  <p v-if="error" role="alert" class="error error-panel">{{ error }}</p>
  <p v-if="notice" role="status" class="success-panel">{{ notice }}</p>
  <section v-if="createOpen" class="panel evaluation-create">
    <h2>准备固定题集</h2>
    <form @submit.prevent="create">
      <div class="create-fields">
        <label class="field"
          ><span>评测名称</span
          ><input v-model="title" required maxlength="100" /></label
        ><label class="field"
          ><span>产品范围</span
          ><select v-model="productId" required>
            <option :value="undefined" disabled>请选择产品</option>
            <option
              v-for="product in products"
              :key="product.id"
              :value="product.id"
            >
              {{ product.name }}
            </option>
          </select></label
        ><label class="field"
          ><span>题集来源</span
          ><select v-model="mode">
            <option value="demo">内置 30 题 · 耳机演示规则</option>
            <option value="custom">自定义 JSON · 1～50 题</option>
          </select></label
        >
      </div>
      <p v-if="mode === 'demo'" class="muted">
        只适用于仅发布标准耳机演示规则的产品，覆盖正常问答、多轮追问、信息不足、无答案和错误前提。创建时检查实际文档，不能用于推断真实产品性能。
      </p>
      <template v-else
        ><label class="field"
          ><span>题集 JSON 数组</span
          ><textarea
            v-model="customJson"
            required
            rows="8"
            placeholder='[{"id":"q1","category":"正常问题","question":"填写问题","history":[],"required_points":["填写必要要点"],"expected_behavior":"answered","expected_chunk_ids":[知识块编号],"forbidden":["禁止编造"]}]'
          />
        </label>
        <p class="muted">
          expected_behavior 填 answered、clarification 或
          insufficient；expected_chunk_ids 为下方真实知识块编号。多轮 history 按
          user、assistant 成对填写。请使用脱敏测试数据。
        </p>
        <button
          class="button outline"
          type="button"
          :disabled="busy || productId === undefined"
          @click="loadReferences()"
        >
          查看该产品知识块编号
        </button>
        <div v-if="references" class="reference-list">
          <details v-for="source in references.items" :key="source.chunk_id">
            <summary>{{ source.chunk_id }} · {{ source.title }}</summary>
            <p>{{ source.content }}</p>
          </details>
          <div>
            <button
              type="button"
              :disabled="busy || referencePage === 1"
              @click="loadReferences(-1)"
            >
              上一页
            </button>
            第 {{ referencePage }} 页
            <button
              type="button"
              :disabled="busy || !references.has_more"
              @click="loadReferences(1)"
            >
              下一页
            </button>
          </div>
        </div></template
      >
      <div class="actions">
        <button
          class="button outline"
          type="button"
          :disabled="busy"
          @click="createOpen = false"
        >
          取消</button
        ><button
          class="button primary"
          type="submit"
          :disabled="busy || !title.trim()"
        >
          创建题集快照
        </button>
      </div>
    </form>
  </section>

  <section class="panel evaluation-selector">
    <label
      ><span>历史评测</span
      ><select
        :value="run?.id ?? ''"
        :disabled="running || busy"
        @change="selectRun(Number(($event.target as HTMLSelectElement).value))"
      >
        <option value="" disabled>选择评测记录</option>
        <option v-for="item in runs" :key="item.id" :value="item.id">
          #{{ item.id }} {{ item.title }} · {{ item.processed }}/{{
            item.case_count
          }}
          · {{ formatTime(item.created_at) }}
        </option>
      </select></label
    >
    <div class="actions">
      <button
        class="button outline"
        :disabled="running || busy || listPage === 1"
        @click="pageRuns(-1)"
      >
        上一页</button
      ><span>{{ listPage }} / {{ Math.max(1, Math.ceil(total / 20)) }}</span
      ><button
        class="button outline"
        :disabled="running || busy || listPage * 20 >= total"
        @click="pageRuns(1)"
      >
        下一页
      </button>
    </div>
  </section>
  <div v-if="!run" class="panel evaluation-empty">
    先创建一份题集，或选择已有评测记录。未执行、未人工评阅的指标会显示“未评测”。
  </div>
  <template v-else>
    <section class="panel run-toolbar">
      <div>
        <h2>{{ run.title }}</h2>
        <p class="muted">
          已处理 {{ run.processed }} / {{ run.case_count }} 题 · 运行失败或受阻
          {{ run.metrics.failed }} 题 · 人工已评 {{ run.metrics.reviewed }} 题
        </p>
      </div>
      <div class="actions">
        <button
          class="button outline"
          :disabled="busy || running"
          @click="refreshRun"
        >
          刷新结果</button
        ><button class="button outline" :disabled="busy" @click="exportReport">
          导出报告</button
        ><button
          v-if="running"
          class="button outline"
          :disabled="stopRequested"
          @click="stopRequested = true"
        >
          {{ stopRequested ? '本题结束后暂停' : '暂停后续题目' }}</button
        ><template v-else
          ><button
            class="button outline"
            :disabled="busy || run.state !== 'ready'"
            @click="execute(false)"
          >
            运行下一题</button
          ><button
            class="button primary"
            :disabled="busy || run.state !== 'ready'"
            @click="execute(true)"
          >
            运行全部剩余题目
          </button></template
        >
      </div>
    </section>
    <p class="muted run-hint">
      运行会调用已配置的模型 API 并消耗
      Token；刷新或关闭页面不会撤销正在执行的单题。再次进入后先刷新结果。知识版本变化时需要新建评测。
    </p>
    <div class="metrics-grid">
      <article
        v-for="metric in metricCards"
        :key="metric.key"
        class="panel metric-card"
      >
        <span>{{ metric.label }}</span
        ><strong>{{ percent(metric.value) }}</strong
        ><small>样本 {{ metric.count }} 题</small
        ><small v-if="previous"
          >上次同题集：{{ percent(previous.metrics[metric.key]) }}</small
        >
      </article>
    </div>
    <p class="muted comparison-note">
      {{
        previous
          ? `对照当前列表内上一份相同题目、参考答案及知识版本的记录 #${previous.id}；人工评分覆盖数不同，请按样本数解读。`
          : '当前历史列表中暂无相同题集与知识版本的可比较记录。'
      }}
      预期行为匹配和检索指标不等于回答准确率。
    </p>
    <div class="evaluation-layout">
      <section class="panel case-list">
        <h2>测试题目</h2>
        <button
          v-for="(item, index) in run.cases"
          :key="item.id"
          :class="{ selected: selectedIndex === index }"
          @click="selectedIndex = index"
        >
          <span>{{ index + 1 }}. {{ item.question }}</span
          ><small
            >{{ item.category }} ·
            {{
              run.results[index]
                ? behaviorNames[run.results[index]!.status]
                : '待运行'
            }}{{ run.results[index]?.review ? ' · 已评阅' : '' }}</small
          >
        </button>
      </section>
      <section v-if="selectedCase" class="panel case-detail">
        <header>
          <span class="muted"
            >{{ selectedCase.id }} · 预期：{{
              behaviorNames[selectedCase.expected_behavior]
            }}</span
          >
          <h2>{{ selectedCase.question }}</h2>
        </header>
        <details v-if="selectedCase.history.length">
          <summary>固定的历史上下文</summary>
          <p v-for="(item, i) in selectedCase.history" :key="i">
            {{ item.role === 'user' ? '用户' : '助手' }}：{{ item.content }}
          </p>
        </details>
        <h3>参考答案必要要点</h3>
        <ul>
          <li v-for="point in selectedCase.required_points" :key="point">
            {{ point }}
          </li>
        </ul>
        <p class="forbidden">
          禁止：{{
            selectedCase.forbidden.join('；') || '按产品规则核实，不能编造'
          }}
        </p>
        <details
          v-for="source in selectedCase.references"
          :key="source.chunk_id"
        >
          <summary>
            参考依据 {{ source.source_id }} · {{ source.title }}
          </summary>
          <p>{{ source.content }}</p>
          <small class="muted">冻结版本 {{ source.fingerprint }}</small>
        </details>
        <h3>实际回答</h3>
        <button
          v-if="selectedResult?.conversation_id && selectedResult?.message_id"
          class="button outline"
          @click="
            runTarget = {
              conversationId: selectedResult.conversation_id,
              messageId: selectedResult.message_id,
            }
          "
        >
          运行详情</button
        ><template v-if="selectedResult"
          ><div
            class="answer"
            :class="{
              failure: ['failed', 'blocked'].includes(selectedResult.status),
            }"
          >
            {{ selectedResult.error ?? (selectedResult.answer || '正在执行…') }}
          </div>
          <p class="muted">
            {{ behaviorNames[selectedResult.status] }} · 耗时
            {{
              selectedResult.duration_ms === null
                ? '未知'
                : (selectedResult.duration_ms / 1000).toFixed(2) + ' 秒'
            }}
            · Token {{ formatTokenUsage(selectedResult.token_usage) }}
          </p>
          <details
            v-for="source in selectedResult.sources"
            :key="source.source_id"
          >
            <summary>
              回答引用 {{ source.source_id }} · {{ source.title }}
            </summary>
            <p>{{ source.content }}</p>
          </details>
          <p v-if="selectedResult.review" class="review-note">
            上次人工评阅：{{ selectedResult.review.note }}
          </p>
          <button
            v-if="canReview && !reviewStarted"
            class="button primary"
            :disabled="running || busy"
            @click="startReview"
          >
            {{ selectedResult.review ? '修改人工评阅' : '开始人工评阅' }}
          </button></template
        >
        <p v-else class="muted">本题尚未运行。</p>
        <form
          v-if="reviewStarted && canReview"
          class="review-form"
          @submit.prevent="submitReview"
        >
          <label class="field"
            ><span>正确性</span
            ><select v-model="review.correctness" required>
              <option :value="null" disabled>请选择判定结果</option>
              <option :value="2">正确：无错误或编造</option>
              <option :value="1">部分正确：存在局部问题</option>
              <option :value="0">错误：主要结论错误或编造</option>
            </select></label
          >
          <fieldset>
            <legend>勾选实际回答覆盖的必要要点</legend>
            <label
              v-for="(point, index) in selectedCase.required_points"
              :key="index"
              ><input
                v-model="review.covered_points"
                type="checkbox"
                :value="index"
              />{{ point }}</label
            >
          </fieldset>
          <label class="field"
            ><span>引用是否支持结论</span
            ><select
              v-model="review.citation_support"
              :disabled="!selectedResult?.sources.length"
            >
              <option :value="null">不适用／暂未评阅</option>
              <option :value="2">全部支持</option>
              <option :value="1">部分支持</option>
              <option :value="0">不支持</option>
            </select></label
          ><label class="field"
            ><span>评阅依据与问题说明</span
            ><textarea
              v-model="review.note"
              required
              maxlength="2000"
              rows="3"
              placeholder="说明判分依据、遗漏要点或不支持结论的引用。"
            />
          </label>
          <div class="actions">
            <button
              class="button outline"
              type="button"
              :disabled="busy"
              @click="reviewStarted = false"
            >
              取消</button
            ><button
              class="button primary"
              type="submit"
              :disabled="
                busy || review.correctness === null || !review.note.trim()
              "
            >
              保存人工评阅
            </button>
          </div>
        </form>
      </section>
    </div>
  </template>
  <QaRunDetails :target="runTarget" @close="runTarget = null" />
</template>

<style scoped>
.evaluation-create,
.evaluation-selector,
.evaluation-empty,
.run-toolbar,
.case-list,
.case-detail {
  padding: 24px;
  margin-bottom: 20px;
}
.create-fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
}
.evaluation-selector,
.run-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
}
.evaluation-selector label {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 0;
}
.evaluation-selector select {
  max-width: 650px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  font: inherit;
}
.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.actions .button + .button {
  margin-left: 0;
}
.run-toolbar h2,
.run-toolbar p {
  margin: 0 0 8px;
}
.run-hint,
.comparison-note {
  font-size: 14px;
  line-height: 1.7;
}
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.metric-card {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.metric-card strong {
  font-size: 28px;
  color: #245ee0;
}
.metric-card small {
  color: var(--muted);
}
.evaluation-layout {
  display: grid;
  grid-template-columns: minmax(260px, 0.8fr) minmax(0, 2fr);
  gap: 20px;
  align-items: start;
}
.case-list {
  max-height: 850px;
  overflow: auto;
}
.case-list h2,
.case-detail h2 {
  font-size: 22px;
  margin: 0 0 20px;
}
.case-list button {
  width: 100%;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--line);
  padding: 16px 12px;
  text-align: left;
  color: inherit;
  font: inherit;
  cursor: pointer;
  line-height: 1.6;
}
.case-list button.selected {
  color: #245ee0;
  background: #edf3ff;
  border-radius: 8px;
}
.case-list small {
  display: block;
  color: var(--muted);
  margin-top: 8px;
}
.case-detail h3 {
  font-size: 18px;
  margin: 24px 0 12px;
}
.case-detail li {
  line-height: 1.8;
}
.case-detail details,
.reference-list details {
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
}
.case-detail details p,
.reference-list p {
  white-space: pre-wrap;
  line-height: 1.8;
}
.case-detail small {
  overflow-wrap: anywhere;
}
.answer {
  white-space: pre-wrap;
  line-height: 1.9;
  background: #f3f7fd;
  padding: 18px;
  border-radius: 10px;
}
.answer.failure {
  background: #fff2f1;
  color: #b63730;
}
.forbidden {
  color: #936024;
  font-size: 14px;
}
.review-form {
  margin-top: 24px;
  border-top: 1px solid var(--line);
  padding-top: 24px;
}
.review-form fieldset {
  margin: 0 0 20px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.review-form fieldset label {
  display: flex;
  align-items: baseline;
  gap: 10px;
  line-height: 1.7;
}
.review-form input[type='checkbox'] {
  width: 18px;
  height: 18px;
}
.review-note {
  border-left: 3px solid #3e91ba;
  padding: 10px 16px;
  background: #f2f8fa;
}
.reference-list {
  max-height: 320px;
  overflow: auto;
  margin: 16px 0;
}
@media (max-width: 1100px) {
  .evaluation-layout {
    grid-template-columns: 1fr;
  }
  .case-list {
    max-height: 320px;
  }
  .create-fields {
    grid-template-columns: 1fr;
  }
  .evaluation-selector select {
    max-width: 100%;
  }
}
</style>
