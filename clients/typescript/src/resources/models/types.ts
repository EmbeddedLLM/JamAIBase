import { PageSchema, PaginationParamsSchema } from "@/resources/shared/types";
import { z } from "zod";

/**
 * Model config create schema
 */
export const ModelConfigCreateSchema = z.object({
    id: z.string(),
    name: z.string().max(255),
    type: z.enum(["completion", "embed", "rerank"]),
    owned_by: z.string().optional(),
    context_length: z.number().optional(),
    capabilities: z.array(z.string()).optional(),
    languages: z.array(z.string()).optional(),
    max_output_tokens: z.number().nullable().optional(),
    timeout: z.number().optional(),
    priority: z.number().optional(),
    allowed_orgs: z.array(z.string()).optional(),
    blocked_orgs: z.array(z.string()).optional(),
    llm_input_cost_per_mtoken: z.number().optional(),
    llm_output_cost_per_mtoken: z.number().optional(),
    embedding_size: z.number().nullable().optional(),
    embedding_dimensions: z.number().nullable().optional(),
    embedding_transform_query: z.string().nullable().optional(),
    embedding_cost_per_mtoken: z.number().optional(),
    reranking_cost_per_ksearch: z.number().optional(),
    meta: z.record(z.any()).optional(),
});

export type ModelConfigCreate = z.infer<typeof ModelConfigCreateSchema>;

/**
 * Model config update schema
 */
export const ModelConfigUpdateSchema = z.object({
    name: z.string().max(255).optional(),
    context_length: z.number().optional(),
    capabilities: z.array(z.string()).optional(),
    languages: z.array(z.string()).optional(),
    meta: z.record(z.any()).optional()
});

export type ModelConfigUpdate = z.infer<typeof ModelConfigUpdateSchema>;

/**
 * Model config read schema
 */
export const ModelConfigReadSchema = z.object({
    id: z.string(),
    type: z.enum(["completion", "llm", "embed", "rerank"]),
    name: z.string(),
    owned_by: z.string(),
    context_length: z.number().nullable().optional(),
    capabilities: z.array(z.string()).optional(),
    languages: z.array(z.string()).optional(),
    max_output_tokens: z.number().nullable().optional(),
    timeout: z.number().optional(),
    priority: z.number().optional(),
    allowed_orgs: z.array(z.string()).optional(),
    blocked_orgs: z.array(z.string()).optional(),
    llm_input_cost_per_mtoken: z.number().optional(),
    llm_output_cost_per_mtoken: z.number().optional(),
    embedding_size: z.number().nullable().optional(),
    embedding_dimensions: z.number().nullable().optional(),
    embedding_transform_query: z.string().nullable().optional(),
    embedding_cost_per_mtoken: z.number().optional(),
    reranking_cost_per_ksearch: z.number().optional(),
    is_private: z.boolean().optional(),
    deployments: z.array(z.any()).optional(),
    is_active: z.boolean().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    meta: z.record(z.any()).optional()
});

export type ModelConfigRead = z.infer<typeof ModelConfigReadSchema>;

/**
 * Deployment create schema
 */
export const DeploymentCreateSchema = z.object({
    model_id: z.string(),
    name: z.string().max(255),
    routing_id: z.string().default("").optional(),
    api_base: z.string().default("").optional(),
    provider: z.string().default("").optional(),
    weight: z.number().default(1).optional(),
    cooldown_until: z.string().optional(),
    meta: z.record(z.any()).optional()
});

export type DeploymentCreate = z.infer<typeof DeploymentCreateSchema>;

/**
 * Deployment update schema
 */
export const DeploymentUpdateSchema = z.object({
    name: z.string().max(255).optional(),
    routing_id: z.string().optional(),
    api_base: z.string().optional(),
    provider: z.string().optional(),
    weight: z.number().optional(),
    cooldown_until: z.string().optional(),
    meta: z.record(z.any()).optional()
});

export type DeploymentUpdate = z.infer<typeof DeploymentUpdateSchema>;

/**
 * Deployment read schema
 */
export const DeploymentReadSchema = z.object({
    id: z.string(),
    model_id: z.string(),
    name: z.string(),
    routing_id: z.string(),
    api_base: z.string(),
    provider: z.string(),
    weight: z.number(),
    cooldown_until: z.string(),
    status: z.string(),
    model: z.any().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    meta: z.record(z.any()).optional()
});

export type DeploymentRead = z.infer<typeof DeploymentReadSchema>;

/**
 * List model configs params
 */
export const ListModelConfigsParamsSchema = PaginationParamsSchema.extend({
    organization_id: z.string().optional()
});

export type ListModelConfigsParams = z.infer<typeof ListModelConfigsParamsSchema>;

/**
 * List deployments params
 */
export const ListDeploymentsParamsSchema = PaginationParamsSchema;

export type ListDeploymentsParams = z.infer<typeof ListDeploymentsParamsSchema>;

// Page types
export const PageModelConfigReadSchema = PageSchema(ModelConfigReadSchema);
export type PageModelConfigRead = z.infer<typeof PageModelConfigReadSchema>;

export const PageDeploymentReadSchema = PageSchema(DeploymentReadSchema);
export type PageDeploymentRead = z.infer<typeof PageDeploymentReadSchema>;
