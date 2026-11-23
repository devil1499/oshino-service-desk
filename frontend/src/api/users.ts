import { z } from 'zod'
import { request, requestAll } from './http'
import { userSchema } from './models'

const loginSchema = z.object({
  access_token: z.string().min(1), token_type: z.literal('bearer'), user: userSchema,
})

export const login = (username: string, password: string) =>
  request('/auth/login', loginSchema, { method: 'POST', body: { username, password } })

export const getCurrentUser = (token: string) =>
  request('/auth/me', userSchema, { token })

export const listUsers = (token: string) =>
  requestAll('/users', userSchema, token)

export const createStaff = (token: string, body: { username: string; display_name: string; password: string }) =>
  request('/users', userSchema, { token, method: 'POST', body })

export const setStaffActive = (token: string, id: number, is_active: boolean) =>
  request(`/users/${id}`, userSchema, { token, method: 'PATCH', body: { is_active } })
