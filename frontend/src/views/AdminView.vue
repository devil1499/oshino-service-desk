<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { createConfig, getCatalog, updateConfig } from '../api/config'
import type { Catalog, ConfigKind } from '../api/config'
import type { NamedItem } from '../api/models'
import AppIcon from '../components/AppIcon.vue'
import { useAuthStore } from '../stores/auth'

type CatalogRow = NamedItem & { product_id?: number }
const auth = useAuthStore()
const catalog = ref<Catalog>({ products: [], modules: [], categories: [] })
const configKind = ref<ConfigKind>('products')
const kindLabels: Record<ConfigKind, string> = {
  products: '产品',
  modules: '模块',
  categories: '问题分类',
}
const configKinds: ConfigKind[] = ['products', 'modules', 'categories']
const search = ref('')
const page = ref(1)
const pageSize = 10
const filteredRows = computed(() =>
  catalog.value[configKind.value].filter((item) =>
    item.name.includes(search.value.trim()),
  ),
)
const rows = computed(() =>
  filteredRows.value.slice((page.value - 1) * pageSize, page.value * pageSize),
)
const productNames = computed(() =>
  Object.fromEntries(
    catalog.value.products.map((item) => [item.id, item.name]),
  ),
)
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const notice = ref('')
const formOpen = ref(false)
const formError = ref('')
const formKind = ref<ConfigKind>('products')
const configName = ref('')
const configActive = ref(true)
const productId = ref<number>()
const editingId = ref<number | null>(null)
const nameInput = ref<HTMLInputElement | null>(null)
const formTitle = computed(() =>
  editingId.value === null ? '新增基础资料' : '编辑基础资料',
)

watch([configKind, search], () => {
  page.value = 1
})
watch(configKind, () => {
  formOpen.value = false
})

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    catalog.value = await getCatalog(auth.token)
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function openForm(item?: CatalogRow) {
  formKind.value = configKind.value
  editingId.value = item?.id ?? null
  configName.value = item?.name ?? ''
  configActive.value = item?.is_active ?? true
  productId.value = item?.product_id
  formError.value = ''
  notice.value = ''
  formOpen.value = true
  await nextTick()
  nameInput.value?.focus()
}

async function saveConfig() {
  saving.value = true
  formError.value = ''
  notice.value = ''
  try {
    if (editingId.value === null) {
      // 新建接口默认启用；编辑接口负责启停，避免创建后再发第二次请求。
      await createConfig(
        auth.token,
        formKind.value,
        configName.value.trim(),
        productId.value,
      )
    } else {
      await updateConfig(
        auth.token,
        formKind.value,
        editingId.value,
        configName.value.trim(),
        configActive.value,
      )
    }
    formOpen.value = false
    configKind.value = formKind.value
    search.value = ''
    page.value = 1
    notice.value = `${kindLabels[formKind.value]}已保存`
    await load()
    if (errorMessage.value)
      errorMessage.value = `保存已完成，刷新列表失败：${errorMessage.value}`
  } catch (error) {
    if (!(error instanceof Error)) throw error
    formError.value = error.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <header class="page-heading">
    <div>
      <h1>基础资料</h1>
      <p>维护产品、模块与问题分类。</p>
    </div>
  </header>
  <p v-if="errorMessage" class="error error-panel" role="alert">
    {{ errorMessage }}
    <button
      type="button"
      class="text-button"
      :disabled="loading || saving"
      @click="load"
    >
      重新读取
    </button>
  </p>
  <p v-if="notice" class="success-panel" role="status">{{ notice }}</p>
  <div class="catalog-layout" :class="{ 'with-form': formOpen }">
    <section
      class="panel catalog-list"
      aria-label="基础资料列表"
      :aria-busy="loading"
      v-loading="loading"
    >
      <div class="catalog-toolbar">
        <label class="type-filter"
          ><span class="sr-only">资料类型</span
          ><select
            v-model="configKind"
            aria-label="资料类型"
            :disabled="saving"
          >
            <option v-for="kind in configKinds" :key="kind" :value="kind">
              {{ kindLabels[kind] }}
            </option>
          </select></label
        >
        <label class="search-field"
          ><span class="sr-only">搜索名称</span
          ><input
            v-model="search"
            type="search"
            placeholder="搜索名称"
            :disabled="saving"
        /></label>
        <button
          type="button"
          class="button primary"
          :disabled="loading || saving || !!errorMessage"
          @click="openForm()"
        >
          <AppIcon name="plus" :size="18" />新增{{ kindLabels[configKind] }}
        </button>
      </div>
      <el-table
        :data="rows"
        :row-class-name="
          ({ row }: { row: CatalogRow }) =>
            formOpen && editingId === row.id && configKind === formKind
              ? 'editing-row'
              : ''
        "
        empty-text="没有匹配的资料"
      >
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column
          v-if="configKind === 'modules'"
          label="所属产品"
          min-width="180"
          ><template #default="{ row }">{{
            productNames[row.product_id]
          }}</template></el-table-column
        >
        <el-table-column label="状态" width="90"
          ><template #default="{ row }"
            ><span class="state" :class="{ inactive: !row.is_active }">{{
              row.is_active ? '启用' : '停用'
            }}</span></template
          ></el-table-column
        >
        <el-table-column label="操作" width="80"
          ><template #default="{ row }"
            ><button
              type="button"
              class="text-button"
              :disabled="saving"
              @click="openForm(row)"
            >
              编辑
            </button></template
          ></el-table-column
        >
      </el-table>
      <footer class="pagination">
        <span>共 {{ filteredRows.length }} 条</span>
        <div>
          <button
            class="pagination-button"
            :disabled="page === 1"
            @click="page--"
          >
            上一页</button
          ><span>
            {{ page }} /
            {{ Math.max(1, Math.ceil(filteredRows.length / pageSize)) }} </span
          ><button
            class="pagination-button"
            :disabled="page * pageSize >= filteredRows.length"
            @click="page++"
          >
            下一页
          </button>
        </div>
      </footer>
    </section>
    <section
      v-if="formOpen"
      class="panel catalog-editor"
      aria-labelledby="catalog-form-title"
    >
      <header class="editor-heading">
        <div>
          <h2 id="catalog-form-title">{{ formTitle }}</h2>
          <p class="muted">填写后点击保存，取消不会修改资料。</p>
        </div>
        <button
          class="icon-button"
          type="button"
          aria-label="关闭表单"
          :disabled="saving"
          @click="formOpen = false"
        >
          ×
        </button>
      </header>
      <form aria-label="基础资料表单" @submit.prevent="saveConfig">
        <fieldset :disabled="saving">
          <label class="field"
            ><span>资料类型</span
            ><select
              v-model="formKind"
              :disabled="editingId !== null"
              @change="productId = undefined"
            >
              <option v-for="kind in configKinds" :key="kind" :value="kind">
                {{ kindLabels[kind] }}
              </option>
            </select></label
          >
          <label class="field"
            ><span>名称 <span class="required">*</span></span
            ><input
              ref="nameInput"
              v-model="configName"
              required
              maxlength="100"
              placeholder="填写名称"
          /></label>
          <label v-if="formKind === 'modules'" class="field"
            ><span>所属产品 <span class="required">*</span></span
            ><select
              v-model="productId"
              required
              :disabled="editingId !== null"
            >
              <option :value="undefined" disabled>请选择所属产品</option>
              <option
                v-for="item in catalog.products"
                :key="item.id"
                :value="item.id"
                :disabled="!item.is_active"
              >
                {{ item.name }}{{ item.is_active ? '' : '（已停用）' }}
              </option></select
            ><small class="muted">{{
              editingId === null
                ? '模块需要关联一个产品。'
                : '所属产品创建后不可修改，避免影响已有工单。'
            }}</small></label
          >
          <fieldset v-if="editingId !== null" class="state-options">
            <legend>状态</legend>
            <label
              ><input
                v-model="configActive"
                type="radio"
                :value="true"
              />启用</label
            ><label
              ><input
                v-model="configActive"
                type="radio"
                :value="false"
              />停用</label
            >
          </fieldset>
          <p v-else class="muted">新建资料默认启用。</p>
        </fieldset>
        <p v-if="formError" class="error error-panel" role="alert">
          {{ formError }}
        </p>
        <footer class="form-actions">
          <button
            type="button"
            class="button outline"
            :disabled="saving"
            @click="formOpen = false"
          >
            取消</button
          ><button
            type="submit"
            class="button primary"
            :disabled="
              saving ||
              !configName.trim() ||
              (formKind === 'modules' && productId === undefined)
            "
          >
            {{
              saving
                ? '正在保存…'
                : editingId === null
                  ? `创建${kindLabels[formKind]}`
                  : '保存修改'
            }}
          </button>
        </footer>
      </form>
    </section>
  </div>
