import { Base } from "@/resources/base";
import {
    ChatCompletionChunk,
    ChatCompletionChunkSchema,
    ChatRequest,
    ChatRequestSchema,
    References,
    StreamChatCompletionChunk
} from "@/resources/llm/chat";
import { EmbeddingRequest, EmbeddingRequestSchema, EmbeddingResponse, EmbeddingResponseSchema } from "@/resources/llm/embedding";
import {
    ModelInfoRequest,
    ModelInfoRequestSchema,
    ModelInfoResponse,
    ModelInfoResponseSchema,
    ModelNamesRequest,
    ModelNamesRequestSchema,
    ModelNamesResponse,
    ModelNamesResponseSchema
} from "@/resources/llm/model";
import {
    ModelIdsParams,
    ModelIdsParamsSchema,
    RerankingRequest,
    RerankingRequestSchema,
    RerankingResponse,
    RerankingResponseSchema
} from "@/resources/llm/reranking";
import { ChunkError } from "@/resources/shared/error";
import { AxiosResponse } from "axios";
import { z } from "zod";

export class LLM extends Base {
    // Helper method to handle chat stream responses
    private handleChatStreamResponse(response: AxiosResponse<any, any>): ReadableStream<StreamChatCompletionChunk | References> {
        this.logWarning(response);

        if (response.status != 200) {
            throw new Error(`Received Error Status: ${response.status}`);
        }
        return new ReadableStream<StreamChatCompletionChunk | References>({
            async start(controller: ReadableStreamDefaultController<StreamChatCompletionChunk | References>) {
                response.data.on("data", (data: any) => {
                    data = data.toString();
                    if (data.endsWith("\n\n")) {
                        const lines = data
                            .split("\n\n")
                            .filter((i: string) => i.trim())
                            .flatMap((line: string) => line.split("\n")); // Split by \n to handle collation

                        for (const line of lines) {
                            const chunk = line
                                .toString()
                                .replace(/^data: /, "")
                                .replace(/data: \[DONE\]\s+$/, "");

                            if (chunk.trim() === "[DONE]") return;

                            try {
                                const parsedValue = JSON.parse(chunk);
                                if (parsedValue["object"] === "chat.completion.chunk") {
                                    controller.enqueue(parsedValue as StreamChatCompletionChunk);
                                } else if (parsedValue["object"] === "chat.references") {
                                    controller.enqueue(parsedValue as References);
                                } else {
                                    throw new ChunkError(`Unexpected SSE Chunk object type: ${parsedValue["object"]}`);
                                }
                            } catch (err: any) {
                                if (err instanceof ChunkError) {
                                    controller.error(new ChunkError(err.message));
                                }
                                continue;
                            }
                        }
                    } else {
                        const chunk = data
                            .toString()
                            .replace(/^data: /, "")
                            .replace(/data: \[DONE\]\s+$/, "");

                        if (chunk.trim() === "[DONE]") return;

                        try {
                            const parsedValue = JSON.parse(chunk);
                            if (parsedValue["object"] === "chat.completion.chunk") {
                                controller.enqueue(parsedValue as StreamChatCompletionChunk);
                            } else if (parsedValue["object"] === "chat.references") {
                                controller.enqueue(parsedValue as References);
                            } else {
                                throw new ChunkError(`Unexpected SSE Chunk object type: ${parsedValue["object"]}`);
                            }
                        } catch (err: any) {
                            if (err instanceof ChunkError) {
                                controller.error(new ChunkError(err.message));
                            }
                            // Silently continue for JSON parse errors
                        }
                    }
                });

                response.data.on("error", (err: any) => {
                    controller.error(err || "Unexpected Error");
                });

                response.data.on("end", () => {
                    if (controller.desiredSize !== null) {
                        controller.close();
                    }
                });
            }
        });
    }

