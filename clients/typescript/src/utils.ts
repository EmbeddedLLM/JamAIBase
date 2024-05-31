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
