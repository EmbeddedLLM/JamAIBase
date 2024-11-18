import { Base } from "@/resources/base";
import {
    ChatCompletionChunk,
    ChatCompletionChunkSchema,
    ChatRequest,
    ChatRequestSchema,
    References,
    ReferencesSchema,
    StreamChatCompletionChunk,
    StreamChatCompletionChunkSchema
} from "@/resources/llm/chat";
import { EmbeddingRequest, EmbeddingRequestSchema, EmbeddingResponse, EmbeddingResponseSchema } from "@/resources/llm/embedding";
import {
    ModelInfoRequest,
    ModelInfoResponse,
    ModelInfoResponseSchema,
    ModelNamesRequest,
    ModelNamesResponse,
    ModelNamesResponseSchema
} from "@/resources/llm/model";
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
                                    controller.enqueue(StreamChatCompletionChunkSchema.parse(parsedValue));
                                } else if (parsedValue["object"] === "chat.references") {
                                    controller.enqueue(ReferencesSchema.parse(parsedValue));
                                } else {
                                    throw new ChunkError(`Unexpected SSE Chunk: ${parsedValue}`);
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
                                controller.enqueue(StreamChatCompletionChunkSchema.parse(parsedValue));
                            } else if (parsedValue["object"] === "chat.references") {
                                controller.enqueue(ReferencesSchema.parse(parsedValue));
                            } else {
                                throw new ChunkError(`Unexpected SSE Chunk: ${parsedValue}`);
                            }
                        } catch (err: any) {
                            if (err instanceof ChunkError) {
                                controller.error(new ChunkError(err.message));
                            }
                        }
                    }
                });

                response.data.on("error", () => {
                    controller.error("Unexpected Error");
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
        let getURL = `/api/v1/models`;

        const response = await this.httpClient.get(getURL, {
            params: params,
            paramsSerializer: {
                indexes: false
            }
        });

        return this.handleResponse(response, ModelInfoResponseSchema);
    }

    public async modelNames(params?: ModelNamesRequest): Promise<ModelNamesResponse> {
        let getURL = `/api/v1/model_names`;

        const response = await this.httpClient.get(getURL, {
            params: params,
            paramsSerializer: {
                indexes: false
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
}
