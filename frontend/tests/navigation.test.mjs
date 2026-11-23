import test from 'node:test'
import assert from 'node:assert/strict'
import { staffNavigation, centerFor, centerTabs } from '../src/navigation.ts'

test('客服导航只保留四个入口，旧地址归入对应中心', () => {
  assert.deepEqual(staffNavigation.map(item => item.label), ['工单中心', '智能助手', '知识库', '管理中心'])
  for (const path of ['/service', '/tickets', '/tickets/12/edit']) assert.equal(centerFor(path), 'tickets')
  for (const path of ['/dashboard', '/admin', '/service/people', '/admin/imports', '/qa/evaluation', '/admin/ai-service']) assert.equal(centerFor(path), 'management')
  assert.equal(centerFor('/health'), null)
  assert.equal(centerFor('/qa'), null)
  assert.equal(centerFor('/service/products'), null)
})

test('管理标签不向普通客服提供基础管理入口', () => {
  assert.deepEqual(centerTabs('management', 'admin').map(tab => tab.label), ['数据统计', '人员管理', '基础资料', '历史导入', '回答评测', 'AI 服务'])
  assert.deepEqual(centerTabs('management', 'staff').map(tab => tab.label), ['数据统计', '人员管理', '回答评测'])
  assert.ok(centerTabs('management', 'admin').some(tab => tab.to === '/admin'))
  assert.ok(!centerTabs('management', 'staff').some(tab => tab.to === '/admin'))
  assert.deepEqual(centerTabs('management', 'customer'), [])
})
