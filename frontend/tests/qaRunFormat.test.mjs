import test from 'node:test'
import assert from 'node:assert/strict'
import {
  formatRunDuration,
  formatTokenUsage,
} from '../src/utils/qaRunFormat.ts'

test('问答用量区分未知、不完整的已知用量和没有调用', () => {
  assert.equal(formatTokenUsage(null), '未知')
  assert.equal(
    formatTokenUsage({ total_tokens: null, complete: false, calls: 1 }),
    '未知（统计不完整）',
  )
  assert.equal(
    formatTokenUsage({ total_tokens: 136, complete: false, calls: 2 }),
    '已知 136（统计不完整）',
  )
  assert.equal(
    formatTokenUsage({ total_tokens: 136, complete: true, calls: 2 }),
    '136',
  )
  assert.equal(
    formatTokenUsage({ total_tokens: 0, complete: true, calls: 0 }),
    '0（未调用）',
  )
})

test('历史缺失耗时不能显示为零，真实零耗时正常展示', () => {
  assert.equal(formatRunDuration(null), '未记录')
  assert.equal(formatRunDuration(0), '0 毫秒')
  assert.equal(formatRunDuration(45), '45 毫秒')
  assert.equal(formatRunDuration(1234), '1.23 秒')
})
