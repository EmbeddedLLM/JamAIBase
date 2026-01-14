import { Base } from "@/resources/base";
import { serializeParams } from "@/helpers/utils";
import {
    AgentMetaResponse,
    AgentMetaResponseSchema,
    ConversationCreateRequest,
    ConversationCreateRequestSchema,
    ConversationMetaResponse,
    ConversationMetaResponseSchema,
    ConversationThreadsResponse,
    ConversationThreadsResponseSchema,
    ListConversationsParams,
    ListConversationsParamsSchema,
    ListMessagesParams,
    ListMessagesParamsSchema,
    MessageAddRequest,
    MessageAddRequestSchema,
    MessagesRegenRequest,
    MessagesRegenRequestSchema,
    MessageUpdateRequest,
    MessageUpdateRequestSchema,
    PageConversationMetaResponse,
    PageConversationMetaResponseSchema
} from "@/resources/conversations/types";
import {
    CellCompletionResponse,
    CellReferencesResponse,
    ColumnCompletionResponseSchema,
    RowReferencesResponseSchema
} from "@/resources/gen_tables/chat";
import { ChunkError } from "@/resources/shared/error";
import { OkResponse, OkResponseSchema } from "@/resources/shared/types";

export class Conversations extends Base {
    /**
     * Create a new conversation
     * @param request Conversation create request
     * @returns Stream of conversation metadata and message chunks
     */
    public async createConversation(
        request: ConversationCreateRequest
    ): Promise<ReadableStream<ConversationMetaResponse | CellCompletionResponse | CellReferencesResponse>> {
        const parsedRequest = ConversationCreateRequestSchema.parse(request);
        const response = await this.httpClient.post("/api/v2/conversations", parsedRequest, {
            responseType: "stream"
        });

        return this.handleConversationStreamResponse(response);
    }

    /**
     * List conversations
     * @param params Query parameters
     * @returns Paginated list of conversations
     */
    public async listConversations(params?: ListConversationsParams): Promise<PageConversationMetaResponse> {
        const parsedParams = ListConversationsParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/conversations/list", { params: parsedParams });

        return this.handleResponse(response, PageConversationMetaResponseSchema);
    }

    /**
     * List agents
     * @param params Query parameters
     * @returns Paginated list of agents
     */
    public async listAgents(params?: ListConversationsParams): Promise<PageConversationMetaResponse> {
        const parsedParams = ListConversationsParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/conversations/agents/list", { params: parsedParams });

        return this.handleResponse(response, PageConversationMetaResponseSchema);
    }

    /**
     * Get conversation by ID
     * @param conversationId Conversation ID
     * @returns Conversation metadata
     */
    public async getConversation(conversationId: string): Promise<ConversationMetaResponse> {
        const response = await this.httpClient.get("/api/v2/conversations", {
            params: { conversation_id: conversationId }
        });

        return this.handleResponse(response, ConversationMetaResponseSchema);
    }

    /**
     * Get agent by ID
     * @param agentId Agent ID
     * @returns Agent metadata
     */
    public async getAgent(agentId: string): Promise<AgentMetaResponse> {
        const response = await this.httpClient.get("/api/v2/conversations/agents", {
            params: { agent_id: agentId }
        });

        return this.handleResponse(response, AgentMetaResponseSchema);
    }

    /**
     * Generate title for conversation
     * @param conversationId Conversation ID
     * @returns Updated conversation metadata
     */
    public async generateTitle(conversationId: string): Promise<ConversationMetaResponse> {
        const response = await this.httpClient.post("/api/v2/conversations/title", null, {
            params: { conversation_id: conversationId }
        });

        return this.handleResponse(response, ConversationMetaResponseSchema);
    }

    /**
     * Rename conversation title
     * @param conversationId Conversation ID
     * @param title New title
     * @returns Updated conversation metadata
     */
    public async renameConversationTitle(conversationId: string, title: string): Promise<ConversationMetaResponse> {
        const response = await this.httpClient.patch("/api/v2/conversations/title", null, {
            params: { conversation_id: conversationId, title }
        });

        return this.handleResponse(response, ConversationMetaResponseSchema);
    }

