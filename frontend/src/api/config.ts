import { request, requestAll } from './http'
import { moduleSchema, namedSchema } from './models'

// 给基础资料的返回类型起名，页面不用重复写嵌套的类型表达式。
export type Catalog = Awaited<ReturnType<typeof getCatalog>>

export type ConfigKind = 'products' | 'modules' | 'categories'

export async function getCatalog(token: string) {
  const [products, modules, categories] = await Promise.all([
    requestAll('/config/products', namedSchema, token),
    requestAll('/config/modules', moduleSchema, token),
    requestAll('/config/categories', namedSchema, token),
  ])
  return { products, modules, categories }
}

export function createConfig(token: string, kind: ConfigKind, name: string, product_id?: number) {
  if (kind === 'modules') {
    return request('/config/modules', moduleSchema, {
      token, method: 'POST', body: { name, product_id },
    })
  }
  return request(`/config/${kind}`, namedSchema, { token, method: 'POST', body: { name } })
}

export function updateConfig(token: string, kind: ConfigKind, id: number, name: string, is_active: boolean) {
  return request(`/config/${kind}/${id}`, namedSchema, {
    token, method: 'PUT', body: { name, is_active },
  })
}
