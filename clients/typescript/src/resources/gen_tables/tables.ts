import { ChatRequestSchema } from "@/resources/llm/chat";
import { passthrough } from "@/utils";
import { z } from "zod";
import { zfd } from "zod-form-data";

// Define a generic function to create a pagination schema
function createPaginationSchema<T>(itemSchema: z.ZodType<T>) {
    return passthrough(
        z.object({
            items: z.array(itemSchema).describe("List of items paginated items.").default([]),
            offset: z.number().describe("Number of skipped items.").default(0),
            limit: z.number().describe("Number of items per page.").default(100),
            total: z.number().describe("Total number of items.").default(0)
        })
    );
}

export const QueryRequestParams = z.object({
    offset: z.number().describe("Number of skipped items.").default(0),
    limit: z.number().describe("Number of items per page.").default(100)
});

export const TableTypesSchema = z.enum(["action", "knowledge", "chat"]);

export const IdSchema = z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9_ \-]{0,98}[a-zA-Z0-9]$/, "Invalid Id");
export const TableIdSchema = z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{0,98}[a-zA-Z0-9]$/, "Invalid Table Id");
const DtypeCreateEnumSchema = z.enum(["int", "float", "str", "bool"]);

const DtypeEnumSchema = z.enum(["int", "int8", "float", "float64", "float32", "float16", "bool", "str", "date-time", "file", "bytes"]);
export const ColumnSchemaSchema = z.object({
    id: z.string(),
    dtype: DtypeEnumSchema.default("str").optional(),
    vlen: z.number().int().gte(0).default(0).optional(),
    index: z.boolean().default(true).optional(),
    gen_config: z.union([ChatRequestSchema.partial(), z.null()]).optional()
});

export const ColumnSchemaCreateSchema = ColumnSchemaSchema.extend({
    id: IdSchema,
    dtype: DtypeCreateEnumSchema.default("str").optional()
});

export const TableSchemaCreateSchema = z.object({
    id: TableIdSchema,
    cols: z.array(ColumnSchemaCreateSchema)
});

export let ListTableRequestSchema = QueryRequestParams.extend({
    parent_id: z.union([z.string(), z.null()]).optional()
})
    .partial()
    .extend({
        table_type: TableTypesSchema
    });

export const TableMetaResponseSchema = z.object({
    id: z.string(),
    cols: z.array(ColumnSchemaSchema),
    parent_id: z.union([z.string(), z.null()]),
    title: z.string(),
    lock_till: z.union([z.number(), z.null()]).optional(),
    updated_at: z.string(),
    indexed_at_fts: z.union([z.string(), z.null()]),
    indexed_at_vec: z.union([z.string(), z.null()]),
    indexed_at_sca: z.union([z.string(), z.null()]),
    num_rows: z.number().int()
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
    vec_decimals: z.number().int().default(0)
});

export const ListTableRowsResponseSchema = z.record(z.string(), z.any());

export const GetRowRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    row_id: IdSchema,
    columns: z.array(IdSchema).nullable().optional(),
    float_decimals: z.number().int().default(0),
    vec_decimals: z.number().int().default(0)
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
    table_id_dst: TableIdSchema,
    include_data: z.boolean().optional(),
    deploy: z.boolean().optional()
});

export const RenameColumnsRequestScheme = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    column_map: z.record(IdSchema, IdSchema)
});

export const ReorderColumnsRequestScheme = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    column_names: z.array(IdSchema)
});

export const AddColumnRequestSchema = z.object({
    id: TableIdSchema,
    // cols: z.array(ColumnSchemaSchema),
    cols: z.array(ColumnSchemaCreateSchema)
});

export const UpdateGenConfigRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    column_map: z.record(IdSchema, z.record(z.any(), z.any()))
});

export const DeleteRowRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    row_id: z.string(),
    reindex: z.boolean().default(true)
});

export const AddRowRequestSchema = z.object({
    table_type: TableTypesSchema,
    reindex: z.boolean().nullable().default(true),
    table_id: TableIdSchema,
    data: z.array(z.record(IdSchema, z.any())),
    concurrent: z.boolean().default(true)
    // stream: z.boolean()
});

