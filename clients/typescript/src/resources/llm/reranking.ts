import { z } from "zod";

/**
 * Reranking request schema
 */
export const RerankingRequestSchema = z.object({
    model: z.string(),
    documents: z.array(z.string()),
    query: z.string()
});

export type RerankingRequest = z.infer<typeof RerankingRequestSchema>;

/**
 * Reranking data schema
 */
export const RerankingDataSchema = z.object({
    object: z.literal("reranking"),
    index: z.number(),
    relevance_score: z.number()
});

export type RerankingData = z.infer<typeof RerankingDataSchema>;

/**
 * Reranking usage schema
 */
export const RerankingUsageSchema = z.object({
    documents: z.number(),
    input_tokens: z.number().nullable().optional(),
    output_tokens: z.number().nullable().optional()
});

export type RerankingUsage = z.infer<typeof RerankingUsageSchema>;

/**
 * Reranking API version schema
 */
export const RerankingApiVersionSchema = z.object({
    version: z.string().default(""),
    is_deprecated: z.boolean().default(false),
    is_experimental: z.boolean().default(false)
});

export type RerankingApiVersion = z.infer<typeof RerankingApiVersionSchema>;

/**
 * Reranking billed units schema
 */
export const RerankingBilledUnitsSchema = z.object({
    images: z.number().nullable().optional(),
    input_tokens: z.number().nullable().optional(),
    output_tokens: z.number().nullable().optional(),
    search_units: z.number().nullable().optional(),
    classifications: z.number().nullable().optional()
});

export type RerankingBilledUnits = z.infer<typeof RerankingBilledUnitsSchema>;

/**
 * Reranking meta usage schema
 */
export const RerankingMetaUsageSchema = z.object({
    input_tokens: z.number().nullable().optional(),
    output_tokens: z.number().nullable().optional()
});

export type RerankingMetaUsage = z.infer<typeof RerankingMetaUsageSchema>;

/**
 * Reranking metadata schema
 */
export const RerankingMetaSchema = z.object({
    model: z.string(),
    api_version: RerankingApiVersionSchema.nullable().optional(),
    billed_units: RerankingBilledUnitsSchema.nullable().optional(),
    tokens: RerankingMetaUsageSchema.nullable().optional(),
    warnings: z.array(z.string()).nullable().optional()
});

export type RerankingMeta = z.infer<typeof RerankingMetaSchema>;

/**
 * Reranking response schema
 */
export const RerankingResponseSchema = z.object({
    object: z.literal("list"),
    results: z.array(RerankingDataSchema),
    usage: RerankingUsageSchema,
    meta: RerankingMetaSchema
});

export type RerankingResponse = z.infer<typeof RerankingResponseSchema>;

/**
 * Model IDs request params schema
 */
export const ModelIdsParamsSchema = z.object({
    prefer: z.string().optional(),
    capabilities: z.array(z.string()).optional()
});

/**
 * Model IDs request params
 */
export type ModelIdsParams = z.infer<typeof ModelIdsParamsSchema>;
