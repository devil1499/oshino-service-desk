<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { getCatalog, type Catalog } from "../api/config";
import {
  createConversation,
  listConversations,
  listMessages,
  sendMessage,
  type QaConversation,
  type QaMessage,
} from "../api/qa";
import AppIcon from "../components/AppIcon.vue";
import QaRunDetails from "../components/QaRunDetails.vue";
import { useAuthStore } from "../stores/auth";
import { formatRunDuration, formatTokenUsage } from "../utils/qaRunFormat";
import { getAiCapabilities } from "../api/aiService";

const auth = useAuthStore();
const catalog = ref<Catalog | null>(null);
const conversations = ref<QaConversation[]>([]);
const conversationPage = ref(1);
const conversationTotal = ref(0);
const activeId = ref<number | null>(null);
const messages = ref<QaMessage[]>([]);
const messagePage = ref(1);
const messageTotal = ref(0);
const newProductId = ref(0);
const newTitle = ref("");
const draft = ref("");
const webSearch = ref(false);
const webSearchAvailable = ref(false);
const capabilityError = ref("");
const pendingText = ref("");
const pendingConversationId = ref<number | null>(null);
const retryRequest = ref<{
  conversationId: number;
  text: string;
  requestId: string;
  webSearch: boolean;
} | null>(null);
const loading = ref(false);
const sending = ref(false);
const creating = ref(false);
const errorMessage = ref("");
const messageError = ref("");
const runTarget = ref<{ conversationId: number; messageId: number } | null>(
  null,
);
let pollTimer: number | undefined;

const selected = computed(() =>
  conversations.value.find((item) => item.id === activeId.value),
);
const activeProducts = computed(
  () => catalog.value?.products.filter((item) => item.is_active) ?? [],
);
const productName = computed(
  () =>
    catalog.value?.products.find(
      (item) => item.id === selected.value?.product_id,
    )?.name ?? "",
);

function stopPolling() {
  if (pollTimer !== undefined) window.clearTimeout(pollTimer);
  pollTimer = undefined;
}

async function loadConversations(page: number) {
  const result = await listConversations(auth.token, page);
  conversations.value = result.items;
  conversationPage.value = page;
  conversationTotal.value = result.total;
}

async function changeConversationPage(page: number) {
  try {
    await loadConversations(page);
    if (conversations.value.length)
      await chooseConversation(conversations.value[0]!.id);
  } catch (error) {
    if (!(error instanceof Error)) throw error;
    errorMessage.value = error.message;
  }
}

async function loadMessages(showLoading = true) {
  const conversationId = activeId.value;
  if (conversationId === null) return;
  stopPolling();
  if (showLoading) loading.value = true;
  messageError.value = "";
  try {
    const result = await listMessages(auth.token, conversationId);
    if (activeId.value !== conversationId) return;
    messages.value = result.items;
    messagePage.value = 1;
    messageTotal.value = result.total;
    if (result.items.some((item) => item.status === "running")) {
      pollTimer = window.setTimeout(() => {
        void loadMessages(false);
      }, 2000);
    }
  } catch (error) {
    if (!(error instanceof Error)) throw error;
    if (activeId.value === conversationId) messageError.value = error.message;
  } finally {
    loading.value = false;
  }
}

async function chooseConversation(conversationId: number) {
  stopPolling();
  runTarget.value = null;
  activeId.value = conversationId;
  messages.value = [];
  messageTotal.value = 0;
  errorMessage.value = "";
  await loadMessages();
}

async function loadOlder() {
  if (activeId.value === null || messages.value.length >= messageTotal.value)
    return;
  const conversationId = activeId.value;
  const nextPage = messagePage.value + 1;
  try {
    const result = await listMessages(auth.token, conversationId, nextPage);
    if (activeId.value !== conversationId) return;
    messages.value = [...result.items, ...messages.value];
    messagePage.value = nextPage;
  } catch (error) {
    if (!(error instanceof Error)) throw error;
    messageError.value = error.message;
  }
}

async function createNewConversation() {
  if (!newProductId.value || !newTitle.value.trim()) {
    errorMessage.value = "请选择产品并填写会话标题。";
    return;
  }
  creating.value = true;
  errorMessage.value = "";
  try {
    const created = await createConversation(auth.token, {
      product_id: newProductId.value,
      title: newTitle.value.trim(),
    });
    await loadConversations(1);
    newTitle.value = "";
    await chooseConversation(created.id);
  } catch (error) {
    if (!(error instanceof Error)) throw error;
    errorMessage.value = error.message;
  } finally {
    creating.value = false;
  }
}