    /**
     * Delete conversation
     * @param conversationId Conversation ID
     * @param missingOk If true, don't throw error if conversation doesn't exist
     * @returns Success response
     */
    public async deleteConversation(conversationId: string, missingOk: boolean = true): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/conversations", {
            params: { conversation_id: conversationId }
        });

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Send message to conversation
     * @param request Message add request
     * @returns Stream of message chunks
     */
    public async sendMessage(request: MessageAddRequest): Promise<ReadableStream<CellCompletionResponse | CellReferencesResponse>> {
        const parsedRequest = MessageAddRequestSchema.parse(request);
        const response = await this.httpClient.post("/api/v2/conversations/messages", parsedRequest, {
            responseType: "stream"
        });

        return this.handleMessageStreamResponse(response);
    }

    /**
     * List messages in conversation
     * @param conversationId Conversation ID
     * @param params Query parameters
     * @returns Paginated list of messages
     */
    public async listMessages(conversationId: string, params?: ListMessagesParams): Promise<any> {
        const parsedParams = ListMessagesParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/conversations/messages/list", {
            params: { conversation_id: conversationId, ...parsedParams }
        });

        return this.handleResponse(response);
    }

    /**
     * Regenerate message
     * @param request Message regen request
     * @returns Stream of regenerated message chunks
     */
    public async regenMessage(request: MessagesRegenRequest): Promise<ReadableStream<CellCompletionResponse | CellReferencesResponse>> {
        const parsedRequest = MessagesRegenRequestSchema.parse(request);
        const response = await this.httpClient.post("/api/v2/conversations/messages/regen", parsedRequest, {
            responseType: "stream"
        });

        return this.handleMessageStreamResponse(response);
    }

    /**
     * Update message
     * @param request Message update request
     * @returns Success response
     */
    public async updateMessage(request: MessageUpdateRequest): Promise<OkResponse> {
        const parsedRequest = MessageUpdateRequestSchema.parse(request);
        const response = await this.httpClient.patch("/api/v2/conversations/messages", parsedRequest);

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Get conversation threads
     * @param conversationId Conversation ID
     * @param columnIds Optional list of column IDs
     * @returns Conversation threads
     */
    public async getThreads(conversationId: string, columnIds?: string[]): Promise<ConversationThreadsResponse> {
        const response = await this.httpClient.get("/api/v2/conversations/threads", {
            params: {
                conversation_id: conversationId,
                column_ids: columnIds
            },
            paramsSerializer: serializeParams
        });

        return this.handleResponse(response, ConversationThreadsResponseSchema);
    }

    // Helper method for conversation stream (includes metadata event)
    private handleConversationStreamResponse(
        response: any
    ): ReadableStream<ConversationMetaResponse | CellCompletionResponse | CellReferencesResponse> {
        this.logWarning(response);

        if (response.status !== 200) {
            throw new Error(`Received Error Status: ${response.status}`);
        }

        let currentEvent: string | null = null;

        return new ReadableStream({
            async start(controller) {
                response.data.on("data", (data: any) => {
                    const lines = data
                        .toString()
                        .split("\n")
                        .filter((line: string) => line.trim());

                    for (const line of lines) {
                        if (line.startsWith("event:")) {
                            currentEvent = line.substring(6).trim();
                            continue;
                        }

                        if (line.startsWith("data:")) {
                            const chunk = line.substring(5).trim();

                            if (chunk === "[DONE]") continue;

                            try {
                                const parsedValue = JSON.parse(chunk);

                                if (currentEvent === "metadata") {
                                    controller.enqueue(ConversationMetaResponseSchema.parse(parsedValue));
                                    currentEvent = null;
                                } else if (parsedValue["object"] === "gen_table.completion.chunk") {
                                    controller.enqueue(ColumnCompletionResponseSchema.parse(parsedValue));
                                } else if (parsedValue["object"] === "gen_table.references") {
                                    controller.enqueue(RowReferencesResponseSchema.parse(parsedValue));
                                }
                            } catch (err: any) {
                                if (err instanceof ChunkError) {
                                    controller.error(err);
                                }
                            }
                        }
                    }
                });

                response.data.on("error", () => {
                    controller.error(new Error("Stream error"));
                });

                response.data.on("end", () => {
                    if (controller.desiredSize !== null) {
                        controller.close();
                    }
                });
            }
        });
    }

    // Helper method for message stream (no metadata event)
    private handleMessageStreamResponse(response: any): ReadableStream<CellCompletionResponse | CellReferencesResponse> {
        this.logWarning(response);

        if (response.status !== 200) {
            throw new Error(`Received Error Status: ${response.status}`);
        }

        return new ReadableStream({
            async start(controller) {
                response.data.on("data", (data: any) => {
                    const chunk = data
                        .toString()
                        .replace(/^data: /, "")
                        .replace(/data: \[DONE\]\s+$/, "")
                        .trim();

                    if (chunk === "[DONE]") return;

                    try {
                        const parsedValue = JSON.parse(chunk);

                        if (parsedValue["object"] === "gen_table.completion.chunk") {
                            controller.enqueue(ColumnCompletionResponseSchema.parse(parsedValue));
                        } else if (parsedValue["object"] === "gen_table.references") {
                            controller.enqueue(RowReferencesResponseSchema.parse(parsedValue));
                        }
                    } catch (err: any) {
                        if (err instanceof ChunkError) {
                            controller.error(err);
                        }
                    }
                });

                response.data.on("error", () => {
                    controller.error(new Error("Stream error"));
                });

                response.data.on("end", () => {
                    if (controller.desiredSize !== null) {
                        controller.close();
                    }
                });
            }
        });
    }
}
