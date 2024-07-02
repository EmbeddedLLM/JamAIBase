import { z } from "zod";
import { ChatCompletionUsageSchema } from "./chat";

export const EmbeddingRequestSchema = z.object({
    input: z
        .union([z.string(), z.array(z.string())])
        .describe(
            "Input text to embed, encoded as a string or array of strings (to embed multiple inputs in a single request). The input must not exceed the max input tokens for the model, and cannot contain empty string."
        ),
    model: z.string().describe("The ID of the model to use. You can use the List models API to see all of your available models."),
    type: z
        .enum(["query", "document"])
        .default("document")
        .describe('Whether the input text is a "query" (used to retrieve) or a "document" (to be retrieved).'),

    encoding_format: z
        .enum(["float", "base64"])
        .default("float")
        .describe(
            '_Optional_. The format to return the embeddings in. Can be either "float" or "base64". `base64` string should be decoded as a `float32` array. Example: `np.frombuffer(base64.b64decode(response), dtype=np.float32)`'
        )
});

export const EmbeddingResponseDataSchema = z.object({
    object: z.string().default("embedding").describe("The object type, which is always `embedding`."),

    embedding: z
        .union([z.array(z.number()), z.string()])
        .describe("The embedding vector, which is a list of floats or a base64-encoded string. The length of the vector depends on the model."),

    index: z.number().default(0).describe("The index of the embedding in the list of embeddings.")
});

export const EmbeddingResponseSchema = z.object({
    object: z.string().default("list").describe("The object type, which is always `list`."),

    data: z.array(EmbeddingResponseDataSchema).describe("List of `EmbeddingResponseData`."),
    model: z.string().describe("The ID of the model used."),

    usage: ChatCompletionUsageSchema.default({
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0
    }).describe("The number of tokens consumed.")
});

export type EmbeddingRequest = z.infer<typeof EmbeddingRequestSchema>;
export type EmbeddingResponse = z.infer<typeof EmbeddingResponseSchema>;
