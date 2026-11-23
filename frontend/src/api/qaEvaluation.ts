import { z } from 'zod'
import { request } from './http'

const sourceSchema = z.object({
  source_id: z.string(),
  document_id: z.number(),
  chunk_id: z.number(),
  title: z.string(),
  content: z.string(),
  fingerprint: z.string(),
})
export const evaluationCaseInput = z.object({
  id: z.string().min(1).max(50),
  category: z.string().min(1).max(50),
  question: z.string().min(1).max(2000),
  history: z
    .array(
      z.object({ role: z.enum(['user', 'assistant']), content: z.string() }),
    )
    .max(12)
    .default([]),
  required_points: z.array(z.string().min(1)).min(1).max(20),
  expected_behavior: z.enum(['answered', 'clarification', 'insufficient']),
  expected_chunk_ids: z.array(z.number().int().positive()).max(10).default([]),
  forbidden: z.array(z.string()).max(10).default([]),
})
const caseSchema = evaluationCaseInput.extend({
  references: z.array(sourceSchema),
  knowledge_scope: z.record(z.string(), z.string()),
})
const reviewSchema = z.object({
  correctness: z.number(),
  covered_points: z.array(z.number()),
  citation_support: z.number().nullable(),
  note: z.string(),
  reviewer_id: z.number(),
  reviewed_at: z.string(),
})
const resultSchema = z.object({
  case_index: z.number(),
  case_id: z.string(),
  conversation_id: z.number().nullable(),
  message_id: z.number().nullable(),
  expected_behavior: z.string(),
  status: z.string(),
  answer: z.string(),
  sources: z.array(sourceSchema),
  duration_ms: z.number().nullable(),
  error: z.string().nullable(),
  review: reviewSchema.nullable(),
  retrieval_recall: z.number().nullable(),
  retrieval_hit: z.boolean().nullable(),
  point_count: z.number(),
  token_usage: z
    .object({
      input_tokens: z.number().nullable(),
      output_tokens: z.number().nullable(),
      total_tokens: z.number().nullable(),
      complete: z.boolean(),
      calls: z.number(),
      known_calls: z.number(),
    })
    .nullable(),
})
const metricsSchema = z.object({
  finished: z.number(),
  failed: z.number(),
  reviewed: z.number(),
  correctness: z.number().nullable(),
  completeness: z.number().nullable(),
  citation_support: z.number().nullable(),
  citation_samples: z.number(),
  behavior_match: z.number().nullable(),
  behavior_samples: z.number(),
  retrieval_recall: z.number().nullable(),
  retrieval_hit: z.number().nullable(),
  retrieval_samples: z.number(),
})
const summarySchema = z.object({
  id: z.number(),
  product_id: z.number(),
  title: z.string(),
  suite_version: z.string(),
  suite_signature: z.string(),
  created_at: z.string(),
  state: z.enum(['ready', 'running', 'completed']),
  case_count: z.number(),
  processed: z.number(),
  metrics: metricsSchema,
})
const runSchema = summarySchema.extend({
  cases: z.array(caseSchema),
  results: z.array(resultSchema),
})
const listSchema = z.object({
  items: z.array(summarySchema),
  total: z.number(),
  page: z.number(),
})
export type EvaluationRun = z.infer<typeof runSchema>
export type EvaluationSummary = z.infer<typeof summarySchema>
export type EvaluationCaseInput = z.infer<typeof evaluationCaseInput>
export type EvaluationReview = Pick<
  z.infer<typeof reviewSchema>,
  'correctness' | 'covered_points' | 'citation_support' | 'note'
>

export const listEvaluations = (token: string, page = 1) =>
  request(`/qa/evaluations/runs?page=${page}`, listSchema, { token })
export const getEvaluation = (token: string, id: number) =>
  request(`/qa/evaluations/runs/${id}`, runSchema, { token })
export const createEvaluation = (
  token: string,
  body: { product_id: number; title: string; cases?: EvaluationCaseInput[] },
) => request('/qa/evaluations/runs', runSchema, { token, method: 'POST', body })
export const runNextCase = (token: string, id: number) =>
  request(`/qa/evaluations/runs/${id}/next`, runSchema, {
    token,
    method: 'POST',
    timeoutMs: 165000,
  })
export const saveReview = (
  token: string,
  id: number,
  index: number,
  body: EvaluationReview,
) =>
  request(`/qa/evaluations/runs/${id}/reviews/${index}`, runSchema, {
    token,
    method: 'PUT',
    body,
  })
export const listEvaluationReferences = (
  token: string,
  productId: number,
  page = 1,
) =>
  request(
    `/qa/evaluations/references?product_id=${productId}&page=${page}`,
    z.object({
      items: z.array(sourceSchema),
      page: z.number(),
      has_more: z.boolean(),
    }),
    { token },
  )
