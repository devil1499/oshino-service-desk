<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AppIcon from '../components/AppIcon.vue'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref(typeof route.query.session_error === 'string' ? route.query.session_error : '')

async function submit() {
  submitting.value = true
  errorMessage.value = ''
  try {
    await auth.signIn(username.value, password.value)
    password.value = ''
    const redirect = route.query.redirect
    const destination =
      typeof redirect === 'string' && /^\/(?:tickets(?:\/(?:new|\d+(?:\/edit)?))?|knowledge(?:\/(?:new|\d+))?)$/.test(redirect)
        ? redirect
        : '/service'
    await router.push(
      (redirect === '/admin' || redirect === '/tickets/import') && auth.user?.role === 'admin'
        ? redirect
        : auth.user?.role === 'customer' ? '/service' : destination,
    )
  } catch (error) {
    if (!(error instanceof Error)) throw error
    errorMessage.value = error.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-layout">
      <section class="login-story" aria-label="工作台介绍">
        <RouterLink to="/tickets" class="login-brand">
          <span class="login-brand-mark"><AppIcon name="ticket" :size="26" /></span>
          <span>
            售后工单
            <small>客户支持工作台</small>
          </span>
        </RouterLink>
        <div class="login-intro">
          <div class="eyebrow">每一次回应，都值得认真对待</div>
          <h1>
            让每一次服务，
            <br />
            都有清晰的下一步。
          </h1>
          <p>从问题受理到处理完成，让服务过程有迹可循。</p>
          <div class="login-flow-label">工单流程示意</div>
          <ol class="login-flow">
            <li>
              <span class="login-flow-icon"><AppIcon name="ticket" :size="25" /></span>
              <strong>受理问题</strong>
              <small>
                记录客户反馈
                <br />
                创建服务工单
              </small>
            </li>
            <li>
              <span class="login-flow-icon"><AppIcon name="settings" :size="25" /></span>
              <strong>跟进处理</strong>
              <small>
                明确负责人
                <br />
                记录处理进展
              </small>
            </li>
            <li>
              <span class="login-flow-icon"><AppIcon name="check" :size="25" /></span>
              <strong>确认完成</strong>
              <small>
                人工回复客户
                <br />
                确认关闭工单
              </small>
            </li>
          </ol>
        </div>
        <small class="login-story-footer">售后工单智能辅助系统 · 本地工作空间</small>
      </section>
      <section class="login-form-panel" aria-labelledby="login-title">
        <div class="eyebrow">欢迎回来</div>
        <h2 id="login-title">登录工作台</h2>
        <p class="muted">使用管理员创建的账号继续。</p>
        <form @submit.prevent="submit">
          <el-form-item label="用户名" for="login-username">
            <el-input
              id="login-username"
              v-model="username"
              autocomplete="username"
              maxlength="50"
              placeholder="输入用户名"
              required
            />
          </el-form-item>
          <el-form-item label="密码" for="login-password">
            <el-input
              id="login-password"
              v-model="password"
              type="password"
              show-password
              autocomplete="current-password"
              placeholder="输入密码"
              required
            />
          </el-form-item>
          <p v-if="errorMessage" role="alert" class="error">{{ errorMessage }}</p>
          <el-button type="primary" native-type="submit" :loading="submitting" class="login-submit">
            登录工作台
            <AppIcon name="arrow-right" :size="20" />
          </el-button>
        </form>
        <p class="login-note">登录有效期为 8 小时，当前标签页刷新后可保持登录。</p>
        <div class="login-divider"><span>登录前可以检查服务状态</span></div>
        <RouterLink to="/health" class="button outline login-demo">
          检查服务连接
          <AppIcon name="arrow-right" :size="18" />
        </RouterLink>
      </section>
    </div>
  </div>
</template>
