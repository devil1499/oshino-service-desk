import { z } from 'zod'
import { request } from './http'

const similarResult = z.object({
  items: z.array(z.object({
    id: z.number().int(), number: z.string(), title: z.string(), solution: z.string(),
    module_id: z.number().int(), score: z.number(), scope: z.enum(['module', 'category']),
  })),
  expanded: z.boolean(), stale_count: z.number().int(), indexed_at: z.string(),
})

export function findSimilarCases(token: string, ticketId: number) {
  return request(`/tickets/${ticketId}/similar`, similarResult, { token, method: 'POST', timeoutMs: 60000 })
}
