import { z } from "zod";

/**
 * Represents who said a chat message.
 */

const ChatRoleSchema = z.enum(["system", "user", "assistant", "function"]);

export const ChatEntrySchema = z.object({
    role: ChatRoleSchema,
    content: z.union([z.string(), z.array(z.record(z.union([z.string(), z.record(z.string())])))]),
    name: z.string().optional().nullable()
});

export const RAGParamsSchema = z.object({
    search_query: z.string().optional(),
    k: z.number().optional(),
    fetch_k: z.number().optional(),
    document_ids: z.array(z.string()).optional(),
    rank_profile: z.enum(["bm25", "semantic", "hybrid", "hybrid_log"]).optional(),
    rerank: z.boolean().optional(),
    concat_reranker_input: z.boolean().optional()
});

const FunctionSpecSchema = z.object({
    name: z.string(),
    description: z.string().optional(),
    parameters: z.record(z.string(), z.any())
});

const ToolSpecSchema = z.object({
    type: z.string().optional(),
    function: FunctionSpecSchema
});

const FunctionChoiceSpecSchema = z.object({
    name: z.string()
});

export const ChatCompletionUsageSchema = z.object({
    prompt_tokens: z.number().nullable().optional().default(0),
    completion_tokens: z.number().nullable().optional().default(0),
    total_tokens: z.number().nullable().optional().default(0)
});

/**
 * Represents a message in the chat context.
 */
// export type ChatEntry = {
//   role: ChatRole;
//   content: string;
//   name?: string | null;
// };

export const ChatRequestSchema = z.object({
    id: z.string().default(""),
    model: z.string().default(""),
    messages: z.array(ChatEntrySchema),
    rag_params: RAGParamsSchema.nullable().default(null),
    temperature: z.number().min(0.001).max(2.0).default(0.2),
    top_p: z.number().min(0.001).max(1.0).default(0.6),
    n: z.number().default(1),
    stream: z.boolean().default(true),
    stop: z.array(z.string()).nullable().default(null),
    max_tokens: z.number().int().min(1).default(2048),
    presence_penalty: z.number().default(0.0),
    frequency_penalty: z.number().default(0.0),
    logit_bias: z.record(z.string(), z.any()).default({}),
    user: z.string().default("")
});

// Delta schema for streaming responses - same as ChatEntry but with all fields optional
export const ChatCompletionDeltaSchema = ChatEntrySchema.partial().extend({
    role: ChatRoleSchema.optional().default("assistant"),
    content: z.union([z.string(), z.array(z.record(z.union([z.string(), z.record(z.string())])))]).nullable().optional()
});

export const ChatCompletionChoiceSchema = z.object({
    message: ChatEntrySchema,
    index: z.number(),
    finish_reason: z.string().nullable()
});

export const ChatCompletionChoiceDeltaSchema = z.object({
    message: ChatEntrySchema.nullable().optional(),
    index: z.number(),
    finish_reason: z.string().nullable().optional(),
    delta: ChatCompletionDeltaSchema.nullable().optional()
});

export const ChunkSchema = z.object({
    text: z.string(),
    title: z.string(),
    page: z.number(),
    file_name: z.string(),
    file_path: z.string(),
    document_id: z.string(),
    chunk_id: z.string(),
    metadata: z.record(z.string(), z.any())
});

export const ReferencesSchema = z.object({
    object: z.enum(["chat.references"]),
    chunks: z.array(ChunkSchema),
    search_query: z.string().describe("Query used to retrieve items from the KB database."),
    finish_reason: z.enum(["stop", "context_overflow"]).nullable()
});

export const ChatCompletionChunkSchema = z.object({
    id: z.string(),
    object: z.enum(["chat.completion"]),
    created: z.number(),
    model: z.string(),
    usage: ChatCompletionUsageSchema.nullable().optional(),
    // choices: z.array(ChatCompletionChoiceSchema),
    choices: z.union([z.array(ChatCompletionChoiceSchema), z.array(ChatCompletionChoiceDeltaSchema)]),
    references: ReferencesSchema.nullable().optional()
});

export const StreamChatCompletionChunkSchema = z.object({
    id: z.string(),
    object: z.enum(["chat.completion.chunk"]),
    created: z.number(),
    model: z.string(),
    usage: ChatCompletionUsageSchema.nullable().optional(),
    choices: z.array(ChatCompletionChoiceDeltaSchema),
    // choices: z.union([z.array(ChatCompletionChoiceSchema), z.array(ChatCompletionChoiceDeltaSchema)]),
    references: ReferencesSchema.nullable().optional()
});

export type ChatRole = z.infer<typeof ChatRoleSchema>;
export type ChatEntry = z.infer<typeof ChatEntrySchema>;
export type RAGParams = z.infer<typeof RAGParamsSchema>;
export type FunctionSpec = z.infer<typeof FunctionSpecSchema>;
export type ToolSpec = z.infer<typeof ToolSpecSchema>;
export type FunctionChoiceSpec = z.infer<typeof FunctionChoiceSpecSchema>;
export type ChatCompletionUsage = z.infer<typeof ChatCompletionUsageSchema>;
export type ChatRequest = z.input<typeof ChatRequestSchema>;
export type Chunk = z.infer<typeof ChunkSchema>;
export type References = z.infer<typeof ReferencesSchema>;
export type ChatCompletionDelta = z.infer<typeof ChatCompletionDeltaSchema>;
export type ChatCompletionChoice = z.infer<typeof ChatCompletionChoiceSchema>;
export type ChatCompletionChoiceDelta = z.infer<typeof ChatCompletionChoiceDeltaSchema>;
export type ChatCompletionChunk = z.infer<typeof ChatCompletionChunkSchema>;
export type StreamChatCompletionChunk = z.infer<typeof StreamChatCompletionChunkSchema>;
