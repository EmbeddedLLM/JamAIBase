import { PageSchema, PaginationParamsSchema, RoleSchema } from "@/resources/shared/types";
import { z } from "zod";

/**
 * Organization create schema
 */
export const OrganizationCreateSchema = z.object({
    name: z.string().max(255),
    timezone: z.string().nullable().optional(),
    external_keys: z.record(z.string()).optional(),
    meta: z.record(z.any()).optional()
});

export type OrganizationCreate = z.infer<typeof OrganizationCreateSchema>;

/**
 * Organization update schema
 */
export const OrganizationUpdateSchema = z.object({
    name: z.string().max(255).optional(),
    timezone: z.string().nullable().optional(),
    external_keys: z.record(z.string()).optional(),
    meta: z.record(z.any()).optional()
});

export type OrganizationUpdate = z.infer<typeof OrganizationUpdateSchema>;

/**
 * Organization read schema
 */
export const OrganizationReadSchema = z.object({
    id: z.string(),
    name: z.string(),
    timezone: z.string().nullable().optional(),
    external_keys: z.record(z.string()).optional(),
    currency: z.string(),
    created_by: z.string(),
    owner: z.string(),
    stripe_id: z.string().nullable().optional(),
    price_plan_id: z.string().nullable().optional(),
    payment_state: z.enum(["NONE", "SUCCESS", "PROCESSING", "FAILED"]),
    last_subscription_payment_at: z.string().nullable().optional(),
    quota_reset_at: z.string(),
    credit: z.number(),
    credit_grant: z.number(),
    llm_tokens_quota_mtok: z.number().nullable().optional(),
    llm_tokens_usage_mtok: z.number(),
    embedding_tokens_quota_mtok: z.number().nullable().optional(),
    embedding_tokens_usage_mtok: z.number(),
    reranker_quota_ksearch: z.number().nullable().optional(),
    reranker_usage_ksearch: z.number(),
    db_quota_gib: z.number().nullable().optional(),
    db_usage_gib: z.number(),
    db_usage_updated_at: z.string(),
    file_quota_gib: z.number().nullable().optional(),
    file_usage_gib: z.number(),
    file_usage_updated_at: z.string(),
    egress_quota_gib: z.number().nullable().optional(),
    egress_usage_gib: z.number(),
    active: z.boolean(),
    quotas: z.record(z.record(z.number().nullable())),
    price_plan: z.any().nullable().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    meta: z.record(z.any()).optional()
});

export type OrganizationRead = z.infer<typeof OrganizationReadSchema>;

/**
 * User schema (simplified for member responses)
 */
export const UserSchema = z.object({
    id: z.string(),
    email: z.string().email(),
    name: z.string().optional(),
    email_verified: z.boolean().optional(),
    created_at: z.string().optional(),
    updated_at: z.string().optional()
}).passthrough();

/**
 * Organization member read schema
 */
export const OrgMemberReadSchema = z.object({
    user_id: z.string(),
    organization_id: z.string(),
    role: RoleSchema,
    user: UserSchema,
    organization: z.any(),
    created_at: z.string(),
    updated_at: z.string(),
    meta: z.record(z.any()).optional()
});

export type OrgMemberRead = z.infer<typeof OrgMemberReadSchema>;

/**
 * Verification code read schema (for invites)
 */

export const OrgInviteCodeRequestSchema = z.object({
    user_email: z.string(),
    organization_id: z.string(),
    role: RoleSchema,
    valid_days: z.number()
})

export const OrgInviteCodeReadSchema = z.object({
    created_at: z.string(),
    updated_at: z.string(),
    meta: z.record(z.any()).optional(),
    name: z.string(),
    role: z.union([z.string(), z.null()]),
    user_email: z.union([z.string().email(), z.null()]),
    expiry: z.string(),
    organization_id: z.union([z.string(), z.null()]),
    project_id: z.union([z.string(), z.null()]),
    id: z.string(),
    purpose: z.union([z.string(), z.null()]),
    used_at: z.union([z.string(), z.null()]),
    revoked_at: z.union([z.string(), z.null()])
});

export type OrgInviteCodeRead = z.infer<typeof OrgInviteCodeReadSchema>;
export type OrgInviteCodeRequest = z.infer<typeof OrgInviteCodeRequestSchema>;

/**
 * Model config read schema (for catalogue)
 */
export const ModelConfigReadSchema = z.object({
    id: z.string(),
    name: z.string(),
    owned_by: z.string(),
    capabilities: z.array(z.string()).optional(),
    context_length: z.number().optional(),
    languages: z.array(z.string()).optional(),
    created_at: z.string().optional(),
    updated_at: z.string().optional()
});

export type ModelConfigRead = z.infer<typeof ModelConfigReadSchema>;

/**
 * Stripe payment info schema
 */
export const StripePaymentInfoSchema = z.object({
    status: z.string(),
    subscription_id: z.string().nullable().optional(),
    payment_intent_id: z.string().nullable().optional(),
    client_secret: z.string().nullable().optional(),
    amount_due: z.number(),
    amount_overpaid: z.number(),
    amount_paid: z.number(),
    amount_remaining: z.number(),
    currency: z.string()
});

export type StripePaymentInfo = z.infer<typeof StripePaymentInfoSchema>;

/**
 * List organizations params
 */
export const ListOrganizationsParamsSchema = PaginationParamsSchema;

export type ListOrganizationsParams = z.infer<typeof ListOrganizationsParamsSchema>;

/**
 * List members params
 */
export const ListMembersParamsSchema = PaginationParamsSchema;

export type ListMembersParams = z.infer<typeof ListMembersParamsSchema>;

/**
 * List invites params
 */
export const ListInvitesParamsSchema = PaginationParamsSchema;

export type ListInvitesParams = z.infer<typeof ListInvitesParamsSchema>;

/**
 * Model catalogue params
 */
export const ModelCatalogueParamsSchema = PaginationParamsSchema;

export type ModelCatalogueParams = z.infer<typeof ModelCatalogueParamsSchema>;

// Page types
export const PageOrganizationReadSchema = PageSchema(OrganizationReadSchema);
export type PageOrganizationRead = z.infer<typeof PageOrganizationReadSchema>;

export const PageOrgMemberReadSchema = PageSchema(OrgMemberReadSchema);
export type PageOrgMemberRead = z.infer<typeof PageOrgMemberReadSchema>;

export const PageInviteCodeReadSchema = PageSchema(OrgInviteCodeReadSchema);
export type PageInviteCodeRead = z.infer<typeof PageInviteCodeReadSchema>;

export const PageModelConfigReadSchema = PageSchema(ModelConfigReadSchema);
export type PageModelConfigRead = z.infer<typeof PageModelConfigReadSchema>;
