export type TicketStatus = 'pending' | 'processing' | 'resolved' | 'closed'
export type TicketPriority = 'P1' | 'P2' | 'P3' | 'P4'
export const statusLabels: Record<TicketStatus, string> = {
  pending: '待处理', processing: '处理中', resolved: '已解决', closed: '已关闭',
}
export const priorities: TicketPriority[] = ['P1', 'P2', 'P3', 'P4']
export const statuses = Object.keys(statusLabels) as TicketStatus[]
export const demoProducts = ['云办公平台', '云账本', '开放平台']
export const demoCategories = ['账号权限', '计费订阅', '功能使用', '配置集成', '性能故障', '数据问题']
export const demoModules: Record<string, string[]> = {
  云办公平台: ['账号管理', '报表中心', '审批协作'],
  云账本: ['订阅管理', '支付结算'],
  开放平台: ['接口集成', '消息通知'],
}

export interface TicketRecord {
  id: string
  actor: string
  content: string
  createdAt: string
}

export interface TicketDraft {
  title: string
  description: string
  customerName: string
  customerEmail: string
  product: string
  module: string
  category: string
  priority: TicketPriority | ''
}

export interface DemoTicket extends Omit<TicketDraft, 'priority'> {
  id: number
  number: string
  priority: TicketPriority
  status: TicketStatus
  owner: string
  createdAt: string
  updatedAt: string
  solution: string
  records: TicketRecord[]
}

export interface KnowledgeArticle {
  id: number
  title: string
  category: string
  summary: string
  content: string
  updatedAt: string
  isDraft: boolean
}

export function recentRecords(tickets: DemoTicket[], limit = 5): (TicketRecord & { number: string; ticketId: number })[] {
  return tickets.flatMap(ticket => ticket.records.map(record => ({
    ...record, number: ticket.number, ticketId: ticket.id,
  }))).sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt)).slice(0, limit)
}

export function validateDraft(input: TicketDraft): string | null {
  if (!input.title.trim() || input.title.trim().length > 200) return '工单标题应为 1～200 字'
  if (!input.description.trim() || input.description.trim().length > 10000) return '问题描述应为 1～10000 字'
  if (!input.customerName.trim() || input.customerName.trim().length > 100) return '客户姓名应为 1～100 字'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input.customerEmail) || input.customerEmail.length > 254) {
    return '请填写有效的客户邮箱'
  }
  if (!demoModules[input.product]?.includes(input.module)) return '请选择产品及对应模块'
  if (!demoCategories.includes(input.category)) return '请选择问题分类'
  if (!priorities.includes(input.priority as TicketPriority)) return '请选择优先级'
  return null
}

export function createTicket(input: TicketDraft, id: number, actor: string, now: string): DemoTicket {
  const error = validateDraft(input)
  if (error) throw new Error(error)
  return {
    ...input, title: input.title.trim(), description: input.description.trim(), customerName: input.customerName.trim(),
    id, number: `D${String(id).padStart(6, '0')}`, priority: input.priority as TicketPriority,
    status: 'pending', owner: actor, createdAt: now, updatedAt: now, solution: '',
    records: [{ id: `${id}-created`, actor, content: '创建了演示工单，等待处理。', createdAt: now }],
  }
}

export function appendRecord(ticket: DemoTicket, content: string, actor: string, now: string): DemoTicket {
  if (ticket.status === 'closed') throw new Error('已关闭的工单只允许查看')
  if (!content.trim() || content.trim().length > 10000) throw new Error('处理记录应为 1～10000 字')
  return {
    ...ticket, updatedAt: now,
    records: [...ticket.records, { id: `${ticket.id}-${ticket.records.length}`, actor, content: content.trim(), createdAt: now }],
  }
}

export function advanceTicket(
  ticket: DemoTicket, next: TicketStatus, actor: string, now: string,
  options: { solution?: string; replyConfirmed?: boolean } = {},
): DemoTicket {
  const transitions: Partial<Record<TicketStatus, TicketStatus>> = {
    pending: 'processing', processing: 'resolved', resolved: 'closed',
  }
  if (transitions[ticket.status] !== next) throw new Error('请按待处理、处理中、已解决、已关闭的顺序操作')
  const solution = options.solution?.trim() ?? ''
  if (next === 'resolved' && (!solution || solution.length > 10000)) throw new Error('解决方案应为 1～10000 字')
  if (next === 'closed' && !options.replyConfirmed) throw new Error('请先确认已完成模拟客户回复')
  const content = next === 'resolved' ? `保存了解决方案：${solution}` : `将演示工单标记为${statusLabels[next]}。`
  const updated = appendRecord(ticket, content, actor, now)
  return { ...updated, status: next, solution: next === 'resolved' ? solution : ticket.solution }
}

