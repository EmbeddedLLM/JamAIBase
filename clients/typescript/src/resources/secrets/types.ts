import { PageSchema, PaginationParamsSchema } from "@/resources/shared/types";
import { z } from "zod";

/**
 * Secret create schema
 */
export const SecretCreateSchema = z.object({
    name: z.string().regex(/^[A-Za-z_][A-Za-z0-9_]*$/),
    value: z.string().nullable().optional(),
    allowed_projects: z.array(z.string()).nullable().optional(),
    meta: z.record(z.any()).optional()
});

export type SecretCreate = z.infer<typeof SecretCreateSchema>;

/**
 * Secret update schema
 */
export const SecretUpdateSchema = z.object({
    value: z.string().nullable().optional(),
    allowed_projects: z.array(z.string()).nullable().optional(),
    meta: z.record(z.any()).optional()
});

export type SecretUpdate = z.infer<typeof SecretUpdateSchema>;

/**
 * Secret read schema
 */
export const SecretReadSchema = z.object({
    name: z.string(),
    value: z.string(),
    organization_id: z.string(),
    allowed_projects: z.array(z.string()).nullable().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    meta: z.record(z.any()).optional()
});

export type SecretRead = z.infer<typeof SecretReadSchema>;

/**
 * List secrets params
 */
export const ListSecretsParamsSchema = PaginationParamsSchema.extend({
    search_columns: z.array(z.string()).optional(),
    after: z.string().optional()
});

export type ListSecretsParams = z.infer<typeof ListSecretsParamsSchema>;

// Page types
export const PageSecretReadSchema = PageSchema(SecretReadSchema);
export type PageSecretRead = z.infer<typeof PageSecretReadSchema>;