async function send() {
  const text = draft.value.trim();
  const conversationId = activeId.value;
  if (!text || conversationId === null || sending.value) return;
  const requestId =
    retryRequest.value?.conversationId === conversationId &&
    retryRequest.value.text === text &&
    retryRequest.value.webSearch === webSearch.value
      ? retryRequest.value.requestId
      : crypto.randomUUID();
  sending.value = true;
  pendingText.value = text;
  pendingConversationId.value = conversationId;
  errorMessage.value = "";
  try {
    await sendMessage(auth.token, conversationId, {
      request_id: requestId,
      text,
      web_search: webSearch.value,
    });
    retryRequest.value = null;
    if (activeId.value === conversationId) {
      draft.value = "";
      await loadMessages(false);
    }
  } catch (error) {
    if (!(error instanceof Error)) throw error;
    if (activeId.value === conversationId) {
      errorMessage.value = error.message;
      await loadMessages(false);
      const saved = messages.value.filter(
        (item) => item.request_id === requestId,
      );
      retryRequest.value = saved.length
        ? null
        : { conversationId, text, requestId, webSearch: webSearch.value };
      if (
        saved.some(
          (item) => item.role === "assistant" && item.status === "answered",
        )
      )
        draft.value = "";
    }
  } finally {
    pendingText.value = "";
    pendingConversationId.value = null;
    sending.value = false;
  }
}

onMounted(async () => {
  try {
    webSearchAvailable.value = (
      await getAiCapabilities(auth.token)
    ).web_search_available;
  } catch (error) {
    if (!(error instanceof Error)) throw error;
    capabilityError.value = error.message;
  }
  try {
    catalog.value = await getCatalog(auth.token);
    await loadConversations(1);
    if (conversations.value.length)
      await chooseConversation(conversations.value[0]!.id);
  } catch (error) {
    if (!(error instanceof Error)) throw error;
    errorMessage.value = error.message;
  }
});
onUnmounted(stopPolling);
</script>