export function createDemoTickets(): DemoTicket[] {
  const seeds: [string, string, TicketPriority, TicketStatus, number, string][] = [
    ['登录失败，提示 E401', '林女士', 'P1', 'pending', 0, '账号权限'],
    ['月度报表导出后数据不完整', '陈先生', 'P2', 'processing', 0, '数据问题'],
    ['订阅续费后仍提示套餐已到期', '张女士', 'P2', 'pending', 1, '计费订阅'],
    ['Webhook 回调偶发超时', '王先生', 'P1', 'processing', 2, '配置集成'],
    ['新成员无法查看审批记录', '李女士', 'P3', 'pending', 0, '账号权限'],
    ['支付成功后未收到确认通知', '周先生', 'P2', 'resolved', 1, '功能使用'],
    ['开放接口返回请求频率过高', '刘先生', 'P3', 'pending', 2, '性能故障'],
    ['希望支持批量导出审批附件', '赵女士', 'P4', 'pending', 0, '功能使用'],
    ['工作台首屏加载缓慢', '孙先生', 'P3', 'processing', 0, '性能故障'],
    ['重复扣款的核对与退款', '吴女士', 'P1', 'resolved', 1, '计费订阅'],
    ['账号角色调整后权限未更新', '郑先生', 'P3', 'closed', 0, '账号权限'],
    ['API 签名校验失败', '何女士', 'P2', 'closed', 2, '配置集成'],
  ]
  return seeds.map(([title, customerName, priority, status, productIndex, category], index) => {
    const id = 26 - index
    const product = demoProducts[productIndex]!
    const module = demoModules[product]![0]!
    const now = `2026-10-23T${String(10 - Math.floor(index / 6)).padStart(2, '0')}:${String(50 - index * 3).padStart(2, '0')}:00+08:00`
    const ticket = createTicket({
      title, customerName, customerEmail: `customer${index + 1}@example.com`, product, module, category, priority,
      description: index === 0
        ? '客户在登录工作台时收到 E401 提示，重置密码后仍无法进入系统。其他同事可以正常登录。请协助核对账号状态、角色绑定及权限配置。'
        : `客户反馈“${title}”。已收集问题现象，等待进一步核对复现步骤与相关配置。此内容为前端演示示例。`,
    }, id, index % 2 ? '示例客服 · 陈' : '示例客服 · 林', now)
    if (status === 'pending') return ticket
    let updated = advanceTicket(ticket, 'processing', ticket.owner, now)
    if (status === 'processing') return updated
    updated = advanceTicket(updated, 'resolved', ticket.owner, now, { solution: '核对配置并修正后，模拟问题已恢复正常。' })
    return status === 'resolved' ? updated : advanceTicket(updated, 'closed', ticket.owner, now, { replyConfirmed: true })
  })
}

export function createDemoArticles(): KnowledgeArticle[] {
  return [
    ['登录出现 E401，如何排查？', '账号权限', '从账号状态、角色配置和登录凭证三个方面逐步定位。',
      '适用场景\n账号可以输入密码，但登录后提示 E401 或无访问权限。\n\n排查步骤\n1. 确认账号仍为启用状态。\n2. 检查角色与产品权限是否正确绑定。\n3. 退出当前会话，重新登录以获取新凭证。\n4. 若仍失败，记录错误时间和请求编号，交由管理员核查。\n\n注意事项\n不要在处理记录中粘贴密码、完整令牌或客户敏感信息。'],
    ['报表导出缺少部分数据', '数据问题', '核对筛选条件、日期范围和数据权限，避免遗漏统计口径。',
      '排查步骤\n1. 对照页面筛选条件和导出日期范围。\n2. 核对当前账号可见的数据范围。\n3. 使用一条已知记录检查是否被过滤。\n4. 记录筛选条件和缺失的记录编号，交由相关人员复核。'],
    ['订阅支付与重复扣款核对', '计费订阅', '区分订单状态和实际支付结果，以交易记录为准核对。',
      '处理建议\n先核对订单编号、交易时间及支付渠道，再比对交易记录。\n\n发现疑似重复支付时，应交由有权限的财务人员核对。不要仅根据页面提示承诺退款结果。'],
    ['Webhook 集成检查清单', '配置集成', '检查回调地址、签名配置和接收服务的响应状态。',
      '排查步骤\n1. 核对回调地址与使用环境。\n2. 对照双方约定检查签名算法和时间戳。\n3. 检查接收端是否及时返回成功状态。\n4. 记录失败请求编号，在确认幂等性后再考虑重新发送。'],
  ].map(([title, category, summary, content], index) => ({
    id: index + 1, title: title!, category: category!, summary: summary!, content: content!,
    updatedAt: '2026-10-23T09:00:00+08:00', isDraft: false,
  }))
}
