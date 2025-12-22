import { z } from "zod";

/**
 * Progress state constants
 * Matches Python client: STARTED, COMPLETED, FAILED
 */
export const PROGRESS_STATES = {
    STARTED: "STARTED" as const,
    COMPLETED: "COMPLETED" as const,
    FAILED: "FAILED" as const
} as const;

/**
 * Progress state enum
 */
export const ProgressStateSchema = z.enum(["STARTED", "COMPLETED", "FAILED"]);
export type ProgressState = z.infer<typeof ProgressStateSchema>;

/**
 * Progress response schema
 */
export const ProgressResponseSchema = z.object({
    state: ProgressStateSchema.optional(),
    error: z.string().nullable().optional(),
    data: z.any().optional()
});

export type ProgressResponse = z.infer<typeof ProgressResponseSchema>;

/**
 * Poll progress params
 */
export const PollProgressParamsSchema = z.object({
    initialWait: z.number().optional(),
    maxWait: z.number().optional(),
    verbose: z.boolean().optional()
});

export type PollProgressParams = z.infer<typeof PollProgressParamsSchema>;
