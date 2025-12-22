import { z } from "zod";

/**
 * Generic pagination response
 */
export const PageSchema = <T extends z.ZodTypeAny>(itemSchema: T) =>
    z.object({
        items: z.array(itemSchema),
        offset: z.number(),
        limit: z.number(),
        total: z.number()
    });

export type Page<T> = {
    items: T[];
    offset: number;
    limit: number;
    total: number;
};

/**
 * Role enum
 */
export const RoleSchema = z.enum(["ADMIN", "MEMBER", "GUEST"]);
export type Role = z.infer<typeof RoleSchema>;

/**
 * Common pagination parameters
 */
export const PaginationParamsSchema = z.object({
    offset: z.number().optional(),
    limit: z.number().optional(),
    order_by: z.string().optional(),
    order_ascending: z.boolean().optional(),
    search_query: z.string().optional()
});

export type PaginationParams = z.infer<typeof PaginationParamsSchema>;

/**
 * OK Response
 */
export const OkResponseSchema = z.object({
    ok: z.boolean().default(true),
    progress_key: z.string().optional()
});

export type OkResponse = z.infer<typeof OkResponseSchema>;