export const RegenRowRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    row_ids: z.array(z.string()),
    reindex: z.boolean().nullable().default(null),
    concurrent: z.boolean().default(true)
    // stream: z.boolean()
});

export const UpdateRowRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    row_id: IdSchema,
    data: z.record(IdSchema, z.any()),
    reindex: z.boolean().nullable().default(null)
});

export const DeleteRowsRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    where: z.string().optional(),
    reindex: z.boolean().default(true)
});

export const HybridSearchRequestSchema = z.object({
    table_type: TableTypesSchema,
    table_id: TableIdSchema,
    query: z.string(),
    where: z.string().nullable().default(null).optional(),
    limit: z.number().gt(0).lte(1000).optional(),
    metric: z.string().optional(),
    nprobes: z.number().gt(0).lte(1000).optional(),
    refine_factor: z.number().gt(0).lte(1000).optional(),
    reranking_model: z.string().nullable().default(null).optional(),
    float_decimals: z.number().int().default(0),
    vec_decimals: z.number().int().default(0)
});

export const HybridSearchResponseSchema = z.array(z.record(z.string(), z.any()));

export const CreateTableRequestSchema = z.object({
    id: z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9_ \-]{0,98}[a-zA-Z0-9]$/),
    cols: z.array(ColumnSchemaSchema)
});

export const ImportTableRequestSchema = zfd.formData({
    file_path: zfd.text().optional(),
    file: zfd.file().optional(),
    table_id: zfd.text(IdSchema),
    table_type: zfd.text(TableTypesSchema),
    delimiter: zfd.text().default(",").optional()
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
export type ColumnSchema = z.infer<typeof ColumnSchemaSchema>;
export type ColumnSchemaCreate = z.infer<typeof ColumnSchemaCreateSchema>;
export type ListTableRequest = z.infer<typeof ListTableRequestSchema>;
export type PageListTableRowsResponse = z.infer<typeof PageListTableRowsResponseSchema>;
export type PageListTableMetaResponse = z.infer<typeof PageListTableMetaResponseSchema>;
export type TableMetaRequest = z.infer<typeof TableMetaRequestSchema>;
export type TableMetaResponse = z.infer<typeof TableMetaResponseSchema>;
export type GetRowRequest = z.input<typeof GetRowRequestSchema>;
export type GetRowResponse = z.infer<typeof GetRowResponseSchema>;
export type OkResponse = z.infer<typeof OkResponseSchema>;
export type DeleteTableRequest = z.infer<typeof DeleteTableRequestSchema>;
export type RenameTableRequest = z.infer<typeof RenameTableRequestSchema>;
export type DuplicateTableRequest = z.infer<typeof DuplicateTableRequestSchema>;
export type RenameColumnsRequest = z.infer<typeof RenameColumnsRequestScheme>;
export type ReorderColumnsRequest = z.infer<typeof ReorderColumnsRequestScheme>;
export type DropColumnsRequest = ReorderColumnsRequest;
export type AddColumnRequest = z.infer<typeof AddColumnRequestSchema>;
export type UpdateGenConfigRequest = z.infer<typeof UpdateGenConfigRequestSchema>;
export type DeleteRowRequest = z.infer<typeof DeleteRowRequestSchema>;
export type AddRowRequest = z.infer<typeof AddRowRequestSchema>;
export type RegenRowRequest = z.infer<typeof RegenRowRequestSchema>;
export type UpdateRowRequest = z.infer<typeof UpdateRowRequestSchema>;
export type DeleteRowsRequest = z.infer<typeof DeleteRowsRequestSchema>;
export type HybridSearchRequest = z.input<typeof HybridSearchRequestSchema>;
export type HybridSearchResponse = z.infer<typeof HybridSearchResponseSchema>;
export type ExportTableRequest = z.input<typeof ExportTableRequestSchema>;
export type ImportTableRequest = z.infer<typeof ImportTableRequestSchema>;
