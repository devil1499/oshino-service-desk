import { z } from 'zod'
import { request } from './http'

export const documentSchema = z.object({
  id: z.number().int().positive(), title: z.string(), content: z.string(), source_name: z.string(),
  product_id: z.number().int().positive(), module_id: z.number().int().positive(), category_id: z.number().int().positive(),
  status: z.enum(['draft', 'published', 'disabled']), revision: z.number().int().positive(),
  chunk_count: z.number().int().nonnegative(), updated_at: z.string(),
})
export type KnowledgeDocument = z.infer<typeof documentSchema>
export type DocumentInput = Pick<KnowledgeDocument, 'title' | 'content' | 'product_id' | 'module_id' | 'category_id'>
const pageSchema = z.object({ items: z.array(documentSchema), total: z.number().int().nonnegative(), page: z.number().int().positive() })
const hitSchema = z.object({ document_id: z.number().int().positive(), chunk_id: z.number().int().positive(), title: z.string(),
  source_name: z.string(), chunk_order: z.number().int().positive(), content: z.string(), fingerprint: z.string(),
  score: z.number(), scope: z.enum(['module', 'category']) })
export const knowledgeResultSchema = z.object({ items: z.array(hitSchema), expanded: z.boolean(),
  stale_count: z.number().int().nonnegative(), indexed_at: z.string() })

export function listKnowledge(token: string, page: number, q = '', status = '') {
  const query = new URLSearchParams({ page: String(page) })
  if (q) query.set('q', q)
  if (status) query.set('status', status)
  return request(`/knowledge?${query}`, pageSchema, { token })
}
export function getKnowledge(token: string, id: number) {
  return request(`/knowledge/${id}`, documentSchema, { token })
}
export function saveKnowledge(token: string, body: DocumentInput, id?: number) {
  return request(id ? `/knowledge/${id}/content` : '/knowledge', documentSchema,
    { token, method: id ? 'PUT' : 'POST', body })
}
export function uploadKnowledge(token: string, body: DocumentInput, file: File) {
  const form = new FormData()
  form.append('file', file)
  form.append('title', body.title)
  form.append('product_id', String(body.product_id))
  form.append('module_id', String(body.module_id))
  form.append('category_id', String(body.category_id))
  return request('/knowledge/upload', documentSchema, { token, method: 'POST', body: form, timeoutMs: 200000 })
}
export function changeKnowledge(token: string, id: number, action: 'publish' | 'disable') {
  return request(`/knowledge/${id}/${action}`, documentSchema, { token, method: 'POST' })
}
export function searchKnowledge(token: string, ticketId: number) {
  return request(`/tickets/${ticketId}/knowledge`, knowledgeResultSchema,
    { token, method: 'POST', timeoutMs: 60000 })
}
