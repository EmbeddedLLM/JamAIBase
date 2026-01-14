import Agent from "agentkeepalive";
import { ZodObject, ZodRawShape, z } from "zod";

export function createHttpAgent(payload: Agent.HttpOptions = { maxFreeSockets: 10, freeSocketTimeout: 20000 }) {
    return new Agent(payload);
}

export function createHttpsAgent(payload: Agent.HttpOptions = { maxFreeSockets: 10, freeSocketTimeout: 20000 }) {
    return new Agent.HttpsAgent(payload);
}

export function applyMixins(derivedCtor: any, constructors: any[]) {
    constructors.forEach((baseCtor) => {
        Object.getOwnPropertyNames(baseCtor.prototype).forEach((name) => {
            Object.defineProperty(derivedCtor.prototype, name, Object.getOwnPropertyDescriptor(baseCtor.prototype, name) || Object.create(null));
        });
    });
}

// https://github.com/colinhacks/zod/issues/2938

// Custom passthrough function for zod schema
export const passthrough = <T extends ZodRawShape>(schema: ZodObject<T>) => {
    return schema.and(z.record(z.string(), z.any()));
};

export const isRunningInBrowser = () => {
    return (
        // @ts-ignore
        typeof window !== "undefined" &&
        // @ts-ignore
        typeof window.document !== "undefined" &&
        // @ts-ignore
        typeof navigator !== "undefined"
    );
};

// Define a generic function to create a pagination schema
export function createPaginationSchema<T>(itemSchema: z.ZodType<T>) {
    return passthrough(
        z.object({
            items: z.array(itemSchema).describe("List of items paginated items.").default([]),
            offset: z.number().describe("Number of skipped items.").default(0),
            limit: z.number().describe("Number of items per page.").default(100),
            total: z.number().describe("Total number of items.").default(0)
        })
    );
}

/**
 * Serializes query parameters for axios requests, properly handling arrays and skipping null/undefined values.
 * This prevents null/undefined values from being sent as literal strings (e.g., "columns=null").
 *
 * @param params - The query parameters object to serialize
 * @returns URL-encoded query string
 *
 * @example
 * serializeParams({ foo: 'bar', list: [1, 2], skip: null })
 * // Returns: "foo=bar&list=1&list=2"
 */
export function serializeParams(params: Record<string, any>): string {
    return Object.entries(params)
        .flatMap(([key, value]) =>
            Array.isArray(value)
                ? value.map((val) => `${encodeURIComponent(key)}=${encodeURIComponent(val)}`)
                : value !== undefined && value !== null
                ? `${encodeURIComponent(key)}=${encodeURIComponent(value)}`
                : []
        )
        .join("&");
}
