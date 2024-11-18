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