</template>

<style scoped>
.catalog-layout {
  display: grid;
  gap: 22px;
  align-items: start;
}
.catalog-layout.with-form {
  grid-template-columns: minmax(0, 1.35fr) minmax(360px, 1fr);
}
.catalog-list,
.catalog-editor {
  min-width: 0;
  padding: 24px;
}
.catalog-list {
  min-height: 570px;
  display: flex;
  flex-direction: column;
}
.catalog-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 24px;
}
.catalog-toolbar label {
  margin: 0;
}
.type-filter {
  flex: 0 0 140px;
}
.search-field {
  flex: 1 1 160px;
}
.catalog-toolbar input,
.catalog-toolbar select {
  width: 100%;
  min-height: 46px;
  padding: 10px 12px;
  color: inherit;
  background: #f8fafd;
  border: 1px solid var(--line);
  border-radius: 8px;
  font: inherit;
}
.catalog-toolbar .button {
  white-space: nowrap;
}
.pagination {
  margin-top: auto;
  padding-top: 24px;
  gap: 12px;
  flex-wrap: wrap;
}
.editor-heading {
  display: flex;
  justify-content: space-between;
  align-items: start;
  margin-bottom: 24px;
  gap: 12px;
}
.editor-heading h2 {
  font-size: 24px;
  margin: 0 0 10px;
}
.editor-heading p {
  margin: 0;
  font-size: 15px;
}
.catalog-editor {
  position: sticky;
  top: 24px;
}
.catalog-editor form {
  min-height: 430px;
  display: flex;
  flex-direction: column;
}
fieldset {
  border: 0;
  padding: 0;
  margin: 0;
  min-width: 0;
}
.state-options {
  display: flex;
  gap: 28px;
  padding-bottom: 20px;
}
.state-options legend {
  margin-bottom: 14px;
}
.state-options label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
.state-options input {
  width: 18px;
  height: 18px;
  accent-color: #245ee0;
}
.required {
  color: #cf3944;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: auto;
  padding-top: 24px;
  border-top: 1px solid var(--line);
}
.form-actions .button + .button {
  margin-left: 0;
}
.state {
  display: inline-block;
  color: #147d55;
  background: #edf8f3;
  padding: 3px 10px;
  border-radius: 5px;
  white-space: nowrap;
}
.state.inactive {
  color: var(--muted);
  background: #edf1f6;
}
:deep(.editing-row) {
  --el-table-tr-bg-color: #edf3ff;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
@media (max-width: 1200px) {
  .catalog-layout.with-form {
    grid-template-columns: 1fr;
  }
  .catalog-editor {
    position: static;
  }
}
</style>
