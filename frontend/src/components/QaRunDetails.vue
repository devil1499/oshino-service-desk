<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { getRun, type QaRun } from "../api/qa";
import { useAuthStore } from "../stores/auth";
import { formatRunDuration, formatTokenUsage } from "../utils/qaRunFormat";

const props = defineProps<{
  target: { conversationId: number; messageId: number } | null;
}>();
const emit = defineEmits<{ close: [] }>();
const auth = useAuthStore();
const run = ref<QaRun | null>(null);
const loading = ref(false);
const error = ref("");
const activeTab = ref("steps");
const tabs = [
  { id: "steps", label: "步骤耗时" },
  { id: "usage", label: "模型用量" },
  { id: "context", label: "历史上下文" },
  { id: "sources", label: "检索资料" },
];
const stepNames: Record<string, string> = {
  plan: "理解问题",
  retrieve: "检索知识",
  web_search: "联网搜索",
  assess: "判断依据与回答",
  generate: "生成回答",
  verify_sources: "校验引用",
};
const statusNames: Record<string, string> = {
  running: "进行中",
  success: "成功",
  succeeded: "成功",
  completed: "已完成",
  answered: "已回答",
  clarification: "需要追问",
  insufficient: "知识不足",
  failed: "失败",
  cancelled: "已中断",
  interrupted: "已中断",
};
const retrievals = computed(
  () => run.value?.steps.filter((step) => step.name === "retrieve") ?? [],
);
const citedIds = computed(
  () => new Set(run.value?.sources.map((source) => source.source_id)),
);
let requestNumber = 0;

function statusLabel(status: string) {
  return statusNames[status] ?? status;
}
function snapshot(value: unknown) {
  return JSON.stringify(value, null, 2);
}
function tokenCount(value: number | null) {
  return value === null ? "未知" : value.toLocaleString();
}
function changeVisibility(open: boolean) {
  if (!open) emit("close");
}

async function load() {
  const target = props.target;
  const currentRequest = ++requestNumber;
  run.value = null;
  error.value = "";
  loading.value = target !== null;
  if (!target) return;
  try {
    const result = await getRun(
      auth.token,
      target.conversationId,
      target.messageId,
    );
    if (currentRequest === requestNumber) run.value = result;
  } catch (cause) {
    if (!(cause instanceof Error)) throw cause;
    if (currentRequest === requestNumber) error.value = cause.message;
  } finally {
    if (currentRequest === requestNumber) loading.value = false;
  }
}
watch(
  () => props.target,
  () => {
    activeTab.value = "steps";
    void load();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  requestNumber++;
});
</script>

