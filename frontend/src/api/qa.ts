import { z } from "zod";
import { request } from "./http";

const knowledgeSourceSchema = z.object({
  source_id: z.string(),
  document_id: z.number().int().positive(),
  chunk_id: z.number().int().positive(),
  title: z.string(),
  content: z.string(),
  fingerprint: z.string(),
});
const sourceSchema = z.union([
  z.object({
    kind: z.literal("web"),
    source_id: z.string(),
    title: z.string(),
    content: z.string(),
    url: z.string().url(),
    retrieved_at: z.string(),
  }),
  knowledgeSourceSchema,
]);
const conversationSchema = z.object({
  id: z.number().int().positive(),
  product_id: z.number().int().positive(),
  title: z.string(),
  created_at: z.string(),
});
const tokenCountSchema = z.number().int().nonnegative().nullable();
const tokenUsageSchema = z.object({
  input_tokens: tokenCountSchema,
  output_tokens: tokenCountSchema,
  total_tokens: tokenCountSchema,
  complete: z.boolean(),
  calls: z.number().int().nonnegative(),
  known_calls: z.number().int().nonnegative(),
});
const messageSchema = z.object({
  id: z.number().int().positive(),
  request_id: z.string(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  status: z.enum([
    "submitted",
    "running",
    "answered",
    "clarification",
    "insufficient",
    "failed",
  ]),
  sources: z.array(sourceSchema),
  web_search: z.boolean().default(false),
  error_code: z.string().nullable(),
  created_at: z.string(),
  duration_ms: z.number().int().nonnegative().nullable(),
  model: z.string().nullable(),
  prompt_version: z.string().nullable(),
  has_run: z.boolean(),
  token_usage: tokenUsageSchema.nullable(),
});
const snapshotSchema = z.record(z.string(), z.unknown());
const runSchema = z.object({
  schema_version: z.literal(1),
  started_at: z.string(),
  status: z.string(),
  duration_ms: z.number().int().nonnegative().nullable(),
  model: z.string(),
  prompt_version: z.string(),
  question: z.object({
    text: z.string(),
    product_id: z.number().int().positive(),
    web_search: z.boolean().default(false),
    history: z.array(
      z.object({ role: z.enum(["user", "assistant"]), content: z.string() }),
    ),
  }),
  steps: z.array(
    z.object({
      name: z.string(),
      status: z.string(),
      duration_ms: z.number().int().nonnegative().nullable(),
      input: snapshotSchema,
      output: z
        .object({ sources: z.array(sourceSchema).optional() })
        .catchall(z.unknown())
        .nullable(),
      error: z.string().nullable(),
    }),
  ),
  calls: z.array(
    z.object({
      kind: z.enum(["chat", "embedding"]),
      model: z.string(),
      status: z.string(),
      duration_ms: z.number().int().nonnegative().nullable(),
      request: snapshotSchema.nullable(),
      response: snapshotSchema.nullable(),
      usage: z
        .object({
          input_tokens: tokenCountSchema,
          output_tokens: tokenCountSchema,
          total_tokens: tokenCountSchema,
        })
        .nullable(),
      error: z.string().nullable(),
    }),
  ),
  usage: z.object({ chat: tokenUsageSchema, embedding: tokenUsageSchema }),
  sources: z.array(sourceSchema),
  error: z.string().nullable(),
});
const conversationPageSchema = z.object({
  items: z.array(conversationSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
});
const messagePageSchema = z.object({
  items: z.array(messageSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
});

export type QaConversation = z.infer<typeof conversationSchema>;
export type QaMessage = z.infer<typeof messageSchema>;
export type QaRun = z.infer<typeof runSchema>;

export function getRun(
  token: string,
  conversationId: number,
  messageId: number,
) {
  return request(
    `/qa/conversations/${conversationId}/messages/${messageId}/run`,
    runSchema,
    { token },
  );
}

export function createConversation(
  token: string,
  body: { product_id: number; title: string },
) {
  return request("/qa/conversations", conversationSchema, {
    token,
    method: "POST",
    body,
  });
}

export function listConversations(token: string, page = 1) {
  return request(`/qa/conversations?page=${page}`, conversationPageSchema, {
    token,
  });
}

export function listMessages(token: string, conversationId: number, page = 1) {
  return request(
    `/qa/conversations/${conversationId}/messages?page=${page}&page_size=100`,
    messagePageSchema,
    { token },
  );
}

export function sendMessage(
  token: string,
  conversationId: number,
  body: { request_id: string; text: string; web_search?: boolean },
) {
  return request(
    `/qa/conversations/${conversationId}/messages`,
    messageSchema,
    { token, method: "POST", body, timeoutMs: 160000 },
  );
}
