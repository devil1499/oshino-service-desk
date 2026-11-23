import { z } from 'zod'
import { request } from './http'

export const emailSchema = z.object({
  id: z.number().int().positive(),
  request_id: z.string(),
  recipient: z.string(),
  subject: z.string(),
  content: z.string(),
  assistance_id: z.number().int().positive().nullable(),
  message_id: z.string(),
  status: z.enum(['sending', 'accepted', 'failed', 'unknown']),
  error: z.string().nullable(),
  created_at: z.string(),
  finished_at: z.string().nullable(),
})

export type EmailRecord = z.infer<typeof emailSchema>

export interface EmailInput {
  request_id: string
  recipient: string
  subject: string
  content: string
  confirmed: true
  assistance_id: number | null
}

export function sendEmail(token: string, ticketId: number, body: EmailInput) {
  return request(`/tickets/${ticketId}/emails`, emailSchema, {
    token,
    method: 'POST',
    body,
    timeoutMs: 120000,
  })
}

export function listEmails(token: string, ticketId: number, page: number) {
  return request(`/tickets/${ticketId}/emails?page=${page}`, z.array(emailSchema), { token })
}
