export const staffNavigation = [
  { to: '/service', label: '工单中心', icon: 'ticket' },
  { to: '/qa', label: '智能助手', icon: 'assistant' },
  { to: '/knowledge', label: '知识库', icon: 'book' },
  { to: '/dashboard', label: '管理中心', icon: 'settings' },
] as const

export function centerFor(path: string): 'tickets' | 'management' | null {
  if (
    path === '/service' ||
    path === '/tickets' ||
    path.startsWith('/tickets/')
  )
    return 'tickets'
  if (
    ['/dashboard', '/admin', '/admin/imports', '/service/people', '/qa/evaluation', '/admin/ai-service'].includes(path)
  )
    return 'management'
  return null
}

export function centerTabs(center: ReturnType<typeof centerFor>, role: string) {
  if (role === 'customer') return []
  if (center === 'tickets')
    return [
      { to: '/service', label: '接单与处理' },
      { to: '/tickets', label: '全部工单' },
    ]
  if (center !== 'management') return []
  const tabs = [
    { to: '/dashboard', label: '数据统计' },
    { to: '/service/people', label: '人员管理' },
  ]
  if (role === 'admin')
    tabs.push(
      { to: '/admin', label: '基础资料' },
      { to: '/admin/imports', label: '历史导入' },
    )
  tabs.push({ to: '/qa/evaluation', label: '回答评测' })
  if (role === 'admin') tabs.push({ to: '/admin/ai-service', label: 'AI 服务' })
  return tabs
}