    public async modelInfo(params?: ModelInfoRequest): Promise<ModelInfoResponse> {
        const parsedParams = ModelInfoRequestSchema.parse(params ?? {});
    
        const getURL = `/api/v1/models`;
    
        const response = await this.httpClient.get(getURL, {
            params: parsedParams,
            paramsSerializer: (params) => {
                const searchParams = new URLSearchParams();
              
                Object.entries(params).forEach(([key, value]) => {
                  if (Array.isArray(value)) {
                    value.forEach(v => searchParams.append(key, String(v)));
                  } else if (value !== undefined && value !== null) {
                    searchParams.append(key, String(value));
                  }
                });
              
                return searchParams.toString();
              }
              
        });
    
        return this.handleResponse(response, ModelInfoResponseSchema);
    }
    

    public async modelNames(params?: ModelNamesRequest): Promise<ModelNamesResponse> {
        const parsedParams = ModelNamesRequestSchema.parse(params ?? {});

        const getURL = `/api/v1/model_names`;

        const response = await this.httpClient.get(getURL, {
            params: parsedParams,
            paramsSerializer: (params) => {
                const searchParams = new URLSearchParams();
              
                Object.entries(params).forEach(([key, value]) => {
                  if (Array.isArray(value)) {
                    value.forEach(v => searchParams.append(key, String(v)));
                  } else if (value !== undefined && value !== null) {
                    searchParams.append(key, String(value));
                  }
                });
              
                return searchParams.toString();
              }
        });

        return this.handleResponse(response, ModelNamesResponseSchema);
    }

    public async generateChatCompletionsStream(params: ChatRequest): Promise<ReadableStream<StreamChatCompletionChunk | References>> {
        const parsedParams = ChatRequestSchema.parse(params);
        parsedParams.stream = true;
        const apiURL = "/api/v1/chat/completions";
        const response = await this.httpClient.post(apiURL, parsedParams, {
            responseType: "stream"
        });

        return this.handleChatStreamResponse(response);
    }

    public async generateChatCompletions(params: ChatRequest): Promise<ChatCompletionChunk> {
        const parsedParams = ChatRequestSchema.parse(params);
        parsedParams.stream = false;

        const apiURL = "/api/v1/chat/completions";

        const response = await this.httpClient.post<ChatCompletionChunk>(apiURL, parsedParams, {});

        return this.handleResponse(response, ChatCompletionChunkSchema);
    }

    public async generateEmbeddings(params: z.input<typeof EmbeddingRequestSchema>): Promise<EmbeddingResponse> {
        const apiURL = "/api/v1/embeddings";

        const parsedParams = EmbeddingRequestSchema.parse(params);

        const response = await this.httpClient.post<EmbeddingRequest>(apiURL, {
            ...parsedParams
        });

        return this.handleResponse(response, EmbeddingResponseSchema);
    }

    /**
     * Get list of available model IDs
     * @param params Query parameters
     * @returns List of model IDs
     */
    public async modelIds(params?: ModelIdsParams): Promise<string[]> {
        const parsedParams = ModelIdsParamsSchema.parse(params ?? {});

        const response = await this.httpClient.get("/api/v1/models/ids", {
            params: parsedParams,
            paramsSerializer: (params) => {
                const searchParams = new URLSearchParams();
              
                Object.entries(params).forEach(([key, value]) => {
                  if (Array.isArray(value)) {
                    value.forEach(v => searchParams.append(key, String(v)));
                  } else if (value !== undefined && value !== null) {
                    searchParams.append(key, String(value));
                  }
                });
              
                return searchParams.toString();
              }
        });

        return this.handleResponse(response);
    }

    /**
     * Rerank documents based on relevance to query
     * @param params Reranking request
     * @returns Reranking response with relevance scores
     */
    public async rerank(params: RerankingRequest): Promise<RerankingResponse> {
        const parsedParams = RerankingRequestSchema.parse(params);
        const response = await this.httpClient.post("/api/v1/rerank", parsedParams);

        return this.handleResponse(response, RerankingResponseSchema);
    }
}
