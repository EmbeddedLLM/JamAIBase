import { createPaginationSchema } from "@/helpers/utils";
import { RAGParamsSchema } from "@/resources/llm/chat";
import { z } from "zod";

export const GenTableOrderBy = Object.freeze({
    ID: "id", // Sort by `id` column
    TABLE_ID: "table_id", // Sort by `table_id` column
    UPDATED_AT: "updated_at" // Sort by `updated_at` column
});

export const QueryRequestParams = z.object({
    offset: z.number().describe("Number of skipped items.").default(0),
    limit: z.number().describe("Number of items per page.").default(100)
});

export const TableTypesSchema = z.enum(["action", "knowledge", "chat"]);

export const IdSchema = z.string().regex(/^[A-Za-z0-9]([A-Za-z0-9 _-]{0,98}[A-Za-z0-9])?$/, "Invalid Id");
export const TableIdSchema = z.string().regex(/^[A-Za-z0-9]([A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$/, "Invalid Table Id");

const DtypeCreateEnumSchema = z.enum(["int", "float", "bool", "str", "image", "audio", "document"]);

const DtypeEnumSchema = z.enum(["int", "int8", "float", "float32", "float16", "bool", "str", "image", "audio", "document", "date-time", "json"]);

export const EmbedGenConfigSchema = z.object({
    object: z.literal("gen_config.embed").default("gen_config.embed"),
    embedding_model: z.string(),
    source_column: z.string()
});
export const LLMGenConfigSchema = z.object({
    object: z.literal("gen_config.llm").default("gen_config.llm"),
    model: z.string().default(""),
    prompt: z.string().default(""),
    system_prompt: z.string().default(""),
    multi_turn: z.boolean().default(false),
    rag_params: RAGParamsSchema.nullable().default(null),
    temperature: z.number().min(0.001).max(2.0).default(0.2),
    top_p: z.number().min(0.001).max(1.0).default(0.6),
    stop: z.array(z.string()).nullable().default(null),
    max_tokens: z.number().int().min(1).default(2048),
    presence_penalty: z.number().default(0.0),
    frequency_penalty: z.number().default(0.0),
    logit_bias: z.record(z.string(), z.any()).default({})
});

export const CodeGenConfigSchema = z.object({
    object: z.literal("gen_config.code").default("gen_config.code"),
    source_column: z.string()
});

export const ColumnSchemaSchema = z.object({
    id: z.string(),
    dtype: DtypeEnumSchema.default("str"),
    vlen: z.number().int().gte(0).default(0),
    index: z.boolean().default(true),
    gen_config: z.union([LLMGenConfigSchema, EmbedGenConfigSchema, CodeGenConfigSchema, z.null()]).optional()
});

export const ColumnSchemaCreateSchema = ColumnSchemaSchema.extend({
    id: IdSchema,
    dtype: DtypeCreateEnumSchema.default("str")
});

export const TableSchemaCreateSchema = z.object({
    id: TableIdSchema,
    cols: z.array(ColumnSchemaCreateSchema)
});

export let ListTableRequestSchema = QueryRequestParams.extend({
    table_type: TableTypesSchema,
    offset: z.number().min(0).optional(),
    limit: z.number().min(1).max(100).optional(),
    order_by: z.string().optional(),
    order_ascending: z.boolean().optional().optional(),
    parent_id: z.string().nullable().optional(),
    search_query: z.string().optional(),
    count_rows: z.boolean().optional(),
    created_by: z.string().nullable().optional(),
});

export const TableMetaResponseSchema = z.object({
    id: z.string(),
    cols: z.array(ColumnSchemaSchema),
    parent_id: z.union([z.string(), z.null()]),
    title: z.string(),
    created_by: z.string(),
    updated_at: z.string(),
    num_rows: z.number().int(),
    version: z.string()
});

export const TableMetaRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema
});

export const ListTableRowsRequestSchema = QueryRequestParams.extend({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    columns: z.array(IdSchema).nullable().optional(),
    search_query: z.string().default(""),
    float_decimals: z.number().int().default(0),
    vec_decimals: z.number().int().default(0),
    order_descending: z.boolean().default(true)
});

export const ListTableRowsResponseSchema = z.record(z.string(), z.any());

export const GetRowRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    row_id: z.string(),
    columns: z.array(IdSchema).nullable().optional(),
    float_decimals: z.number().int().optional(),
    vec_decimals: z.number().int().optional()
});

export const GetRowResponseSchema = z.record(z.string(), z.any());

export const PageListTableRowsResponseSchema = createPaginationSchema(ListTableRowsResponseSchema);
export const PageListTableMetaResponseSchema = createPaginationSchema(TableMetaResponseSchema);

export const OkResponseSchema = z.object({
    ok: z.boolean().default(true)
});

export const DeleteTableRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema
});

export const RenameTableRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id_src: TableIdSchema,
    table_id_dst: TableIdSchema
});

export const DuplicateTableRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id_src: TableIdSchema,
    table_id_dst: TableIdSchema.nullable().optional(),
    include_data: z.boolean().optional(),
    create_as_child: z.boolean().optional()
});

