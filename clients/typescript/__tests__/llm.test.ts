import JamAI from "@/index";
import { ChatCompletionChunkSchema, ChatRequest } from "@/resources/llm/chat";
import { EmbeddingResponseSchema } from "@/resources/llm/embedding";
import { ModelInfoResponseSchema, ModelNamesResponseSchema } from "@/resources/llm/model";
import dotenv from "dotenv";
import { cleanupTestEnvironment, isApiKeyError, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

let llmModel: string;
let embeddingModel: string;
let embeddingModels: string[];

describe("APIClient LLM", () => {
    let client: JamAI;
    let testContext: TestContext;
    jest.setTimeout(30000);
    jest.retryTimes(1, {
        logErrorsBeforeRetry: true
    });

    let requestDataChat: ChatRequest;

    beforeAll(async () => {
        testContext = await setupTestEnvironment({ createModels: true });
        client = testContext.client;

        // Use pre-created models from testContext
        if (testContext.modelConfigs) {
            llmModel = testContext.modelConfigs.completionModelId;
            embeddingModel = testContext.modelConfigs.embeddingModelId;
            embeddingModels = [embeddingModel];

        } else {
            // Fallback to dynamic model lookup (shouldn't happen if createModels: true)
            const models = await client.llm.modelInfo();

            const selectedLlmModel = models.data.find((model) => model.capabilities.includes("chat"));
            llmModel = selectedLlmModel?.id ? selectedLlmModel.id : "openai/gpt-4o-mini";

            // Store all embedding models
            const allEmbeddingModels = models.data.filter((model) => model.capabilities.includes("embed"));
            embeddingModels = allEmbeddingModels.length > 0
                ? allEmbeddingModels.map((model) => model.id)
                : ["ellm/sentence-transformers/all-MiniLM-L6-v2"];

            // Set the first one as default
            embeddingModel = embeddingModels[0]!;

            console.log("Available embedding models: ", embeddingModels);
            console.log("Default embedding model: ", embeddingModel);
        }

        requestDataChat = {
            model: llmModel,
            messages: [
                { role: "system", content: "you are a helpful assistant." },
                { role: "user", content: "Hello, what is the capital of Bangladesh?" }
            ],
            max_tokens: 100,
            temperature: 0.1,
            top_p: 0.1,
            presence_penalty: 0,
            frequency_penalty: 0,
            logit_bias: undefined
        };
    });

    afterAll(async function () {
        await cleanupTestEnvironment(testContext);
    });

    it("get model info", async () => {
        const response = await client.llm.modelInfo();

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model info with 'chat' capabilities", async () => {
        const response = await client.llm.modelInfo({
            capabilities: ["chat"]
        });

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);


        // Assert all models have the 'chat' capability and no others are included
        expect(parsedData.data.length).toBeGreaterThan(0);
        for (const model of parsedData.data) {
            expect(model.capabilities).toContain("chat");
            // Optionally ensure "chat" is the only capability, if that's expected
            // expect(model.capabilities).toEqual(expect.arrayContaining(["chat"]));
        }
    });

    it("get model info with 'embed' capabilities", async () => {
        const response = await client.llm.modelInfo({
            capabilities: ["embed"]
        });

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);

        expect(parsedData.data.length).toBeGreaterThan(0);
        for (const model of parsedData.data) {
            expect(model.capabilities).toContain("embed");
        }
    });

    it("get model info with 'image' capabilities", async () => {
        const response = await client.llm.modelInfo({
            capabilities: ["image"]
        });

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);

        // No model should have capabilities excluding "image"
        for (const model of parsedData.data) {
            expect(model.capabilities).toContain("image");
        }
    });

    it("get model info with 'rerank' capabilities", async () => {
        const response = await client.llm.modelInfo({
            capabilities: ["rerank"]
        });

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);

        // No model should have capabilities excluding "image"
        for (const model of parsedData.data) {
            expect(model.capabilities).toContain("rerank");
        }
    });

    it("get model info with multiple capabilities", async () => {
        const response = await client.llm.modelInfo({
            capabilities: ["embed", "chat"]
        });

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);

        // Each model must have both capabilities
        for (const model of parsedData.data) {
            expect(model.capabilities).toEqual(expect.arrayContaining(["embed", "chat"]));
        }
    });


    it("get model info with name", async () => {
        const response = await client.llm.modelInfo({
            model: llmModel
        });

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model info with both params", async () => {
        const response = await client.llm.modelInfo({
            model: llmModel,
            capabilities: ["chat"]
        });

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model name", async () => {
        const response = await client.llm.modelNames();

        const parsedData = ModelNamesResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model name with capabilities", async () => {
        const response = await client.llm.modelNames({
            capabilities: ["image"]
        });

        const parsedData = ModelNamesResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model info with prefer", async () => {
        const response = await client.llm.modelNames({
            prefer: llmModel
        });


        const parsedData = ModelNamesResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model info with both params", async () => {
        const response = await client.llm.modelNames({
            prefer: llmModel,
            capabilities: ["chat"]
        });

        const parsedData = ModelNamesResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("generate chat completion", async () => {
        const response = await client.llm.generateChatCompletions(requestDataChat);
        expect(ChatCompletionChunkSchema.parse(response)).toEqual(response);
    });

    it("generate chat completion - stream", async () => {
        const response = await client.llm.generateChatCompletionsStream(requestDataChat);

        expect(response).toBeInstanceOf(ReadableStream);
        const reader = response.getReader();
        let count: number = 0;

        while (true) {
            const { done } = await reader.read();

            if (done) {
                break;
            }
            count += 1;
        }

        expect(count).toBeGreaterThan(2);
    });

    it("generate embedding", async () => {
        let lastError: any = null;
        let allApiKeyErrors = true;
        let success = false;

        // Try all embedding models with API key error fallback
        for (const model of embeddingModels) {
            try {
                console.log(`Attempting to generate embedding with model: ${model}`);

                const response = await client.llm.generateEmbeddings({
                    type: "document",
                    model: model,
                    input: "This is embedding test"
                });

                expect(EmbeddingResponseSchema.parse(response)).toEqual(response);
                // Success! Update the global embeddingModel
                embeddingModel = model;
                console.log(`Successfully generated embedding with model: ${model}`);
                success = true;
                break;
            } catch (error: any) {
                console.log(`Failed to generate embedding with model ${model}:`, error?.message || error);
                lastError = error;

                if (!isApiKeyError(error)) {
                    // If it's not an API key error, it's a real error - throw immediately
                    allApiKeyErrors = false;
                    throw error;
                }
                // If it's an API key error, try the next model
            }
        }

        // If we tried all models and they all failed with API key errors, skip the test
        if (!success && allApiKeyErrors && lastError) {
            console.warn("All embedding models failed with API key errors. Skipping this test.");
            // Skip this test without failing
            return;
        }
    });

    
    
});
