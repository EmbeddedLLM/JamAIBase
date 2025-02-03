import { z } from "zod";

export const ModelInfoRequestSchema = z.object({
    model: z.string().optional(),
    capabilities: z
        .array(z.enum(["completion", "chat", "image", "audio", "tool", "embed", "rerank"]))
        .nullable()
        .optional()
});

export const ModelInfoSchema = z.object({
    id: z.string().default("openai/gpt-4o-mini"),
    object: z.string(),
    name: z.string(),
    context_length: z.number().default(16384),
    languages: z.array(z.string()),
    capabilities: z.array(z.enum(["completion", "chat", "image", "audio", "tool", "embed", "rerank"])).default(["chat"]),
    owned_by: z.string()
});

export const ModelInfoResponseSchema = z.object({
    object: z.enum(["chat.model_info"]),
    data: z.array(ModelInfoSchema)
});

export const ModelNamesRequestSchema = z.object({
    prefer: z.string().optional(),
    capabilities: z
        .array(z.enum(["completion", "chat", "image", "audio", "tool", "embed", "rerank"]))
        .nullable()
        .optional()
});

export const ModelNamesResponseSchema = z.array(z.string());

export type ModelInfoRequest = z.infer<typeof ModelInfoRequestSchema>;
export type ModelInfo = z.infer<typeof ModelInfoSchema>;
export type ModelInfoResponse = z.infer<typeof ModelInfoResponseSchema>;
export type ModelNamesRequest = z.infer<typeof ModelNamesRequestSchema>;
export type ModelNamesResponse = z.infer<typeof ModelNamesResponseSchema>;
