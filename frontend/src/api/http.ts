import { z } from 'zod'

const errorSchema = z.object({
  detail: z.union([
    z.string(),
    z.array(
      z.object({
        loc: z.array(z.union([z.string(), z.number()])),
        msg: z.string(),
      }),
    ),
  ]),
})

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

interface RequestOptions {
  token?: string
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH'
  body?: unknown
  timeoutMs?: number
}

// 登录、配置、工单都需要 JSON 请求、错误展示和超时，因此在此复用。
export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  const headers = new Headers()
  if (options.token) headers.set('Authorization', `Bearer ${options.token}`)
  const body = options.body
  const isFileUpload = body instanceof FormData
  // 上传时由浏览器填写 multipart 边界，不能手动设置 JSON 请求头。
  if (options.body !== undefined && !isFileUpload) headers.set('Content-Type', 'application/json')

  const response = await fetch('/api' + path, {
    method: options.method ?? 'GET',
    headers,
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(options.timeoutMs ?? 10000),
  })

  if (!response.ok) {
    let message = `请求失败：HTTP ${response.status}`
    // FastAPI 的业务/校验错误是 JSON；未处理的服务端异常可能只有文本。
    if (response.headers.get('content-type')?.includes('application/json')) {
      const { detail } = errorSchema.parse(await response.json())
      message =
        typeof detail === 'string'
          ? detail
          : detail.map((issue) => `${issue.loc.join('.')}: ${issue.msg}`).join('；')
    }
    throw new ApiError(response.status, message)
  }

  return schema.parse(await response.json())
}

// 保持教程中的数组契约，分批读取以免配置超过一页时被静默截断。
export async function requestAll<T>(
  path: string,
  schema: z.ZodType<T>,
  token: string,
): Promise<T[]> {
  const rows: T[] = []
  for (let page = 1; ; page += 1) {
    const batch = await request(`${path}?page=${page}&page_size=100`, z.array(schema), { token })
    rows.push(...batch)
    if (batch.length < 100) return rows
  }
}
