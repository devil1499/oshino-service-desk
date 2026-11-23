import test from 'node:test'
import assert from 'node:assert/strict'
import { advanceTicket, appendRecord, createDemoTickets, createTicket, recentRecords, validateDraft } from '../src/demo/workspace.ts'

const now = '2026-10-23T06:00:00Z'
const draft = {
  title: '示例问题', description: '需要跟进的问题描述', customerName: '示例客户',
  customerEmail: 'customer@example.com', product: '云办公平台', module: '账号管理', category: '账号权限', priority: 'P2',
}

test('新建演示工单必须校验必填字段、产品模块和优先级', () => {
  assert.equal(validateDraft(draft), null)
  for (const invalid of [
    { title: ' ' }, { description: '' }, { customerName: '' }, { customerEmail: 'not-an-email' },
    { module: '接口集成' }, { product: '不存在' }, { category: '不存在' }, { priority: '' },
  ]) assert.ok(validateDraft({ ...draft, ...invalid }))
  const ticket = createTicket(draft, 27, '演示访客', now)
  assert.equal(ticket.number, 'D000027')
  assert.equal(ticket.status, 'pending')
  assert.equal(ticket.owner, '演示访客')
  assert.equal(ticket.records.length, 1)
})

test('工单只能按顺序推进，解决方案和回复确认不可省略', () => {
  const pending = createTicket(draft, 27, '示例客服', now)
  assert.throws(() => advanceTicket(pending, 'closed', '示例客服', now))
  const processing = advanceTicket(pending, 'processing', '示例客服', now)
  assert.throws(() => advanceTicket(processing, 'resolved', '示例客服', now))
  const resolved = advanceTicket(processing, 'resolved', '示例客服', now, { solution: '已核对并修正配置。' })
  assert.equal(resolved.solution, '已核对并修正配置。')
  assert.throws(() => advanceTicket(resolved, 'closed', '示例客服', now))
  const closed = advanceTicket(resolved, 'closed', '示例客服', now, { replyConfirmed: true })
  assert.equal(closed.status, 'closed')
  assert.equal(closed.records.length, 4)
  assert.throws(() => appendRecord(closed, '尝试修改关闭记录', '示例客服', now))
  assert.throws(() => advanceTicket(closed, 'processing', '示例客服', now))
})

test('追加处理记录不改原对象，空记录不能提交', () => {
  const ticket = createTicket(draft, 27, '示例客服', now)
  assert.throws(() => appendRecord(ticket, ' ', '示例客服', now))
  const updated = appendRecord(ticket, '已核对账号状态。', '示例客服', now)
  assert.equal(ticket.records.length, 1)
  assert.equal(updated.records.length, 2)
  assert.equal(updated.status, 'pending')
})

test('每次创建的示例数据互相隔离，并且时间、编号和状态有效', () => {
  const first = createDemoTickets()
  const second = createDemoTickets()
  assert.equal(first.length, 12)
  assert.equal(new Set(first.map(item => item.number)).size, 12)
  assert.ok(first.every(item => Number.isFinite(Date.parse(item.createdAt))))
  assert.ok(first.every(item => item.customerEmail.endsWith('@example.com')))
  first[0].records[0].content = '只改第一个示例空间'
  assert.notEqual(first[0].records[0].content, second[0].records[0].content)
  for (const item of second.filter(item => ['resolved', 'closed'].includes(item.status))) assert.ok(item.solution)
})

test('最近动态按实际时间排序，兼容 UTC 和带时区的时间', () => {
  const seed = createDemoTickets()
  const newer = createTicket(draft, 27, '演示访客', '2026-10-23T09:00:00Z')
  const rows = recentRecords([...seed, newer])
  assert.equal(rows[0].ticketId, 27)
  assert.equal(rows.length, 5)
})
