import { z } from 'zod'
import { request } from './http'
import { listUsers } from './users'

const customerSchema = z.object({
  id: z.number(),
  name: z.string(),
  role: z.enum(['customer', 'staff', 'admin']),
  tier: z.number(),
  level: z.number(),
})
const peoplePageSchema = z.object({
  items: z.array(customerSchema),
  has_more: z.boolean(),
})

export interface Person {
  id: number
  name: string
  username: string | null
  role: 'customer' | 'staff' | 'admin'
  tier: number
  level: number
  is_active: boolean
}

export async function listPeople(token: string): Promise<Person[]> {
  // 人员目录仅返回启用账号；客服管理接口另含停用账号，两者按角色合并。
  const staff = await listUsers(token)
  const people: Person[] = staff.map((user) => ({
    id: user.id,
    name: user.display_name,
    username: user.username,
    role: user.role,
    tier: user.customer_tier,
    level: user.staff_level,
    is_active: user.is_active,
  }))
  for (let page = 1; ; page += 1) {
    const result = await request(
      `/service/people?page=${page}`,
      peoplePageSchema,
      { token },
    )
    people.push(
      ...result.items
        .filter((person) => person.role === 'customer')
        .map((person) => ({
          ...person,
          username: null,
          is_active: true,
        })),
    )
    if (!result.has_more) return people
  }
}
