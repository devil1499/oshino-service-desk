import { z } from 'zod'
import { request } from './http'

const stepSchema = z.object({ instruction: z.string(), source_ids: z.array(z.string()) })
const draftSchema = z.object({ summary: z.string(), diagnosis: z.string(), category_id: z.number(),
  priority: z.enum(['P1', 'P2', 'P3', 'P4']), reason: z.string(), steps: z.array(stepSchema),
  risks: z.array(z.string()), confirmations: z.array(z.string()), reply_subject: z.string(), reply_body: z.string() })
const sourceSchema = z.object({ source_id: z.string(), kind: z.enum(['ticket', 'knowledge']),
  entity_id: z.number(), title: z.string(), content: z.string(), fingerprint: z.string() })
export const assistanceSchema = z.object({ id: z.number(), ticket_id: z.number(), draft: draftSchema,
  sources: z.array(sourceSchema), model: z.string(), prompt_version: z.string(), duration_ms: z.number(),
  created_at: z.string(), adopted_at: z.string().nullable(), final_solution: z.string().nullable(), final_reply: z.string().nullable() })
export type Assistance = z.infer<typeof assistanceSchema>
export function generateAssistance(token: string, ticketId: number) {
  return request(`/tickets/${ticketId}/assist`, assistanceSchema, { token, method: 'POST', timeoutMs: 180000 })
}
export function listAssistance(token: string, ticketId: number, page: number) {
  return request(`/tickets/${ticketId}/assistance?page=${page}`, z.array(assistanceSchema), { token })
}
export function adoptAssistance(token: string, ticketId: number, runId: number, solution: string, reply: string) {
  return request(`/tickets/${ticketId}/assistance/${runId}/adopt`, assistanceSchema,
    { token, method: 'POST', body: { confirmed: true, solution, reply } })
}
