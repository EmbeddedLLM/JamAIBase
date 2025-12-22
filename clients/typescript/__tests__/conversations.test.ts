import JamAI from "@/index";
import { beforeAll, describe, expect, it, jest } from "@jest/globals";
import dotenv from "dotenv";
import { v4 as uuidv4 } from "uuid";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

let llmModel: string;
let testAgentId: string | null = null;

describe("APIClient Conversations", () => {
    let client: JamAI;
    let testContext: TestContext;
    jest.setTimeout(30000);
    jest.retryTimes(1, {
        logErrorsBeforeRetry: true
    });

    beforeAll(async () => {
        // prepare environment
        testContext = await setupTestEnvironment({ createModels: true });
        client = testContext.client;

        // Get the completion model as used in llm.test.ts
        if (testContext.modelConfigs) {
            llmModel = testContext.modelConfigs.completionModelId;
        } else {
            // fallback in rare case setupTestEnvironment didn't set models
            const models = await client.llm.modelInfo();
            const selectedLlmModel = models.data.find((model: any) => model.capabilities?.includes("chat"));
            llmModel = selectedLlmModel?.id ? selectedLlmModel.id : "openai/gpt-4o-mini";
        }

        // Create the agent/chat table using a real model as in llm.test.ts
        const agent = await client.table.createChatTable({
            id: "test-agent",
            cols: [
                {
                    id: "User",
                    dtype: "str"
                },
                {
                    id: "AI",
                    dtype: "str",
                    gen_config: {
                        model: llmModel,
                        system_prompt: ""
                    }
                }
            ]
        });

        testAgentId = agent.id;
    });

    afterAll(async function () {
        await cleanupTestEnvironment(testContext);

        await client.table.deleteTable({
            table_type: "chat",
            table_id: testAgentId!
        });
    });

    async function* _getConversation() {
        if (!testAgentId) {
            throw new Error("No agent available for conversation tests");
        }

        const conversationTitle = `Test Conversation ${uuidv4().substring(0, 8)}`;

        const stream = await client.conversations.createConversation({
            agent_id: testAgentId,
            title: conversationTitle,
            data: {}
        });

        let conversationId: string | null = null;

        // Read the stream to get conversation ID
        const reader = stream.getReader();
        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                if (value && typeof value === "object" && "conversation_id" in value) {
                    conversationId = value.conversation_id as string;
                    break;
                }
            }
        } finally {
            reader.releaseLock();
        }

        if (!conversationId) {
            throw new Error("Failed to create conversation");
        }

        try {
            yield { conversation_id: conversationId, title: conversationTitle };
        } finally {
            // Cleanup
            await client.conversations.deleteConversation(conversationId);
        }
    }

    it("list agents - without limit and offset", async () => {
        const response = await client.conversations.listAgents({});

        expect(response).toHaveProperty("items");
        expect(Array.isArray(response.items)).toBe(true);
        expect(response).toHaveProperty("offset");
        expect(response).toHaveProperty("limit");
        expect(response).toHaveProperty("total");
    });

    it("list agents - with limit", async () => {
        const limit = 2;
        const response = await client.conversations.listAgents({ limit });

        expect(response.items.length).toBeLessThanOrEqual(limit);
        expect(response.limit).toEqual(limit);
    });

    it("get agent", async () => {
        if (!testAgentId) {
            console.warn("Get agent test skipped: No agent available");
            return;
        }

        const response = await client.conversations.getAgent(testAgentId);

        expect(response).toHaveProperty("agent_id");
        expect(response.agent_id).toEqual(testAgentId);
        expect(response).toHaveProperty("title");
        expect(response).toHaveProperty("cols");
    });

    it("create conversation - streaming", async () => {
        const conversationTitle = `Test Conversation ${uuidv4().substring(0, 8)}`;

        const stream = await client.conversations.createConversation({
            agent_id: testAgentId!,
            title: conversationTitle,
            data: {}
        });

        expect(stream).toBeInstanceOf(ReadableStream);

        let conversationId: string | null = null;
        const reader = stream.getReader();

        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                if (value && typeof value === "object" && "conversation_id" in value) {
                    conversationId = value.conversation_id as string;
                }
            }
        } finally {
            reader.releaseLock();
        }

        expect(conversationId).toBeTruthy();

        // Cleanup
        if (conversationId) {
            await client.conversations.deleteConversation(conversationId);
        }
    });

    it("list conversations - without limit and offset", async () => {
        const response = await client.conversations.listConversations({});

        expect(response).toHaveProperty("items");
        expect(Array.isArray(response.items)).toBe(true);
        expect(response).toHaveProperty("offset");
        expect(response).toHaveProperty("limit");
        expect(response).toHaveProperty("total");
    });

    it("list conversations - with limit", async () => {
        const limit = 2;
        const response = await client.conversations.listConversations({ limit });

        expect(response.items.length).toBeLessThanOrEqual(limit);
        expect(response.limit).toEqual(limit);
    });

    it("get conversation", async () => {
        for await (const conversation of _getConversation()) {
            const response = await client.conversations.getConversation(conversation.conversation_id);

            expect(response).toHaveProperty("conversation_id");
            expect(response.conversation_id).toEqual(conversation.conversation_id);
            expect(response).toHaveProperty("title");
        }
    });

    it("rename conversation title", async () => {
        for await (const conversation of _getConversation()) {
            const updatedTitle = `Updated Title ${uuidv4().substring(0, 8)}`;

            const response = await client.conversations.renameConversationTitle(conversation.conversation_id, updatedTitle);

            expect(response).toHaveProperty("conversation_id");
            expect(response.conversation_id).toEqual(conversation.conversation_id);
            expect(response).toHaveProperty("title");
            expect(response.title).toEqual(updatedTitle);
        }
    });

    it("delete conversation", async () => {
        const conversationTitle = `Test Conversation ${uuidv4().substring(0, 8)}`;
        const stream = await client.conversations.createConversation({
            agent_id: testAgentId!,
            title: conversationTitle,
            data: {}
        });

        let conversationId: string | null = null;
        const reader = stream.getReader();

        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                if (value && typeof value === "object" && "conversation_id" in value) {
                    conversationId = value.conversation_id as string;
                    break;
                }
            }
        } finally {
            reader.releaseLock();
        }

        if (conversationId) {
            const deleteResponse = await client.conversations.deleteConversation(conversationId);

            expect(deleteResponse).toHaveProperty("ok");
            expect(deleteResponse.ok).toBeTruthy();

            // Verify conversation is deleted
            const listResponse = await client.conversations.listConversations({});
            const foundConversation = listResponse.items.find((item) => item.conversation_id === conversationId);
            expect(foundConversation).toBeUndefined();
        }
    });


    it("send message - streaming", async () => {
        for await (const conversation of _getConversation()) {
            const stream = await client.conversations.sendMessage({
                conversation_id: conversation.conversation_id,
                data: { User: "Hello, What's the capital of Bangladesh?" }
            });

            expect(stream).toBeInstanceOf(ReadableStream);

            const reader = stream.getReader();
            let chunkCount = 0;

            try {
                while (true) {
                    const { done, value } = await reader.read();

                    if (done) break;
                    chunkCount++;
                }
            } finally {
                reader.releaseLock();
            }

            expect(chunkCount).toBeGreaterThan(0);
        }
    });

    it("list messages", async () => {
        for await (const conversation of _getConversation()) {
            const response = await client.conversations.listMessages(conversation.conversation_id, {});

            expect(response).toBeDefined();
        }
    });

    it("get conversation threads", async () => {
        for await (const conversation of _getConversation()) {
            const response = await client.conversations.getThreads(conversation.conversation_id);

            expect(response).toHaveProperty("threads");
            expect(typeof response.threads).toBe("object");
        }
    });
});
