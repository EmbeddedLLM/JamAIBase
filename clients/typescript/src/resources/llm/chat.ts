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
    table_id: z.string().default(""),
    reranking_model: z.string().nullable().default(null),
    search_query: z.string().default(""),
    k: z.number().int().gt(0).lte(1024).default(3),
    rerank: z.boolean().default(true),
    concat_reranker_input: z.boolean().default(false),
    inline_citations: z.boolean().default(true)
});

const FunctionParameterSchema = z.object({
    type: z.string().default(""),
    description: z.string().default(""),
    enum: z.array(z.string()).default([])
});

const FunctionParametersSchema = z.object({
    type: z.string().default("object"),
    properties: z.record(z.string(), FunctionParameterSchema),
    required: z.array(z.string()),
    additionalProperties: z.boolean().default(false)
});

const FunctionSchema = z.object({
    name: z.string().max(64),
    description: z.string().nullable().default(null),
    parameters: FunctionParametersSchema.nullable().default(null),
    strict: z.boolean().default(false)
});

const FunctionToolSchema = z.object({
    type: z.literal("function").default("function"),
    function: FunctionSchema
});

const WebSearchToolSchema = z.object({
    type: z.literal("web_search").default("web_search")
});

const CodeInterpreterToolSchema = z.object({
    type: z.literal("code_interpreter").default("code_interpreter"),
    container: z.record(z.string(), z.string()).default({ type: "auto" })
});

export const ToolSchema = z.discriminatedUnion("type", [
    WebSearchToolSchema,
    CodeInterpreterToolSchema,
    FunctionToolSchema
]);

const ToolChoiceFunctionSchema = z.object({
    name: z.string()
});

const ToolChoiceSchema = z.object({
    type: z.string().default("function"),
    function: ToolChoiceFunctionSchema
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
    tools: z.array(ToolSchema).min(1).nullable().default(null),
    tool_choice: z.union([
        z.enum(["none", "auto", "required"]),
        ToolChoiceSchema
    ]).nullable().default(null),
    temperature: z.number().min(0.001).max(2.0).default(0.2),
    top_p: z.number().min(0.001).max(1.0).default(0.6),
    n: z.number().default(1),
    stream: z.boolean().default(false),
    stop: z.array(z.string()).nullable().default(null),
    max_tokens: z.number().int().min(1).default(2048),
    max_completion_tokens: z.number().int().min(1).nullable().default(null),
    presence_penalty: z.number().default(0.0),
    frequency_penalty: z.number().default(0.0),
    logit_bias: z.record(z.string(), z.any()).default({}),
    reasoning_effort: z.enum(["disable", "minimal", "none", "low", "medium", "high"]).nullable().default(null),
    thinking_budget: z.number().int().gte(0).nullable().default(null),
    reasoning_summary: z.enum(["auto", "concise", "detailed"]).default("auto"),
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
    title: z.string().default(""),
    page: z.number().nullable().default(null),
    file_name: z.string().default(""),
    file_path: z.string().default(""),
    document_id: z.string().default(""),
    chunk_id: z.string().default(""),
    context: z.record(z.string(), z.string()).default({}),
    metadata: z.record(z.string(), z.any()).default({})
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
export type Tool = z.infer<typeof ToolSchema>;
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
