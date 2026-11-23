import { request } from './http'
import { ticketDetailSchema, ticketPageSchema } from './models'
import type { Ticket, TicketInput } from './models'

export interface TicketFilters {
  page: number
  keyword?: string
  status?: Ticket['status']
  priority?: Ticket['priority']
  product_id?: number
  module_id?: number
  category_id?: number
  owner_id?: number
  imported_only?: boolean
}

export function listTickets(token: string, filters: TicketFilters) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  return request('/tickets?' + query.toString(), ticketPageSchema, { token })
}

export const getTicket = (token: string, id: number) =>
  request(`/tickets/${id}`, ticketDetailSchema, { token })

export const createTicket = (token: string, body: TicketInput) =>
  request('/tickets', ticketDetailSchema, { token, method: 'POST', body })

export const updateTicket = (token: string, id: number, body: TicketInput & { owner_id: number }) =>
  request(`/tickets/${id}`, ticketDetailSchema, { token, method: 'PATCH', body })

export const startTicket = (token: string, id: number) =>
  request(`/tickets/${id}/start`, ticketDetailSchema, { token, method: 'POST' })

export const addNote = (token: string, id: number, content: string) =>
  request(`/tickets/${id}/records`, ticketDetailSchema, {
    token,
    method: 'POST',
    body: { content },
  })

export const resolveTicket = (token: string, id: number, solution: string) =>
  request(`/tickets/${id}/resolve`, ticketDetailSchema, {
    token,
    method: 'POST',
    body: { solution },
  })

export const closeTicket = (token: string, id: number) =>
  request(`/tickets/${id}/close`, ticketDetailSchema, {
    token,
    method: 'POST',
    body: { customer_reply_confirmed: true },
  })
