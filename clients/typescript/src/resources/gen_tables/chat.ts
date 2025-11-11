import { IdSchema, TableSchemaCreateSchema, TableTypesSchema } from "@/resources/gen_tables/tables";
import { ChatCompletionChunkSchema, ChatEntrySchema, ReferencesSchema } from "@/resources/llm/chat";
import { z } from "zod";

export const GetConversationThreadRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: IdSchema,
    column_id: IdSchema,
    row_id: z.string().optional(),
    include: z.boolean().optional()
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

export const MultiRowCompletionResponseSchema = z.object({
    object: z.enum(["gen_table.completion.rows"]),
    rows: z.array(GenTableChatCompletionChunksSchema)
});

export const ColumnCompletionResponseSchema = ChatCompletionChunkSchema.extend({
    object: z.enum(["gen_table.completion.chunk"]),
    output_column_name: z.string(),
    row_id: z.string()
});

export const RowReferencesResponseSchema = ReferencesSchema.extend({
    object: z.enum(["gen_table.references"]),
    output_column_name: z.string()
});

export const CreateChatTableRequestSchema = TableSchemaCreateSchema;
export type CreateChatTableRequest = z.input<typeof CreateChatTableRequestSchema>;

export type GetConversationThreadRequest = z.input<typeof GetConversationThreadRequestSchema>;
export type GetConversationThreadResponse = z.infer<typeof GetConversationThreadResponseSchema>;
export type RowCompletionResponse = z.infer<typeof GenTableChatCompletionChunksSchema>;
export type MultiRowCompletionResponse = z.infer<typeof MultiRowCompletionResponseSchema>;
export type CellCompletionResponse = z.infer<typeof ColumnCompletionResponseSchema>;
export type CellReferencesResponse = z.infer<typeof RowReferencesResponseSchema>;