<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">工作空间 / 产品知识</div>
      <h1>智能助手</h1>
      <p>
        围绕已发布的产品资料提问，继续追问时保留上下文；每条有依据的回答都附来源。
      </p>
    </div>
    <RouterLink to="/knowledge" class="button outline"
      ><AppIcon name="book" :size="18" />查看知识库</RouterLink
    >
  </div>

  <div class="qa-layout">
    <aside class="qa-conversations" aria-label="问答会话">
      <div class="qa-new-heading">
        <h2>我的会话</h2>
        <span>{{ conversationTotal }}</span>
      </div>
      <form class="qa-new-form" @submit.prevent="createNewConversation">
        <label
          >选择产品
          <select v-model.number="newProductId" required :disabled="creating">
            <option :value="0">请选择产品</option>
            <option
              v-for="product in activeProducts"
              :key="product.id"
              :value="product.id"
            >
              {{ product.name }}
            </option>
          </select>
        </label>
        <label
          >会话标题<input
            v-model="newTitle"
            required
            maxlength="100"
            placeholder="如：E401 登录排查"
            :disabled="creating"
        /></label>
        <button type="submit" class="button primary" :disabled="creating">
          新建会话
        </button>
      </form>
      <div class="qa-conversation-list">
        <button
          v-for="conversation in conversations"
          :key="conversation.id"
          type="button"
          class="qa-conversation"
          :class="{ active: conversation.id === activeId }"
          :aria-current="conversation.id === activeId ? 'true' : undefined"
          @click="chooseConversation(conversation.id)"
        >
          <strong>{{ conversation.title }}</strong>
          <small>{{
            catalog?.products.find(
              (item) => item.id === conversation.product_id,
            )?.name
          }}</small>
        </button>
        <p v-if="!conversations.length" class="qa-list-empty">
          新建会话后，就可以开始提问。
        </p>
      </div>
      <div v-if="conversationTotal > 20" class="qa-list-pages">
        <button
          type="button"
          :disabled="conversationPage === 1"
          @click="changeConversationPage(conversationPage - 1)"
        >
          上一页
        </button>
        <span
          >{{ conversationPage }} /
          {{ Math.ceil(conversationTotal / 20) }}</span
        >
        <button
          type="button"
          :disabled="conversationPage * 20 >= conversationTotal"
          @click="changeConversationPage(conversationPage + 1)"
        >
          下一页
        </button>
      </div>
    </aside>

    <section class="qa-chat" aria-label="智能助手对话">
      <header class="qa-chat-header">
        <div>
          <span class="eyebrow">知识问答 · 仅供处理参考</span>
          <h2>{{ selected?.title ?? "开始新会话" }}</h2>
        </div>
        <span v-if="selected" class="qa-product">{{ productName }}</span>
      </header>
      <p v-if="errorMessage" class="error error-panel" role="alert">
        {{ errorMessage }}
      </p>
      <p v-if="messageError" class="error error-panel" role="alert">
        读取历史失败：{{ messageError }}
        <button type="button" @click="loadMessages()">重新读取</button>
      </p>
      <div v-if="!selected" class="qa-welcome">
        <AppIcon name="book" :size="36" />
        <h3>先选产品，创建一个会话</h3>
        <p>助手只会检索这个产品已发布的资料；资料不足时会明确说明。</p>
      </div>
      <template v-else>
        <div class="qa-messages" aria-live="polite">
          <button
            v-if="messages.length < messageTotal"
            type="button"
            class="qa-older"
            @click="loadOlder"
          >
            读取更早的消息
          </button>
          <p v-if="loading" class="muted">正在读取消息……</p>
          <p v-else-if="!messages.length" class="qa-empty-chat">
            可以问产品功能、操作步骤或故障处理。回答后可继续追问。
          </p>
          <article
            v-for="message in messages"
            :key="message.id"
            class="qa-message"
            :class="[message.role, { failed: message.status === 'failed' }]"
          >
            <div class="qa-message-label">
              {{ message.role === "user" ? "我" : "智能助手"
              }}<span v-if="message.status === 'failed'">· 处理失败</span>
              <span v-if="message.web_search"> · 已开启联网搜索</span>
            </div>
            <div class="qa-message-content">
              {{ message.content || "正在检索资料并组织回答……" }}
            </div>
            <div v-if="message.role === 'assistant'" class="qa-run-bar">
              <span>耗时：{{ formatRunDuration(message.duration_ms) }}</span>
              <span>Token：{{ formatTokenUsage(message.token_usage) }}</span>
              <button
                v-if="message.has_run && activeId !== null"
                type="button"
                class="text-button"
                @click="
                  runTarget = {
                    conversationId: activeId,
                    messageId: message.id,
                  }
                "
              >
                运行详情
              </button>
              <span v-else class="muted">{{
                message.status === "running"
                  ? "运行记录准备中"
                  : "此回答没有运行详情"
              }}</span>
            </div>
            <div v-if="message.sources.length" class="qa-sources">
              <strong>参考资料</strong>
              <details
                v-for="source in message.sources"
                :key="source.source_id"
              >
                <summary>{{ source.source_id }} · {{ source.title }}</summary>
                <a
                  v-if="'url' in source"
                  :href="source.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  >网页来源 ↗</a
                >
                <RouterLink v-else :to="`/knowledge/${source.document_id}`"
                  >查看文档 ↗</RouterLink
                >
                <p>{{ source.content }}</p>
              </details>
            </div>
          </article>
          <article
            v-if="
              pendingText &&
              pendingConversationId === activeId &&
              !messages.some((item) => item.status === 'running')
            "
            class="qa-message user qa-pending"
          >
            <div class="qa-message-label">我 · 发送中</div>
            <div class="qa-message-content">{{ pendingText }}</div>
          </article>
        </div>
        <form class="qa-compose" @submit.prevent="send">
          <label for="qa-question">继续提问</label>
          <label class="qa-web-toggle"
            ><input
              v-model="webSearch"
              type="checkbox"
              :disabled="sending || !webSearchAvailable"
            />联网搜索
            <small>{{
              webSearchAvailable
                ? "可选：会发送脱敏检索词到 DeepSeek"
                : "请管理员在 AI 服务中启用"
            }}</small></label
          >
          <p v-if="capabilityError" class="error">
            读取搜索配置失败：{{ capabilityError }}
          </p>
          <textarea
            id="qa-question"
            v-model="draft"
            maxlength="2000"
            rows="3"
            :disabled="sending"
            placeholder="描述问题、错误提示或想了解的操作……"
          />
          <div>
            <span>{{
              webSearch
                ? "参考知识库与互联网资料；内部政策仍须以产品知识为准。"
                : "仅参考当前产品已发布的知识；重要操作请人工核实。"
            }}</span
            ><button
              type="submit"
              class="button primary"
              :disabled="
                sending ||
                !draft.trim() ||
                messages.some((item) => item.status === 'running')
              "
            >
              {{ sending ? "回答中……" : "发送问题" }}
            </button>
          </div>
        </form>
      </template>
    </section>
  </div>
  <QaRunDetails :target="runTarget" @close="runTarget = null" />
</template>

<style scoped>
.qa-web-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0;
}
.qa-web-toggle input {
  width: 18px;
  height: 18px;
  accent-color: #2563eb;
}
.qa-web-toggle small {
  color: #60738f;
  font-weight: normal;
}
.qa-run-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 18px;
  margin: 12px 0 4px;
  color: #647b98;
  font-size: 14px;
  line-height: 1.6;
}
.qa-run-bar .text-button {
  font-size: inherit;
}
</style>
