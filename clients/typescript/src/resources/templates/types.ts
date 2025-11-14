import { createPaginationSchema } from "@/helpers/utils";
import { TableIdSchema, TableMetaResponseSchema, TableTypesSchema } from "@/resources/gen_tables/tables";
import { z } from "zod";

const TemplateTagSchema = z.object({
    id: z.string()
});
const TemplateSchema = z.object({
    id: z.string(),
    name: z.string(),
    created_at: z.string(),
    tags: z.array(TemplateTagSchema)
});

// List Templates
export const ListTemplatesRequestSchema = z.object({
    offset: z.number().int().min(0).optional(),
    limit: z.number().int().min(1).max(1000).optional(),
    order_by: z.string().optional(),
    order_ascending: z.boolean().optional(),
    search_query: z.string().optional()
});
export const ListTemplatesResponseSchema = createPaginationSchema(TemplateSchema);

// Get Template
export const GetTemplateRequestSchema = z.object({
    template_id: z.string()
});
export const GetTemplateResponseSchema = TemplateSchema;

// List Table
export const ListTablesRequestSchema = z.object({
    table_type: TableTypesSchema,
    template_id: z.string(),
    offset: z.number().int().min(0).optional(),
    limit: z.number().int().min(1).max(100).optional(),
    order_by: z.string().optional(),
    order_ascending: z.boolean().optional(),
    parent_id: z.string().optional(),
    search_query: z.string().optional(),
    count_rows: z.boolean().optional()
});
export const ListTablesResponseSchema = createPaginationSchema(TableMetaResponseSchema);

// Get Table
export const GetTableRequestSchema = z.object({
    template_id: z.string(),
    table_type: TableTypesSchema,
    table_id: TableIdSchema
});
export const GetTableResponseSchema = TableMetaResponseSchema;

// List Table Rows
export const ListTableRowsRequestSchema = z.object({
    template_id: z.string(),
    table_type: z.string(),
    table_id: TableIdSchema,
    starting_after: z.string().nullable().optional(),
    offset: z.number().int().min(0).default(0),
    limit: z.number().int().min(1).max(100).default(100),
    order_by: z.string().default("updated_at"),
    order_ascending: z.boolean().default(true),
    parent_id: z.string().nullable().optional(),
    float_decimals: z.number().int().min(0).default(0),
    vec_decimals: z.number().int().min(0).default(0)
});
export const ListTableRowsResponseSchema = createPaginationSchema(z.record(z.string(), z.any()));

// Types
export type IListTemplatesRequest = z.input<typeof ListTemplatesRequestSchema>;
export type IListTemplatesResponse = z.infer<typeof ListTemplatesResponseSchema>;

export type IGetTemplateRequest = z.input<typeof GetTemplateRequestSchema>;
export type IGetTemplateResponse = z.infer<typeof GetTemplateResponseSchema>;

export type IListTablesRequest = z.input<typeof ListTablesRequestSchema>;
export type IListTablesResponse = z.infer<typeof ListTablesResponseSchema>;

export type IGetTableRequest = z.input<typeof GetTableRequestSchema>;
export type IGetTableResponse = z.infer<typeof GetTableResponseSchema>;

export type IListTableRowsRequest = z.input<typeof ListTableRowsRequestSchema>;
export type IListTableRowsResponse = z.infer<typeof ListTableRowsResponseSchema>;
