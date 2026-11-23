import { z } from "zod";
import { request } from "./http";

const settingsSchema = z.object({
  chat_base_url: z.string(),
  chat_model: z.string(),
  chat_key_configured: z.boolean(),
  search_key_configured: z.boolean(),
  search_enabled: z.boolean(),
  search_reuse_chat_key: z.boolean(),
});
export type AiSettings = z.infer<typeof settingsSchema>;
export type AiSettingsInput = Pick<
  AiSettings,
  "chat_base_url" | "chat_model" | "search_enabled" | "search_reuse_chat_key"
> & {
  chat_api_key: string;
  search_api_key: string;
};
export const getAiSettings = (token: string) =>
  request("/ai-service/settings", settingsSchema, { token });
export const saveAiSettings = (token: string, body: AiSettingsInput) =>
  request("/ai-service/settings", settingsSchema, {
    token,
    method: "PUT",
    body,
  });
export const getAiCapabilities = (token: string) =>
  request(
    "/ai-service/capabilities",
    z.object({ web_search_available: z.boolean() }),
    { token },
  );
export const testAiChat = (token: string) =>
  request("/ai-service/test-chat", z.object({ message: z.string() }), {
    token,
    method: "POST",
    timeoutMs: 40000,
  });
export const testAiSearch = (token: string) =>
  request(
    "/ai-service/test-search",
    z.object({
      message: z.string(),
      sources: z.array(z.object({ title: z.string(), url: z.string().url() })),
    }),
    { token, method: "POST", timeoutMs: 30000 },
  );
