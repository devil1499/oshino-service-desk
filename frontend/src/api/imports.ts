import { z } from 'zod'
import { request } from './http'

const importResult = z.object({ imported: z.number().int(), ticket_ids: z.array(z.number().int()) })

export function importTickets(token: string, file: File) {
  const body = new FormData()
  body.append('file', file)
  return request('/tickets/import', importResult, { token, method: 'POST', body, timeoutMs: 30000 })
}
