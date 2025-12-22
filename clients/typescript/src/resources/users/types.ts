import { UserReadSchema } from "@/resources/auth/types";
import { PageSchema, PaginationParamsSchema } from "@/resources/shared/types";
import { z } from "zod";

/**
 * User update schema
 */
export const UserUpdateSchema = z.object({
    name: z.string().max(255).optional(),
    email: z.string().email().optional(),
    password: z.string().max(72).optional(),
    meta: z.record(z.any()).optional()
});

export type UserUpdate = z.infer<typeof UserUpdateSchema>;

/**
 * Project key (PAT) create schema
 */
export const ProjectKeyCreateSchema = z.object({
    name: z.string().max(255),
    project_id: z.string().optional(),
    expirty: z.string().optional(),
    meta: z.record(z.any()).optional()
});

export type ProjectKeyCreate = z.infer<typeof ProjectKeyCreateSchema>;

/**
 * Project key (PAT) read schema
 */
export const ProjectKeyReadSchema = z.object({
    id: z.string(),
    name: z.string(),
    user_id: z.string(),
    expirty: z.string().optional(),
    project_id: z.string().nullable(),
    created_at: z.string(),
    updated_at: z.string(),
    meta: z.record(z.any()).optional()
});

export type ProjectKeyRead = z.infer<typeof ProjectKeyReadSchema>;

/**
 * Project key update schema
 */
export const ProjectKeyUpdateSchema = z.object({
    name: z.string().max(255).optional(),
    meta: z.record(z.any()).optional()
});

export type ProjectKeyUpdate = z.infer<typeof ProjectKeyUpdateSchema>;

/**
 * Verification code read schema
 */
export const VerificationCodeReadSchema = z.object({
    id: z.string(),
    name: z.string().optional(),
    role: z.string().nullable().optional(),
    user_email: z.string().email(),
    expiry: z.string(),
    organization_id: z.string().nullable().optional(),
    project_id: z.string().nullable().optional(),
    purpose: z.string().nullable().optional(),
    used_at: z.string().nullable().optional(),
    revoked_at: z.string().nullable().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    meta: z.record(z.any()).optional()
});

export type VerificationCodeRead = z.infer<typeof VerificationCodeReadSchema>;

/**
 * List users params
 */
export const ListUsersParamsSchema = PaginationParamsSchema.extend({
    search_columns: z.array(z.string()).optional(),
    after: z.string().optional()
});

export type ListUsersParams = z.infer<typeof ListUsersParamsSchema>;

/**
 * List PATs params
 */
export const ListPatsParamsSchema = PaginationParamsSchema;

export type ListPatsParams = z.infer<typeof ListPatsParamsSchema>;

/**
 * List verification codes params
 */
export const ListVerificationCodesParamsSchema = PaginationParamsSchema;

export type ListVerificationCodesParams = z.infer<typeof ListVerificationCodesParamsSchema>;

// Page types
export const PageUserReadSchema = PageSchema(UserReadSchema);
export type PageUserRead = z.infer<typeof PageUserReadSchema>;

export const PageProjectKeyReadSchema = PageSchema(ProjectKeyReadSchema);
export type PageProjectKeyRead = z.infer<typeof PageProjectKeyReadSchema>;

export const PageVerificationCodeReadSchema = PageSchema(VerificationCodeReadSchema);
export type PageVerificationCodeRead = z.infer<typeof PageVerificationCodeReadSchema>;