export const CreateChildTableRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id_src: TableIdSchema,
    table_id_dst: TableIdSchema
});

export const RenameColumnsRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    column_map: z.record(IdSchema, IdSchema)
});

export const ReorderColumnsRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    column_names: z.array(IdSchema)
});

export const DropColumnsRequestSchema = ReorderColumnsRequestSchema;

export const AddColumnRequestSchema = z.object({
    id: TableIdSchema,
    cols: z.array(ColumnSchemaCreateSchema)
});

export const UpdateGenConfigRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    column_map: z.record(z.string(), z.union([LLMGenConfigSchema, EmbedGenConfigSchema, CodeGenConfigSchema, z.null()]))
});

export const DeleteRowRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    row_id: z.string(),
    reindex: z.boolean().default(true)
});

export const AddRowRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    data: z.array(z.record(IdSchema, z.any())),
    concurrent: z.boolean().default(true)
    // stream: z.boolean()
});

export const RegenRowRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    row_ids: z.array(z.string()),
    regen_strategy: z.string().nullable().optional(),
    output_column_id: z.string().nullable().optional(),
    concurrent: z.boolean().optional()
    // stream: z.boolean()
});

export const UpdateRowRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    data: z.record(z.string(), z.record(IdSchema, z.any())),
});

export const DeleteRowsRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    row_ids: z.array(z.string()).nullable().optional(),
    where: z.string().optional(),
});

export const HybridSearchRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    query: z.string(),
    // where: z.string().nullable().default(null).optional(),
    limit: z.number().gt(0).lte(1000).optional(),
    metric: z.string().optional(),
    // nprobes: z.number().gt(0).lte(1000).optional(),
    // refine_factor: z.number().gt(0).lte(1000).optional(),
    reranking_model: z.string().nullable().default(null).optional(),
    float_decimals: z.number().int().default(0),
    vec_decimals: z.number().int().default(0)
});

export const HybridSearchResponseSchema = z.array(z.record(z.string(), z.any()));

export const CreateTableRequestSchema = z.object({
    id: z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9_ \-]{0,98}[a-zA-Z0-9]$/),
    cols: z.array(ColumnSchemaSchema)
});

export const ImportTableRequestSchema = z.object({
    file_path: z.string().optional(),
    file: z.any().optional(),
    table_id: TableIdSchema,
    table_type: TableTypesSchema,
    delimiter: z.string().default(",").optional()
});

export const ExportTableRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    delimiter: z.string().default(","),
    columns: z.array(z.string()).nullable().optional()
});

export type TableTypes = z.infer<typeof TableTypesSchema>;
export type ListTableRowsRequest = z.input<typeof ListTableRowsRequestSchema>;
export type ListTableRowsResponse = z.infer<typeof ListTableRowsResponseSchema>;
export type DtypeEnum = z.infer<typeof DtypeEnumSchema>;
export type ColumnSchema = z.input<typeof ColumnSchemaSchema>;
export type ColumnSchemaCreate = z.input<typeof ColumnSchemaCreateSchema>;
export type ListTableRequest = z.input<typeof ListTableRequestSchema>;
export type PageListTableRowsResponse = z.infer<typeof PageListTableRowsResponseSchema>;
export type PageListTableMetaResponse = z.infer<typeof PageListTableMetaResponseSchema>;
export type TableMetaRequest = z.input<typeof TableMetaRequestSchema>;
export type TableMetaResponse = z.infer<typeof TableMetaResponseSchema>;
export type GetRowRequest = z.input<typeof GetRowRequestSchema>;
export type GetRowResponse = z.infer<typeof GetRowResponseSchema>;
export type OkResponse = z.infer<typeof OkResponseSchema>;
export type DeleteTableRequest = z.input<typeof DeleteTableRequestSchema>;
export type RenameTableRequest = z.input<typeof RenameTableRequestSchema>;
export type DuplicateTableRequest = z.input<typeof DuplicateTableRequestSchema>;
export type CreateChildTableRequest = z.input<typeof CreateChildTableRequestSchema>;
export type RenameColumnsRequest = z.infer<typeof RenameColumnsRequestSchema>;
export type ReorderColumnsRequest = z.infer<typeof ReorderColumnsRequestSchema>;
export type DropColumnsRequest = ReorderColumnsRequest;
export type AddColumnRequest = z.input<typeof AddColumnRequestSchema>;
export type UpdateGenConfigRequest = z.input<typeof UpdateGenConfigRequestSchema>;
export type DeleteRowRequest = z.input<typeof DeleteRowRequestSchema>;
export type AddRowRequest = z.input<typeof AddRowRequestSchema>;
export type RegenRowRequest = z.input<typeof RegenRowRequestSchema>;
export type UpdateRowRequest = z.input<typeof UpdateRowRequestSchema>;
export type DeleteRowsRequest = z.infer<typeof DeleteRowsRequestSchema>;
export type HybridSearchRequest = z.input<typeof HybridSearchRequestSchema>;
export type HybridSearchResponse = z.infer<typeof HybridSearchResponseSchema>;
export type ExportTableRequest = z.input<typeof ExportTableRequestSchema>;
export type ImportTableRequest = z.input<typeof ImportTableRequestSchema>;
