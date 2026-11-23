export interface HealthResponse {
  status: 'ok'
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/health', {
    signal: AbortSignal.timeout(5000),
  })

  if (!response.ok) {
    throw new Error(`健康检查请求失败：HTTP ${response.status}`)
  }

  const data: unknown = await response.json()

  if (
    typeof data !== 'object' ||
    data === null ||
    !('status' in data) ||
    data.status !== 'ok'
  ) {
    throw new Error('健康检查响应不符合约定，应返回 {"status":"ok"}')
  }

  return { status: data.status }
}
