import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getCurrentUser, login } from '../api/users'
import { ApiError } from '../api/http'
import type { User } from '../api/models'

const SESSION_TOKEN_KEY = 'oshino.access_token'

export const useAuthStore = defineStore('auth', () => {
  // 当前标签页刷新后保留令牌；用户身份和角色仍由后端确认。
  const token = ref(sessionStorage.getItem(SESSION_TOKEN_KEY) ?? '')
  const user = ref<User | null>(null)

  async function signIn(username: string, password: string) {
    const result = await login(username, password)
    sessionStorage.setItem(SESSION_TOKEN_KEY, result.access_token)
    token.value = result.access_token
    user.value = result.user
  }

  async function restoreSession() {
    if (!token.value) return
    try {
      user.value = await getCurrentUser(token.value)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        signOut()
        return
      }
      throw error
    }
  }

  function signOut() {
    token.value = ''
    user.value = null
    sessionStorage.removeItem(SESSION_TOKEN_KEY)
  }

  return { token, user, signIn, signOut, restoreSession }
})
