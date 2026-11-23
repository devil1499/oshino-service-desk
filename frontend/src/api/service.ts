import { z } from 'zod'
import { request } from './http'

export const tierNames = ['', '青铜', '铂金', '王者', '最强王者']
export const levelNames = ['', '普通客服', '技术客服', '售后主管']
export const serviceStatus: Record<string, string> = {
  ai: '智能咨询中',
  pending: '等待接单',
  processing: '人工服务中',
  resolved: '待客户确认',
  closed: '已完成',
}
const card = z.object({
  id: z.number(),
  title: z.string(),
  product_name: z.string(),
  customer_name: z.string(),
  customer_tier: z.number(),
  ticket_id: z.number().nullable(),
  priority: z.string().nullable(),
  status: z.string(),
  owner_id: z.number().nullable(),
  owner_name: z.string().nullable(),
  staff_level: z.number().nullable(),
  required_level: z.number(),
  created_at: z.string(),
  solution: z.string(),
})
const message = z.object({
  id: z.number(),
  role: z.string(),
  content: z.string(),
  status: z.string(),
  created_at: z.string(),
  sources: z.array(
    z.object({ source_id: z.string(), title: z.string(), content: z.string() }),
  ),
})
const detail = card.extend({
  messages: z.array(message),
  has_older: z.boolean(),
  records: z.array(
    z.object({
      id: z.number(),
      kind: z.string(),
      content: z.string(),
      created_at: z.string(),
    }),
  ),
})
export type ServiceCard = z.infer<typeof card>
export type ServiceDetail = z.infer<typeof detail>
export const serviceProducts = (token: string) =>
  request(
    '/service/products',
    z.array(z.object({ id: z.number(), name: z.string() })),
    { token },
  )
export const serviceList = (token: string, page: number) =>
  request(
    `/service/conversations?page=${page}`,
    z.object({ items: z.array(card), has_more: z.boolean() }),
    { token },
  )
export const serviceDetail = (token: string, id: number, before?: number) =>
  request(
    `/service/conversations/${id}${before ? `?before=${before}` : ''}`,
    detail,
    { token },
  )
export const newService = (token: string, product_id: number, title: string) =>
  request('/service/conversations', card, {
    token,
    method: 'POST',
    body: { product_id, title },
  })
export const serviceAction = (
  token: string,
  id: number,
  action: string,
  body?: unknown,
) =>
  request(`/service/conversations/${id}/${action}`, z.unknown(), {
    token,
    method: 'POST',
    body,
    timeoutMs: action === 'ai' ? 160000 : 10000,
  })
