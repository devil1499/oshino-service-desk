import { z } from 'zod'

export const userSchema = z.object({
  id: z.number().int().positive(),
  username: z.string(),
  display_name: z.string(),
  role: z.enum(['admin', 'staff', 'customer']),
  customer_tier: z.number().int().min(1).max(4),
  staff_level: z.number().int().min(1).max(3),
  is_active: z.boolean(),
})
export type User = z.infer<typeof userSchema>

export const namedSchema = z.object({
  id: z.number().int().positive(),
  name: z.string(),
  is_active: z.boolean(),
})
export const moduleSchema = namedSchema.extend({ product_id: z.number().int().positive() })
export type NamedItem = z.infer<typeof namedSchema>
export type ProductModule = z.infer<typeof moduleSchema>

export const prioritySchema = z.enum(['P1', 'P2', 'P3', 'P4'])
export const statusSchema = z.enum(['pending', 'processing', 'resolved', 'closed'])
export const statusLabels: Record<z.infer<typeof statusSchema>, string> = {
  pending: '待处理', processing: '处理中', resolved: '已解决', closed: '已关闭',
}

export const ticketSchema = z.object({
  id: z.number().int().positive(),
  number: z.string(),
  title: z.string(),
  description: z.string(),
  customer_name: z.string(),
  customer_email: z.string(),
  product_id: z.number().int().positive(),
  module_id: z.number().int().positive(),
  category_id: z.number().int().positive(),
  owner_id: z.number().int().positive().nullable(),
  priority: prioritySchema,
  status: statusSchema,
  solution: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})
export const ticketDetailSchema = ticketSchema.extend({
  records: z.array(z.object({
    id: z.number().int().positive(), author_id: z.number().int().positive(),
    kind: z.string(), content: z.string(), created_at: z.string(),
  })),
})
export const ticketPageSchema = z.object({
  items: z.array(ticketSchema), total: z.number().int().nonnegative(),
  page: z.number().int().positive(), page_size: z.number().int().positive(),
})
export type Ticket = z.infer<typeof ticketSchema>
export type TicketDetail = z.infer<typeof ticketDetailSchema>
export type TicketInput = Pick<Ticket,
  'title' | 'description' | 'customer_name' | 'customer_email' |
  'product_id' | 'module_id' | 'category_id' | 'priority'
>
