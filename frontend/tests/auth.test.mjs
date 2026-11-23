import test, { after, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'
import { createServer } from 'vite'

// 用已有 Vite 加载真实 TypeScript 模块，模拟浏览器存储和 HTTP 边界。
const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
const { useAuthStore } = await server.ssrLoadModule('/src/stores/auth.ts')
const originalFetch = globalThis.fetch
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage')
const savedValues = new Map()
const storage = {
  getItem: key => savedValues.get(key) ?? null,
  setItem: (key, value) => savedValues.set(key, value),
  removeItem: key => savedValues.delete(key),
}
const user = { id: 1, username: 'admin', display_name: '测试管理员', role: 'admin', is_active: true, customer_tier: 1, staff_level: 1 }

beforeEach(() => {
  savedValues.clear()
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: storage })
  setActivePinia(createPinia())
})
after(async () => {
  globalThis.fetch = originalFetch
  if (originalStorage) Object.defineProperty(globalThis, 'sessionStorage', originalStorage)
  else delete globalThis.sessionStorage
  await server.close()
})

test('登录后刷新可恢复会话，用户身份重新向后端核验，退出清除保存的令牌', async () => {
  globalThis.fetch = async (url, options) => {
    if (url === '/api/auth/login') {
      return Response.json({ access_token: 'test-token', token_type: 'bearer', user })
    }
    assert.equal(url, '/api/auth/me')
    assert.equal(options.headers.get('Authorization'), 'Bearer test-token')
    return Response.json({ ...user, display_name: '最新显示名称' })
  }
  const first = useAuthStore()
  await first.signIn('admin', 'only-test-password')
  assert.ok([...savedValues.values()].includes('test-token'))
  assert.ok([...savedValues.values()].every(value => !value.includes('only-test-password')))

  setActivePinia(createPinia())
  const refreshed = useAuthStore()
  await refreshed.restoreSession()
  assert.equal(refreshed.token, 'test-token')
  assert.equal(refreshed.user.display_name, '最新显示名称')
  assert.equal(refreshed.user.role, 'admin')
  refreshed.signOut()
  assert.equal(refreshed.token, '')
  assert.equal(refreshed.user, null)
  assert.equal(savedValues.size, 0)
})

async function signInForTest() {
  globalThis.fetch = async () => Response.json({ access_token: 'test-token', token_type: 'bearer', user })
  await useAuthStore().signIn('admin', 'only-test-password')
  setActivePinia(createPinia())
  return useAuthStore()
}

test('失效凭证恢复时清除会话，不能继续冒充已登录', async () => {
  const refreshed = await signInForTest()
  globalThis.fetch = async () => Response.json({ detail: '请登录或重新登录' }, { status: 401 })
  await refreshed.restoreSession()
  assert.equal(refreshed.token, '')
  assert.equal(refreshed.user, null)
  assert.equal(savedValues.size, 0)
})

test('后端暂时不可用时准确报错，保留令牌供恢复后重试', async () => {
  const refreshed = await signInForTest()
  globalThis.fetch = async () => Response.json({ detail: '数据库暂时不可用' }, { status: 503 })
  await assert.rejects(refreshed.restoreSession(), { message: '数据库暂时不可用', status: 503 })
  assert.equal(refreshed.token, 'test-token')
  assert.equal(refreshed.user, null)
  assert.ok([...savedValues.values()].includes('test-token'))
})

test('没有登录凭证时不请求身份接口', async () => {
  globalThis.fetch = async () => { throw new Error('不应发起请求') }
  const auth = useAuthStore()
  await auth.restoreSession()
  assert.equal(auth.token, '')
  assert.equal(auth.user, null)
})