<template>
  <el-drawer
    :model-value="target !== null"
    title="运行详情"
    size="min(760px, 94vw)"
    class="qa-run-drawer"
    @update:model-value="changeVisibility"
  >
    <div v-loading="loading" class="run-content" :aria-busy="loading">
      <p v-if="loading" class="muted" role="status">正在读取本轮运行记录……</p>
      <div v-if="error" class="error error-panel" role="alert">
        读取失败：{{ error }}
        <button class="text-button" type="button" @click="load">
          重新读取
        </button>
      </div>
      <template v-if="run">
        <div class="run-heading">
          <span
            >会话 #{{ target?.conversationId }} · 回答 #{{
              target?.messageId
            }}</span
          ><span
            class="run-status"
            :class="{ failed: run.status === 'failed' }"
            >{{ statusLabel(run.status) }}</span
          >
        </div>
        <button
          type="button"
          class="text-button run-refresh"
          :disabled="loading"
          @click="load"
        >
          刷新记录
        </button>
        <p class="run-question">{{ run.question.text }}</p>
        <div class="run-summary">
          <div>
            <span>联网搜索尝试</span
            ><strong
              >{{
                run.steps.filter((step) => step.name === "web_search").length
              }}
              次</strong
            ><small>与模型 Token 分开记录</small>
          </div>
          <div>
            <span>本轮总耗时</span
            ><strong>{{ formatRunDuration(run.duration_ms) }}</strong>
          </div>
          <div>
            <span>聊天模型 Token</span
            ><strong>{{ formatTokenUsage(run.usage.chat) }}</strong>
          </div>
        </div>
        <dl class="run-meta">
          <div>
            <dt>模型</dt>
            <dd>{{ run.model }}</dd>
          </div>
          <div>
            <dt>提示词版本</dt>
            <dd>{{ run.prompt_version }}</dd>
          </div>
          <div>
            <dt>开始时间</dt>
            <dd>{{ new Date(run.started_at).toLocaleString() }}</dd>
          </div>
        </dl>
        <p v-if="run.error" class="error error-panel" role="alert">
          失败原因：{{ run.error }}
        </p>
        <p
          v-if="run.status === 'clarification' || run.status === 'insufficient'"
          class="run-note"
        >
          本轮正常结束。追问和知识不足不等于接口运行失败，回答是否合理需要结合资料评测。
        </p>
        <div class="run-tabs" role="tablist" aria-label="运行详情分区">
          <button
            v-for="tab in tabs"
            :id="`run-tab-${tab.id}`"
            :key="tab.id"
            type="button"
            role="tab"
            :aria-selected="activeTab === tab.id"
            :aria-controls="`run-panel-${tab.id}`"
            :class="{ active: activeTab === tab.id }"
            @click="activeTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </div>

        <section
          v-if="activeTab === 'steps'"
          id="run-panel-steps"
          role="tabpanel"
          aria-labelledby="run-tab-steps"
        >
          <p class="run-note">
            按执行顺序展示；补充检索会再次出现“检索知识”和“判断依据”。步骤内部包含模型调用耗时，请勿重复相加。
          </p>
          <ol class="run-steps">
            <li
              v-for="(step, index) in run.steps"
              :key="index"
              :class="{ failed: step.status === 'failed' }"
            >
              <div class="step-heading">
                <span class="step-number">{{ index + 1 }}</span
                ><strong>{{ stepNames[step.name] ?? step.name }}</strong
                ><span>{{ statusLabel(step.status) }}</span
                ><time>{{ formatRunDuration(step.duration_ms) }}</time>
              </div>
              <p v-if="step.error" class="error">{{ step.error }}</p>
              <details>
                <summary>查看这一步的输入与输出</summary>
                <h4>输入快照</h4>
                <pre>{{ snapshot(step.input) }}</pre>
                <h4>输出快照</h4>
                <pre v-if="step.output !== null">{{
                  snapshot(step.output)
                }}</pre>
                <p v-else class="muted">未产生已记录的输出。</p>
              </details>
            </li>
          </ol>
          <p v-if="!run.steps.length" class="run-note">尚未记录执行步骤。</p>
        </section>

        <section
          v-else-if="activeTab === 'usage'"
          id="run-panel-usage"
          role="tabpanel"
          aria-labelledby="run-tab-usage"
        >
          <div class="usage-totals">
            <article v-for="kind in ['chat', 'embedding'] as const" :key="kind">
              <h3>{{ kind === "chat" ? "聊天模型" : "Embedding" }}</h3>
              <strong>{{ formatTokenUsage(run.usage[kind]) }}</strong>
              <p>
                输入 {{ tokenCount(run.usage[kind].input_tokens) }} · 输出
                {{ tokenCount(run.usage[kind].output_tokens) }}
              </p>
              <small
                >共 {{ run.usage[kind].calls }} 次调用，{{
                  run.usage[kind].known_calls
                }}
                次用量完整</small
              >
            </article>
          </div>
          <p class="run-note">
            仅统计接口实际返回的用量。未知不按 0 计算；聊天与 Embedding
            分开统计。
          </p>
          <div class="usage-table-wrap">
            <table class="usage-table">
              <thead>
                <tr>
                  <th>调用</th>
                  <th>耗时</th>
                  <th>输入</th>
                  <th>输出</th>
                  <th>总量</th>
                  <th>结果</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(call, index) in run.calls" :key="index">
                  <td>
                    {{ index + 1 }} · {{ call.kind === "chat" ? "聊天" : "向量"
                    }}<small>{{ call.model }}</small>
                  </td>
                  <td>{{ formatRunDuration(call.duration_ms) }}</td>
                  <td>{{ tokenCount(call.usage?.input_tokens ?? null) }}</td>
                  <td>{{ tokenCount(call.usage?.output_tokens ?? null) }}</td>
                  <td>{{ tokenCount(call.usage?.total_tokens ?? null) }}</td>
                  <td>{{ statusLabel(call.status) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!run.calls.length" class="run-note">
            本轮尚未发起模型调用。
          </p>
          <p
            v-for="(call, index) in run.calls.filter((item) => item.error)"
            :key="index"
            class="error"
          >
            {{ call.model }}：{{ call.error }}
          </p>
        </section>

        <section
          v-else-if="activeTab === 'context'"
          id="run-panel-context"
          role="tabpanel"
          aria-labelledby="run-tab-context"
        >
          <h3>
            实际带入的历史消息
            <span class="muted">{{ run.question.history.length }} 条</span>
          </h3>
          <p v-if="!run.question.history.length" class="run-note">
            本轮未带入历史消息。
          </p>
          <article
            v-for="(message, index) in run.question.history"
            :key="index"
            class="context-message"
          >
            <strong>{{ message.role === "user" ? "用户" : "智能助手" }}</strong>
            <p>{{ message.content }}</p>
          </article>
          <h3>本轮问题</h3>
          <p class="context-question">{{ run.question.text }}</p>
          <h3>每次调用的实际输入与输出</h3>
          <p class="run-note">
            快照已按规则脱敏。这里只展示调用资料，不代表模型的内部思考过程。
          </p>
          <details
            v-for="(call, index) in run.calls"
            :key="index"
            class="call-snapshot"
          >
            <summary>
              第 {{ index + 1 }} 次 ·
              {{ call.kind === "chat" ? "聊天模型" : "Embedding" }} ·
              {{ call.model }}
            </summary>
            <h4>请求内容</h4>
            <pre v-if="call.request !== null">{{ snapshot(call.request) }}</pre>
            <p v-else class="muted">未记录请求内容。</p>
            <h4>输出内容</h4>
            <pre v-if="call.response !== null">{{
              snapshot(call.response)
            }}</pre>
            <p v-else class="muted">未记录有效输出。</p>
            <p v-if="call.error" class="error">{{ call.error }}</p>
          </details>
        </section>

        <section
          v-else
          id="run-panel-sources"
          role="tabpanel"
          aria-labelledby="run-tab-sources"
        >
          <h3>
            最终引用 <span class="muted">{{ run.sources.length }} 条</span>
          </h3>
          <p v-if="!run.sources.length" class="run-note">本轮没有最终引用。</p>
          <details
            v-for="source in run.sources"
            :key="source.source_id"
            class="source-snapshot"
          >
            <summary>{{ source.source_id }} · {{ source.title }}</summary>
            <p>{{ source.content }}</p>
            <small v-if="'url' in source"
              >互联网来源 · 检索时间 {{ source.retrieved_at }}</small
            >
            <a
              v-if="'url' in source"
              :href="source.url"
              target="_blank"
              rel="noopener noreferrer"
              >查看网页 ↗</a
            >
            <small v-else
              >文档 #{{ source.document_id }} · 分块 #{{ source.chunk_id }} ·
              版本指纹 {{ source.fingerprint }}</small
            ><RouterLink
              v-if="'document_id' in source"
              :to="`/knowledge/${source.document_id}`"
              @click="emit('close')"
              >查看当前文档 ↗</RouterLink
            >
          </details>
          <h3>全部检索记录</h3>
          <p class="run-note">
            下方为检索当时的资料快照，可能与文档的当前版本不同。
          </p>
          <article
            v-for="(step, index) in retrievals"
            :key="index"
            class="retrieval-round"
          >
            <h4>第 {{ index + 1 }} 次检索 · {{ statusLabel(step.status) }}</h4>
            <details>
              <summary>检索输入</summary>
              <pre>{{ snapshot(step.input) }}</pre>
            </details>
            <p v-if="step.error" class="error">{{ step.error }}</p>
            <p v-if="step.output?.sources?.length === 0" class="run-note">
              未检索到有效资料。
            </p>
            <details
              v-for="source in step.output?.sources"
              :key="source.source_id"
              class="source-snapshot"
            >
              <summary>
                {{ source.source_id }} · {{ source.title }}
                <span v-if="citedIds.has(source.source_id)" class="cited-badge"
                  >最终引用</span
                >
              </summary>
              <p>{{ source.content }}</p>
              <small v-if="'url' in source"
                ><a :href="source.url" target="_blank" rel="noopener noreferrer"
                  >{{ source.url }} ↗</a
                >
                · {{ source.retrieved_at }}</small
              >
              <small v-else
                >文档 #{{ source.document_id }} · 分块 #{{ source.chunk_id }} ·
                版本指纹 {{ source.fingerprint }}</small
              >
            </details>
          </article>
          <p v-if="!retrievals.length" class="run-note">本轮未执行知识检索。</p>
        </section>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.run-content {
  min-height: 220px;
  color: #253b58;
}
.run-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  color: #6b7e96;
  font-size: 14px;
}
.run-status {
  color: #177b65;
  background: #eaf7f2;
  padding: 5px 12px;
  border-radius: 6px;
  white-space: nowrap;
}
.run-status.failed {
  color: #bd3d38;
  background: #fff0ef;
}
.run-question {
  font-size: 21px;
  font-weight: 600;
  line-height: 1.6;
  margin: 20px 0;
  overflow-wrap: anywhere;
}
.run-summary {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 12px;
}
.run-summary > div {
  border: 1px solid #dce6f4;
  background: #f5f8fe;
  border-radius: 10px;
  padding: 16px;
}
.run-summary span {
  display: block;
  font-size: 14px;
  color: #647b98;
  margin-bottom: 10px;
}
.run-summary strong {
  font-size: 19px;
  overflow-wrap: anywhere;
}
.run-meta {
  display: grid;
  gap: 9px;
  margin: 20px 0;
  font-size: 14px;
}
.run-meta > div {
  display: flex;
  gap: 16px;
}
.run-meta dt {
  color: #647b98;
  flex: 0 0 80px;
}
.run-meta dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.run-tabs {
  display: flex;
  gap: 6px;
  border-bottom: 1px solid #dce5f0;
  margin: 24px 0;
  overflow-x: auto;
}
.run-tabs button {
  border: 0;
  border-bottom: 3px solid transparent;
  padding: 12px 14px;
  background: transparent;
  color: #60738d;
  font: inherit;
  white-space: nowrap;
  cursor: pointer;
}
.run-tabs button.active {
  color: #245ee0;
  border-bottom-color: #245ee0;
  font-weight: 600;
}
.run-note {
  font-size: 14px;
  color: #647b98;
  line-height: 1.7;
  margin: 14px 0;
}
.run-steps {
  list-style: none;
  margin: 0;
  padding: 0;
}
.run-steps > li {
  border: 1px solid #dce5f0;
  border-radius: 10px;
  margin-top: 14px;
  padding: 16px;
}
.run-steps > li.failed {
  border-color: #f0bbb8;
}
.step-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
}
.step-heading strong {
  font-size: 16px;
}
.step-heading time {
  margin-left: auto;
  color: #60738d;
}
.step-number {
  border-radius: 50%;
  background: #eaf1ff;
  color: #245ee0;
  width: 27px;
  height: 27px;
  display: grid;
  place-items: center;
}
.run-content details {
  margin-top: 14px;
}
.run-content summary {
  cursor: pointer;
  color: #315984;
  line-height: 1.7;
}
.run-content h3 {
  font-size: 18px;
  margin: 24px 0 14px;
}
.run-content h4 {
  font-size: 15px;
  margin: 16px 0 8px;
}
.run-content pre {
  background: #f3f6fa;
  color: #334b69;
  border-radius: 8px;
  padding: 14px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 340px;
  overflow: auto;
  font-size: 13px;
  line-height: 1.65;
}
.usage-totals {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.usage-totals article {
  padding: 16px;
  border: 1px solid #dce5f0;
  border-radius: 10px;
}
.usage-totals h3 {
  margin: 0 0 12px;
}
.usage-totals strong {
  font-size: 18px;
}
.usage-totals p,
.usage-totals small {
  color: #647b98;
  font-size: 13px;
}
.usage-table-wrap {
  overflow-x: auto;
}
.usage-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.usage-table th,
.usage-table td {
  text-align: left;
  padding: 12px 8px;
  border-bottom: 1px solid #e0e7f1;
  vertical-align: top;
}
.usage-table th {
  background: #f5f7fb;
}
.usage-table td small {
  display: block;
  max-width: 130px;
  overflow-wrap: anywhere;
  color: #647b98;
  margin-top: 5px;
}
.context-message,
.context-question {
  background: #f5f8fe;
  padding: 14px;
  border-radius: 8px;
  margin-bottom: 12px;
}
.context-message p,
.context-question,
.source-snapshot p {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.8;
}
.context-message strong {
  font-size: 14px;
  color: #315984;
}
.context-message p {
  margin-bottom: 0;
}
.call-snapshot,
.source-snapshot,
.retrieval-round {
  border: 1px solid #dce5f0;
  border-radius: 9px;
  padding: 14px;
  margin-bottom: 12px;
}
.source-snapshot small {
  display: block;
  color: #647b98;
  overflow-wrap: anywhere;
  line-height: 1.7;
}
.source-snapshot a {
  display: inline-block;
  margin-top: 10px;
}
.cited-badge {
  font-size: 12px;
  background: #e8f7f0;
  color: #177b65;
  padding: 3px 6px;
  border-radius: 4px;
}
@media (max-width: 600px) {
  .run-summary,
  .usage-totals {
    grid-template-columns: 1fr;
  }
  .step-heading {
    flex-wrap: wrap;
  }
}
</style>
