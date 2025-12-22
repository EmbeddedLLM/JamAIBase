import { z } from "zod";

/**
 * Usage response schema
 */
export const UsageResponseSchema = z.object({
    data: z.array(z.any())
});

export type UsageResponse = z.infer<typeof UsageResponseSchema>;

/**
 * Usage metrics params
 */
export const UsageMetricsParamsSchema = z.object({
    type: z.enum(["llm", "embedding", "reranking"]),
    from: z.string(),
    windowSize: z.string(),
    orgIds: z.array(z.string()).optional(),
    projIds: z.array(z.string()).optional(),
    to: z.string().optional(),
    groupBy: z.array(z.string()).optional(),
    dataSource: z.enum(["clickhouse", "victoriametrics"]).optional()
});

export type UsageMetricsParams = z.infer<typeof UsageMetricsParamsSchema>;

/**
 * Billing metrics params
 */
export const BillingMetricsParamsSchema = z.object({
    from: z.string(),
    windowSize: z.string(),
    orgIds: z.array(z.string()).optional(),
    projIds: z.array(z.string()).optional(),
    to: z.string().optional(),
    groupBy: z.array(z.string()).optional(),
    dataSource: z.enum(["clickhouse", "victoriametrics"]).optional()
});

export type BillingMetricsParams = z.infer<typeof BillingMetricsParamsSchema>;

/**
 * Bandwidth metrics params
 */
export const BandwidthMetricsParamsSchema = z.object({
    from: z.string(),
    windowSize: z.string(),
    orgIds: z.array(z.string()).optional(),
    projIds: z.array(z.string()).optional(),
    to: z.string().optional(),
    groupBy: z.array(z.string()).optional(),
    dataSource: z.enum(["clickhouse", "victoriametrics"]).optional()
});

export type BandwidthMetricsParams = z.infer<typeof BandwidthMetricsParamsSchema>;

/**
 * Storage metrics params
 */
export const StorageMetricsParamsSchema = z.object({
    from: z.string(),
    windowSize: z.string(),
    orgIds: z.array(z.string()).optional(),
    projIds: z.array(z.string()).optional(),
    to: z.string().optional(),
    groupBy: z.array(z.string()).optional()
});

export type StorageMetricsParams = z.infer<typeof StorageMetricsParamsSchema>;
