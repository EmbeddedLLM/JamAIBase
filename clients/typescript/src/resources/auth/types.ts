import { z } from "zod";

/**
 * User create request schema
 */
export const UserCreateSchema = z.object({
    id: z.string().optional(),
    name: z.string().max(255),
    email: z.string().email(),
    password: z.string().max(72)
});

export type UserCreate = z.infer<typeof UserCreateSchema>;

/**
 * Password login request schema
 */
export const PasswordLoginRequestSchema = z.object({
    email: z.string().email(),
    password: z.string().min(1).max(72)
});

export type PasswordLoginRequest = z.infer<typeof PasswordLoginRequestSchema>;

/**
 * Password change request schema
 */
export const PasswordChangeRequestSchema = z.object({
    email: z.string().email(),
    password: z.string().min(1).max(72),
    new_password: z.string().min(1).max(72)
});

export type PasswordChangeRequest = z.infer<typeof PasswordChangeRequestSchema>;

/**
 * User read response schema
 */
export const UserReadSchema = z.object({
    id: z.string(),
    name: z.string(),
    email: z.string().email(),
    email_verified: z.boolean(),
    created_at: z.string(),
    updated_at: z.string(),
    preferred_name: z.string().optional(),
    preferred_email: z.string().optional(),
    preferred_picture_url: z.string().nullable().optional(),
    preferred_username: z.string().nullable().optional(),
    org_memberships: z.array(z.any()).optional(),
    proj_memberships: z.array(z.any()).optional(),
    organizations: z.array(z.any()).optional(),
    projects: z.array(z.any()).optional(),
    meta: z.record(z.any()).optional()
});

export type UserRead = z.infer<typeof UserReadSchema>;
