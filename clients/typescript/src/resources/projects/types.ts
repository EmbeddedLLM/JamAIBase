import { OrgInviteCodeReadSchema, UserSchema } from "@/resources/organizations/types";
import { PageSchema, PaginationParamsSchema, RoleSchema } from "@/resources/shared/types";
import { z } from "zod";

/**
 * Project create schema
 */
export const ProjectCreateSchema = z.object({
    organization_id: z.string(),
    name: z.string().max(255),
    description: z.string().optional(),
    tags: z.array(z.string()).optional(),
    profile_picture_url: z.string().nullable().optional(),
    cover_picture_url: z.string().nullable().optional(),
    meta: z.record(z.any()).optional()
});

export type ProjectCreate = z.infer<typeof ProjectCreateSchema>;

/**
 * Project update schema
 */
export const ProjectUpdateSchema = z.object({
    name: z.string().max(255).optional(),
    description: z.string().optional(),
    tags: z.array(z.string()).optional(),
    profile_picture_url: z.string().nullable().optional(),
    cover_picture_url: z.string().nullable().optional(),
    meta: z.record(z.any()).optional()
});

export type ProjectUpdate = z.infer<typeof ProjectUpdateSchema>;

/**
 * Project read schema
 */
export const ProjectReadSchema = z.object({
    id: z.string(),
    organization_id: z.string(),
    name: z.string(),
    description: z.string().optional(),
    tags: z.array(z.string()).optional(),
    profile_picture_url: z.string().nullable().optional(),
    cover_picture_url: z.string().nullable().optional(),
    created_by: z.string(),
    owner: z.string(),
    organization: z.any().optional(),
    chat_agents: z.array(z.any()).nullable().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    meta: z.record(z.any()).optional()
});

export type ProjectRead = z.infer<typeof ProjectReadSchema>;

/**
 * Project member read schema
 */
export const ProjectMemberReadSchema = z.object({
    user_id: z.string(),
    project_id: z.string(),
    role: RoleSchema,
    user: UserSchema,
    project: z.any(),
    created_at: z.string(),
    updated_at: z.string(),
    meta: z.record(z.any()).optional()
});

export type ProjectMemberRead = z.infer<typeof ProjectMemberReadSchema>;

/**
 * List projects params
 */
export const ListProjectsParamsSchema = PaginationParamsSchema.extend({
    list_chat_agents: z.boolean().optional()
});


/**
 * Project invite
 */
export const ProjInviteCodeRequestSchema = z.object({
    user_email: z.string(),
    project_id: z.string(),
    role: RoleSchema,
    valid_days: z.number()
})

export const ProjInviteCodeReadSchema = OrgInviteCodeReadSchema.extend({})

export type ProjInviteCodeRequest = z.infer<typeof ProjInviteCodeRequestSchema>;
export type ProjInviteCodeRead = z.infer<typeof ProjInviteCodeReadSchema>;

export type ListProjectsParams = z.infer<typeof ListProjectsParamsSchema>;

/**
 * List members params
 */
export const ListProjectMembersParamsSchema = PaginationParamsSchema;

export type ListProjectMembersParams = z.infer<typeof ListProjectMembersParamsSchema>;

/**
 * List invites params
 */
export const ListProjectInvitesParamsSchema = PaginationParamsSchema;

export type ListProjectInvitesParams = z.infer<typeof ListProjectInvitesParamsSchema>;

// Page types
export const PageProjectReadSchema = PageSchema(ProjectReadSchema);
export type PageProjectRead = z.infer<typeof PageProjectReadSchema>;

export const PageProjectMemberReadSchema = PageSchema(ProjectMemberReadSchema);
export type PageProjectMemberRead = z.infer<typeof PageProjectMemberReadSchema>;

export const PageProjectInviteCodeReadSchema = PageSchema(OrgInviteCodeReadSchema);
export type PageProjectInviteCodeRead = z.infer<typeof PageProjectInviteCodeReadSchema>;
