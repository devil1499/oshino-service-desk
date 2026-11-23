<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import {
  getAiSettings,
  saveAiSettings,
  testAiChat,
  testAiSearch,
  type AiSettingsInput,
} from "../api/aiService";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const form = reactive<AiSettingsInput>({
  chat_base_url: "",
  chat_model: "",
  chat_api_key: "",
  search_enabled: false,
  search_reuse_chat_key: true,
  search_api_key: "",
});
const chatKeyConfigured = ref(false);
const searchKeyConfigured = ref(false);
const loading = ref(true);
const saving = ref(false);
const testing = ref("");
const dirty = ref(false);
const error = ref("");
const notice = ref("");
const searchResults = ref<{ title: string; url: string }[]>([]);

onMounted(async () => {
  try {
    const saved = await getAiSettings(auth.token);
    Object.assign(form, {
      chat_base_url: saved.chat_base_url,
      chat_model: saved.chat_model,
      search_enabled: saved.search_enabled,
      search_reuse_chat_key: saved.search_reuse_chat_key,
    });
    chatKeyConfigured.value = saved.chat_key_configured;
    searchKeyConfigured.value = saved.search_key_configured;
  } catch (cause) {
    if (!(cause instanceof Error)) throw cause;
    error.value = cause.message;
  } finally {
    loading.value = false;
  }
});

async function save() {
  saving.value = true;
  error.value = "";
  notice.value = "";
  searchResults.value = [];
  try {
    const saved = await saveAiSettings(auth.token, { ...form });
    chatKeyConfigured.value = saved.chat_key_configured;
    searchKeyConfigured.value = saved.search_key_configured;
    form.chat_api_key = "";
    form.search_api_key = "";
    dirty.value = false;
    notice.value = "已保存。下一次模型请求使用新配置，无需重启。";
  } catch (cause) {
    if (!(cause instanceof Error)) throw cause;
    error.value = cause.message;
  } finally {
    saving.value = false;
  }
}

async function test(kind: "chat" | "search") {
  testing.value = kind;
  error.value = "";
  notice.value = "";
  searchResults.value = [];
  try {
    if (kind === "chat") notice.value = (await testAiChat(auth.token)).message;
    else {
      const result = await testAiSearch(auth.token);
      notice.value = result.message;
      searchResults.value = result.sources;
    }
  } catch (cause) {
    if (!(cause instanceof Error)) throw cause;
    error.value = cause.message;
  } finally {
    testing.value = "";
  }
}
</script>

