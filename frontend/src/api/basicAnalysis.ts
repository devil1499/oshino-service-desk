import { z } from 'zod'
import { request } from './http'

const resultSchema = z.object({
  summary: z.string(),
  category_id: z.number().int().positive(),
  priority: z.enum(['P1', 'P2', 'P3', 'P4']),
  reason: z.string(),
})

export const analysisSchema = z.object({
  status: z.enum(['not_started', 'pending', 'running', 'completed', 'failed']),
  attempt: z.number().int().nonnegative(),
  result: resultSchema.nullable(),
  error: z.string().nullable(),
  model: z.string().nullable(),
  stale: z.boolean(),
  adopted_at: z.string().nullable(),
})

export function getAnalysis(token: string, ticketId: number) {
  return request(`/tickets/${ticketId}/analysis`, analysisSchema, { token })
}

export function startAnalysis(token: string, ticketId: number) {
  return request(`/tickets/${ticketId}/analysis`, z.object({ status: z.literal('pending') }), {
    token,
    method: 'POST',
  })
}

export function adoptAnalysis(token: string, ticketId: number) {
  return request(`/tickets/${ticketId}/analysis/adopt`, z.object({ status: z.literal('adopted') }), {
    token,
    method: 'POST',
    body: { confirmed: true },
  })
}
