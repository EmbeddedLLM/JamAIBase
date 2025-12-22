import { z } from "zod";

export const ModelInfoRequestSchema = z.object({
    model: z.string().optional(),
    capabilities: z
        .array(z.enum(["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]))
        .nullable()
        .optional()
});

export const ModelInfoSchema = z.object({
    id: z.string().default("openai/gpt-4o-mini"),
    type: z.string().optional(),
    name: z.string(),
    owned_by: z.string(),
    capabilities: z.array(z.enum(["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"])).default(["chat"]),
    context_length: z.number().default(16384),
    languages: z.array(z.string()),
    max_output_tokens: z.number().nullable().optional(),
    created_at: z.string().optional(),
    updated_at: z.string().optional()
});

export const ModelInfoResponseSchema = z.object({
    object: z.enum(["models.info"]),
    data: z.array(ModelInfoSchema)
});

export const ModelNamesRequestSchema = z.object({
    prefer: z.string().optional(),
    capabilities: z
        .array(z.enum(["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]))
        .nullable()
        .optional()
});

export const ModelNamesResponseSchema = z.array(z.string());

export type ModelInfoRequest = z.infer<typeof ModelInfoRequestSchema>;
export type ModelInfo = z.infer<typeof ModelInfoSchema>;
export type ModelInfoResponse = z.infer<typeof ModelInfoResponseSchema>;
export type ModelNamesRequest = z.infer<typeof ModelNamesRequestSchema>;
export type ModelNamesResponse = z.infer<typeof ModelNamesResponseSchema>;