<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">管理中心 / 模型与搜索</div>
      <h1>AI 服务</h1>
      <p>配置聊天模型与 DeepSeek 联网搜索，统一供智能助手使用。</p>
    </div>
  </div>
  <p v-if="error" class="error error-panel" role="alert">{{ error }}</p>
  <p v-if="notice" class="ai-notice" role="status">{{ notice }}</p>
  <form
    class="ai-settings"
    @submit.prevent="save"
    @input="dirty = true"
    @change="dirty = true"
  >
    <fieldset :disabled="loading || saving || !!testing">
      <section class="ai-card">
        <div class="ai-card-heading">
          <div>
            <span class="ai-number">01</span>
            <h2>聊天模型</h2>
            <p>
              用于智能问答、工单分析与处理建议，兼容现有 Chat Completions 接口。
            </p>
          </div>
          <span class="ai-status">{{
            chatKeyConfigured ? "密钥已配置" : "待配置"
          }}</span>
        </div>
        <div class="ai-fields">
          <label
            >API 地址<input
              v-model.trim="form.chat_base_url"
              required
              type="url"
              placeholder="https://api.deepseek.com"
              autocomplete="off"
            /><small
              >填服务根地址或兼容服务要求的 /v1 地址，不含
              /chat/completions。</small
            ></label
          >
          <label
            >模型名称<input
              v-model.trim="form.chat_model"
              required
              maxlength="200"
              placeholder="填写服务商提供的模型 ID"
              autocomplete="off"
          /></label>
          <label class="ai-full"
            >API Key<input
              v-model.trim="form.chat_api_key"
              type="password"
              maxlength="1000"
              :required="!chatKeyConfigured"
              :placeholder="
                chatKeyConfigured
                  ? '已配置；留空保留，填入新值替换'
                  : '请输入 API Key'
              "
              autocomplete="new-password"
            /><small
              >密钥仅保存在后端私有文件中，页面不会读取已保存的原文。</small
            ></label
          >
        </div>
        <button
          class="button outline"
          type="button"
          :disabled="dirty || !chatKeyConfigured"
          @click="test('chat')"
        >
          {{ testing === "chat" ? "正在检查…" : "测试聊天连接" }}
        </button>
      </section>
      <section class="ai-card">
        <div class="ai-card-heading">
          <div>
            <span class="ai-number">02</span>
            <h2>DeepSeek 联网搜索</h2>
            <p>搜索互联网作为补充资料，回答会附网页出处。</p>
          </div>
          <label class="ai-check"
            ><input
              v-model="form.search_enabled"
              type="checkbox"
            />启用搜索服务</label
          >
        </div>
        <div class="ai-fields">
          <label class="ai-full"
            >搜索接口<input
              value="https://api.deepseek.com/v1/tools/search"
              readonly
            /><small
              >使用 DeepSeek
              官方独立搜索接口；兼容聊天平台的密钥不一定能调用此接口。</small
            ></label
          >
          <label class="ai-check ai-full"
            ><input
              v-model="form.search_reuse_chat_key"
              type="checkbox"
            />复用聊天 API Key（需为 DeepSeek 官方密钥）</label
          >
          <label v-if="!form.search_reuse_chat_key" class="ai-full"
            >DeepSeek 搜索 API Key<input
              v-model.trim="form.search_api_key"
              type="password"
              maxlength="1000"
              placeholder="留空保留已有搜索密钥"
              autocomplete="new-password"
          /></label>
        </div>
        <p class="ai-help">
          客服仍需在每轮提问时开启“联网搜索”。会发送脱敏后的检索词，搜索按服务商规则计费；请勿提交客户隐私。网络资料不能替代内部售后政策。
        </p>
        <button
          class="button outline"
          type="button"
          :disabled="dirty || !form.search_enabled || !searchKeyConfigured"
          @click="test('search')"
        >
          {{ testing === "search" ? "正在搜索…" : "测试联网搜索" }}
        </button>
      </section>
      <div class="ai-save">
        <span>{{
          dirty
            ? "配置已修改，请保存后再测试。"
            : "连接测试使用已保存配置，并会调用真实服务。"
        }}</span
        ><button class="button primary" type="submit">
          {{ saving ? "保存中…" : "保存配置" }}
        </button>
      </div>
    </fieldset>
  </form>
  <section v-if="searchResults.length" class="ai-card">
    <h2>搜索测试结果</h2>
    <ul>
      <li v-for="item in searchResults" :key="item.url">
        <a :href="item.url" target="_blank" rel="noopener noreferrer"
          >{{ item.title }} ↗</a
        >
      </li>
    </ul>
  </section>
</template>

<style scoped>
.ai-settings {
  max-width: 1160px;
}
.ai-settings fieldset {
  border: 0;
  padding: 0;
  margin: 0;
  min-width: 0;
}
.ai-card {
  background: white;
  border: 1px solid #dbe4ef;
  border-radius: 14px;
  padding: 28px;
  margin-bottom: 22px;
}
.ai-card-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 22px;
  margin-bottom: 24px;
}
.ai-card-heading h2 {
  display: inline;
  margin-left: 12px;
  font-size: 22px;
}
.ai-card-heading p {
  color: #60738f;
  margin-bottom: 0;
  line-height: 1.7;
}
.ai-number {
  background: #edf3ff;
  color: #2563eb;
  padding: 7px 9px;
  border-radius: 8px;
  font-weight: 700;
}
.ai-status {
  background: #e8f6ef;
  color: #14735b;
  padding: 7px 12px;
  border-radius: 20px;
  white-space: nowrap;
}
.ai-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 22px;
  margin-bottom: 24px;
}
.ai-fields label {
  display: grid;
  align-content: start;
  gap: 10px;
}
.ai-fields input {
  width: 100%;
  box-sizing: border-box;
  padding: 12px 14px;
  border: 1px solid #ced9e7;
  border-radius: 8px;
  font-size: 16px;
}
.ai-fields small,
.ai-help {
  color: #60738f;
  font-size: 14px;
  line-height: 1.7;
}
.ai-full {
  grid-column: 1 / -1;
}
.ai-check {
  display: flex !important;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
}
.ai-check input {
  width: 18px;
  height: 18px;
  accent-color: #2563eb;
}
.ai-save {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 0 0 28px;
  color: #60738f;
}
.ai-notice {
  background: #e8f6ef;
  padding: 16px;
  border-radius: 10px;
  color: #14735b;
}
.ai-card li {
  margin: 12px 0;
}
@media (max-width: 820px) {
  .ai-fields {
    grid-template-columns: 1fr;
  }
  .ai-card-heading {
    flex-direction: column;
  }
  .ai-card {
    padding: 20px;
  }
}
</style>
