export function formatRunDuration(milliseconds: number | null): string {
  if (milliseconds === null) return '未记录'
  return milliseconds < 1000
    ? `${milliseconds} 毫秒`
    : `${(milliseconds / 1000).toFixed(2)} 秒`
}

export function formatTokenUsage(
  usage: {
    total_tokens: number | null
    complete: boolean
    calls: number
  } | null,
): string {
  if (usage === null) return '未知'
  if (usage.total_tokens === null)
    return usage.complete ? '未知' : '未知（统计不完整）'
  if (!usage.complete)
    return `已知 ${usage.total_tokens.toLocaleString()}（统计不完整）`
  if (usage.calls === 0) return '0（未调用）'
  return usage.total_tokens.toLocaleString()
}
