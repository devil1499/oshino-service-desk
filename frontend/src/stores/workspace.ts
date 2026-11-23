import { defineStore } from 'pinia'
import { ref } from 'vue'
import { advanceTicket, appendRecord, createDemoArticles, createDemoTickets, createTicket } from '../demo/workspace'
import type { DemoTicket, KnowledgeArticle, TicketDraft, TicketStatus } from '../demo/workspace'

export const useWorkspaceStore = defineStore('workspace-demo', () => {
  // 演示数据只在内存中，不调用业务接口，也不持久化到浏览器。
  const tickets = ref(createDemoTickets())
  const articles = ref(createDemoArticles())
  const filters = ref({ keyword: '', status: 'all', priority: '', product: '', page: 1 })

  function findTicket(id: number): DemoTicket | undefined {
    return tickets.value.find(ticket => ticket.id === id)
  }

  function addTicket(input: TicketDraft, actor: string): DemoTicket {
    const id = Math.max(0, ...tickets.value.map(ticket => ticket.id)) + 1
    const ticket = createTicket(input, id, actor, new Date().toISOString())
    tickets.value.unshift(ticket)
    return ticket
  }

  function replace(updated: DemoTicket): void {
    const index = tickets.value.findIndex(ticket => ticket.id === updated.id)
    if (index < 0) throw new Error('演示工单不存在')
    tickets.value[index] = updated
  }

  function addRecord(id: number, content: string, actor: string): void {
    const ticket = findTicket(id)
    if (!ticket) throw new Error('演示工单不存在')
    replace(appendRecord(ticket, content, actor, new Date().toISOString()))
  }

  function advance(
    id: number, next: TicketStatus, actor: string,
    options: { solution?: string; replyConfirmed?: boolean } = {},
  ): void {
    const ticket = findTicket(id)
    if (!ticket) throw new Error('演示工单不存在')
    replace(advanceTicket(ticket, next, actor, new Date().toISOString(), options))
  }

  function addArticle(title: string, category: string, content: string): KnowledgeArticle {
    if (!title.trim() || title.trim().length > 200) throw new Error('文章标题应为 1～200 字')
    if (!content.trim() || content.length > 10000) throw new Error('文章正文应为 1～10000 字')
    const article: KnowledgeArticle = {
      id: Math.max(0, ...articles.value.map(item => item.id)) + 1, title: title.trim(), category,
      summary: content.trim().slice(0, 80), content: content.trim(), updatedAt: new Date().toISOString(), isDraft: true,
    }
    articles.value.unshift(article)
    return article
  }

  return { tickets, articles, filters, findTicket, addTicket, addRecord, advance, addArticle }
})
