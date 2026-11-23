import { z } from 'zod'
import { request } from './http'
export const dashboardSchema = z.object({ total: z.number(),
  by_status: z.record(z.string(), z.number()), by_priority: z.record(z.string(), z.number()),
  resolution_samples: z.number(), average_resolution_hours: z.number().nullable() })
export function getDashboard(token: string, productId: number | null) {
  return request('/dashboard' + (productId === null ? '' : `?product_id=${productId}`), dashboardSchema, { token })
}
