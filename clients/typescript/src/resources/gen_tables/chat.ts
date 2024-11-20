import { IdSchema, TableSchemaCreateSchema, TableTypesSchema } from "@/resources/gen_tables/tables";
import { ChatCompletionChunkSchema, ChatEntrySchema, ReferencesSchema } from "@/resources/llm/chat";
import { z } from "zod";

export const GetConversationThreadRequestSchema = z.object({
    table_id: IdSchema,
    column_id: IdSchema,
    row_id: z.string().default(""),
    table_type: TableTypesSchema,
    include: z.boolean().default(true)
});

export const GetConversationThreadResponseSchema = z.object({
    object: z.enum(["chat.thread"]).describe("Type of API response object."),
    thread: z.array(ChatEntrySchema).describe("List of chat messages.").default([])
});

export const GenTableChatCompletionChunksSchema = z.object({
    object: z.enum(["gen_table.completion.chunks"]),
    columns: z.record(z.string(), ChatCompletionChunkSchema),
    row_id: z.string()
});

export const GenTableRowsChatCompletionChunksSchema = z.object({
    object: z.enum(["gen_table.completion.rows"]),
    rows: z.array(GenTableChatCompletionChunksSchema)
});

export const GenTableStreamChatCompletionChunkSchema = ChatCompletionChunkSchema.extend({
    object: z.enum(["gen_table.completion.chunk"]),
    output_column_name: z.string(),
    row_id: z.string()
});

export const GenTableStreamReferencesSchema = ReferencesSchema.extend({
    object: z.enum(["gen_table.references"]),
    output_column_name: z.string()
});

export const CreateChatTableRequestSchema = TableSchemaCreateSchema;
export type CreateChatTableRequest = z.input<typeof CreateChatTableRequestSchema>;

export type GetConversationThreadRequest = z.input<typeof GetConversationThreadRequestSchema>;
export type GetConversationThreadResponse = z.infer<typeof GetConversationThreadResponseSchema>;
export type GenTableChatCompletionChunks = z.infer<typeof GenTableChatCompletionChunksSchema>;
export type GenTableRowsChatCompletionChunks = z.infer<typeof GenTableRowsChatCompletionChunksSchema>;
export type GenTableStreamChatCompletionChunk = z.infer<typeof GenTableStreamChatCompletionChunkSchema>;
export type GenTableStreamReferences = z.infer<typeof GenTableStreamReferencesSchema>;
