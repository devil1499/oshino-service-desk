<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { listPeople } from '../api/people'
import type { Person } from '../api/people'
import { createStaff, setStaffActive } from '../api/users'
import { tierNames, levelNames } from '../api/service'
import { useAuthStore } from '../stores/auth'
import AppIcon from '../components/AppIcon.vue'

const auth = useAuthStore()
const people = ref<Person[]>([])
const search = ref('')
const role = ref('')
const page = ref(1)
const pageSize = 10
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const staffOpen = ref(false)
const formError = ref('')
const staffForm = reactive({ username: '', display_name: '', password: '' })
const roleNames = { admin: '管理员', staff: '客服', customer: '客户' }
const filtered = computed(() =>
  people.value.filter(
    (person) =>
      (!role.value || person.role === role.value) &&
      (person.name.includes(search.value.trim()) ||
        person.username?.includes(search.value.trim())),
  ),
)
const rows = computed(() =>
  filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize),
)
watch([role, search], () => {
  page.value = 1
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    people.value = await listPeople(auth.token)
  } catch (e) {
    if (!(e instanceof Error)) throw e
    error.value = e.message
  } finally {
    loading.value = false
  }
}
onMounted(load)

function openStaff() {
  Object.assign(staffForm, { username: '', display_name: '', password: '' })
  formError.value = ''
  notice.value = ''
  staffOpen.value = true
}
async function saveStaff() {
  saving.value = true
  formError.value = ''
  try {
    await createStaff(auth.token, {
      ...staffForm,
      display_name: staffForm.display_name.trim(),
    })
    staffForm.password = ''
    staffOpen.value = false
    search.value = ''
    role.value = 'staff'
    page.value = 1
    notice.value = '客服账号已创建'
    await load()
    if (error.value) error.value = `账号已创建，刷新列表失败：${error.value}`
  } catch (e) {
    if (!(e instanceof Error)) throw e
    formError.value = e.message
  } finally {
    saving.value = false
  }
}
async function toggleStaff(person: Person) {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const updated = await setStaffActive(
      auth.token,
      person.id,
      !person.is_active,
    )
    person.is_active = updated.is_active
    notice.value = `${person.name}已${updated.is_active ? '启用' : '停用'}`
  } catch (e) {
    if (!(e instanceof Error)) throw e
    error.value = e.message
  } finally {
    saving.value = false
  }
}
</script>
<template>
  <header class="page-heading">
    <div>
      <h1>人员管理</h1>
      <p>查看客户等级与客服分级，管理员可创建和启停客服账号。</p>
    </div>
    <button
      v-if="auth.user?.role === 'admin'"
      class="button primary"
      :disabled="saving || loading"
      @click="openStaff"
    >
      <AppIcon name="plus" :size="18" />新增客服
    </button>
  </header>
  <p v-if="error" role="alert" class="error error-panel">
    {{ error }}
    <button class="text-button" :disabled="saving || loading" @click="load">
      重新读取
    </button>
  </p>
  <p v-if="notice" role="status" class="success-panel">{{ notice }}</p>
  <section class="panel people-panel" v-loading="loading" :aria-busy="loading">
    <div class="people-toolbar">
      <label
        ><span>查找人员</span
        ><input
          v-model="search"
          placeholder="搜索姓名或客服用户名"
          type="search" /></label
      ><label
        ><span>身份</span
        ><select v-model="role">
          <option value="">全部身份</option>
          <option value="customer">客户</option>
          <option value="staff">客服</option>
          <option value="admin">管理员</option>
        </select></label
      >
    </div>
    <el-table :data="rows" empty-text="没有匹配的人员">
      <el-table-column prop="name" label="姓名" min-width="160" />
      <el-table-column label="用户名" min-width="160"
        ><template #default="{ row }">{{
          row.username ?? '—'
        }}</template></el-table-column
      >
      <el-table-column label="身份" width="110"
        ><template #default="{ row }: { row: Person }">{{
          roleNames[row.role]
        }}</template></el-table-column
      >
      <el-table-column label="等级" min-width="180"
        ><template #default="{ row }">{{
          row.role === 'customer'
            ? tierNames[row.tier]
            : row.role === 'staff'
              ? `L${row.level} ${levelNames[row.level]}`
              : '管理员'
        }}</template></el-table-column
      >
      <el-table-column label="状态" width="110"
        ><template #default="{ row }"
          ><span class="person-state" :class="{ inactive: !row.is_active }">{{
            row.is_active ? '启用' : '停用'
          }}</span></template
        ></el-table-column
      >
      <el-table-column
        v-if="auth.user?.role === 'admin'"
        label="操作"
        width="100"
        ><template #default="{ row }"
          ><button
            v-if="row.role === 'staff'"
            class="text-button"
            :disabled="saving"
            @click="toggleStaff(row)"
          >
            {{ row.is_active ? '停用' : '启用' }}</button
          ><span v-else class="muted">—</span></template
        ></el-table-column
      >
    </el-table>
    <footer class="pagination">
      <span>共 {{ filtered.length }} 人</span>
      <div>
        <button
          class="pagination-button"
          :disabled="page === 1"
          @click="page--"
        >
          上一页</button
        ><span>
          {{ page }} /
          {{ Math.max(1, Math.ceil(filtered.length / pageSize)) }} </span
        ><button
          class="pagination-button"
          :disabled="page * pageSize >= filtered.length"
          @click="page++"
        >
          下一页
        </button>
      </div>
    </footer>
    <p class="muted people-note">
      显示启用的客户及全部客服账号；客户等级影响同优先级工单排序，客服等级表示可处理的业务范围。
    </p>
  </section>
  <el-dialog
    v-model="staffOpen"
    title="新增客服"
    width="min(520px, 92vw)"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @closed="staffForm.password = ''"
  >
    <form @submit.prevent="saveStaff">
      <label class="field"
        ><span>用户名 *</span
        ><input
          v-model="staffForm.username"
          required
          minlength="3"
          maxlength="50"
          pattern="[a-zA-Z0-9_]+"
          autocomplete="off"
          :disabled="saving"
          placeholder="3–50 位字母、数字或下划线"
      /></label>
      <label class="field"
        ><span>显示姓名 *</span
        ><input
          v-model="staffForm.display_name"
          required
          maxlength="100"
          :disabled="saving"
      /></label>
      <label class="field"
        ><span>初始密码 *</span
        ><input
          v-model="staffForm.password"
          type="password"
          required
          minlength="8"
          maxlength="128"
          autocomplete="new-password"
          :disabled="saving"
      /></label>
      <p class="muted">新建账号为 L1 普通客服。</p>
      <p v-if="formError" role="alert" class="error error-panel">
        {{ formError }}
      </p>
      <div class="staff-actions">
        <button
          class="button outline"
          type="button"
          :disabled="saving"
          @click="staffOpen = false"
        >
          取消</button
        ><button
          class="button primary"
          type="submit"
          :disabled="saving || !staffForm.display_name.trim()"
        >
          {{ saving ? '正在创建…' : '创建客服' }}
        </button>
      </div>
    </form>
  </el-dialog>
</template>
<style scoped>
.people-panel {
  padding: 24px;
}
.people-toolbar {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.people-toolbar label {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
}
.people-toolbar input,
.people-toolbar select {
  font: inherit;
  color: inherit;
  background: #f8fafd;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
}
.people-toolbar input {
  width: 300px;
}
.person-state {
  color: #147d55;
  background: #edf8f3;
  padding: 4px 10px;
  border-radius: 5px;
}
.person-state.inactive {
  color: var(--muted);
  background: #edf1f6;
}
.people-note {
  margin: 20px 0 0;
  font-size: 14px;
}
.staff-actions {
  display: flex;
  justify-content: end;
  gap: 12px;
  border-top: 1px solid var(--line);
  margin-top: 24px;
  padding-top: 24px;
}
.staff-actions .button + .button {
  margin-left: 0;
}
</style>
