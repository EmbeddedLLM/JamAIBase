import { PageSchema, PaginationParamsSchema } from "@/resources/shared/types";
import { z } from "zod";

/**
 * Conversation create request schema
 */
export const ConversationCreateRequestSchema = z.object({
    agent_id: z.string(),
    title: z.string().nullable().optional(),
    data: z.record(z.any())
});

export type ConversationCreateRequest = z.infer<typeof ConversationCreateRequestSchema>;

/**
 * Conversation meta response schema
 */
export const ConversationMetaResponseSchema = z.object({
    conversation_id: z.string(),
    parent_id: z.string().nullable().optional(),
    title: z.string(),
    cols: z.array(z.any()),
    created_by: z.string(),
    updated_at: z.string(),
    num_rows: z.number(),
    version: z.string(),
    meta: z.record(z.any()).optional()
});

export type ConversationMetaResponse = z.infer<typeof ConversationMetaResponseSchema>;

/**
 * Agent meta response schema
 */
export const AgentMetaResponseSchema = z.object({
    agent_id: z.string(),
    title: z.string(),
    cols: z.array(z.any()),
    created_by: z.string(),
    updated_at: z.string(),
    num_rows: z.number(),
    version: z.string(),
    meta: z.record(z.any()).optional()
});

export type AgentMetaResponse = z.infer<typeof AgentMetaResponseSchema>;

/**
 * Message add request schema
 */
export const MessageAddRequestSchema = z.object({
    conversation_id: z.string(),
    data: z.record(z.any())
});

export type MessageAddRequest = z.infer<typeof MessageAddRequestSchema>;

/**
 * Message update request schema
 */
export const MessageUpdateRequestSchema = z.object({
    conversation_id: z.string(),
    row_id: z.string(),
    data: z.record(z.any())
});

export type MessageUpdateRequest = z.infer<typeof MessageUpdateRequestSchema>;

/**
 * Messages regen request schema
 */
export const MessagesRegenRequestSchema = z.object({
    conversation_id: z.string(),
    row_id: z.string()
});

export type MessagesRegenRequest = z.infer<typeof MessagesRegenRequestSchema>;

/**
 * Conversation threads response schema
 */
export const ChatReferenceChunkSchema = z.object({
    chunk_id: z.string(),
    context: z.record(z.any()),
    document_id: z.string(),
    file_name: z.string(),
    file_path: z.string(),
    metadata: z.record(z.any()),
    text: z.string(),
    title: z.string(),
});

export const ChatReferencesSchema = z.object({
    object: z.literal("chat.references"),
    search_query: z.string(),
    chunks: z.array(ChatReferenceChunkSchema),
});

export const ChatThreadEntrySchema = z.object({
    content: z.string(),
    role: z.string(),
    references: ChatReferencesSchema.optional().nullable(),
});

export const ChatThreadSchema = z.object({
    column_id: z.string(),
    object: z.literal("chat.thread"),
    thread: z.array(ChatThreadEntrySchema),
});

export const ConversationThreadsResponseSchema = z.object({
    object: z.literal("chat.threads"),
    threads: z.record(ChatThreadSchema),
    conversation_id: z.string(),
});


export type ConversationThreadsResponse = z.infer<typeof ConversationThreadsResponseSchema>;

/**
 * List conversations params
 */
export const ListConversationsParamsSchema = PaginationParamsSchema;

export type ListConversationsParams = z.infer<typeof ListConversationsParamsSchema>;

/**
 * List messages params
 */
export const ListMessagesParamsSchema = PaginationParamsSchema.extend({
    columns: z.array(z.string()).optional(),
    search_columns: z.array(z.string()).optional(),
    float_decimals: z.number().optional(),
    vec_decimals: z.number().optional()
});

export type ListMessagesParams = z.infer<typeof ListMessagesParamsSchema>;

// Page types
export const PageConversationMetaResponseSchema = PageSchema(ConversationMetaResponseSchema);
export type PageConversationMetaResponse = z.infer<typeof PageConversationMetaResponseSchema>;
