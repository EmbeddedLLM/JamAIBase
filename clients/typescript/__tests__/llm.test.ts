import JamAI from "@/index";
import { ChatCompletionChunkSchema, ChatRequest } from "@/resources/llm/chat";
import { EmbeddingResponseSchema } from "@/resources/llm/embedding";
import { ModelInfoResponseSchema, ModelNamesResponseSchema } from "@/resources/llm/model";
import dotenv from "dotenv";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient LLM", () => {
    let client: JamAI;
    jest.setTimeout(30000);
    jest.retryTimes(0);

    beforeAll(() => {
        client = new JamAI({
            baseURL: process.env["BASEURL"]!,
            apiKey: process.env["JAMAI_APIKEY"]!,
            projectId: process.env["PROJECT_ID"]!
        });
        // const credential = Buffer.from(`${process.env["username"]}:${process.env["password"]}`).toString("base64");
        // client.setAuthHeader(`Basic ${credential}`);
    });

    it("get model info", async () => {
        const response = await client.modelInfo();

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
        // expect(false).toEqual(true);
    });

    it("get model info with capabilities", async () => {
        const response = await client.modelInfo({
            capabilities: ["chat"]
        });

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model info with name", async () => {
        const response = await client.modelInfo({
            model: "openai/gpt-3.5-turbo"
        });

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model info with both params", async () => {
        const response = await client.modelInfo({
            model: "openai/gpt-3.5-turbo",
            capabilities: ["chat"]
        });

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model name", async () => {
        const response = await client.modelNames();

        const parsedData = ModelNamesResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model name with capabilities", async () => {
        const response = await client.modelNames({
            capabilities: ["image"]
        });

        const parsedData = ModelNamesResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model info with prefer", async () => {
        const response = await client.modelNames({
            prefer: "openai/gpt-3.5-turbo"
        });

        const parsedData = ModelNamesResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model info with both params", async () => {
        const response = await client.modelNames({
            prefer: "openai/gpt-3.5-turbo",
            capabilities: ["chat"]
        });

        const parsedData = ModelNamesResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    const requestDataChat: ChatRequest = {
        model: "openai/gpt-3.5-turbo",
        messages: [{ role: "user", content: "Hello, what is the capital of Bangladesh?" }],
        max_tokens: 100,
        tools: null,
        // tool_choice: null,
        // n: 1,
        temperature: 0.1,
        top_p: 0.1,
        presence_penalty: 0,
        frequency_penalty: 0,
        logit_bias: undefined
    };

    it("generate chat completion", async () => {
        const response = await client.generateChatCompletions(requestDataChat);

        // console.log("response: ", response.choices[0]?.message);

        expect(ChatCompletionChunkSchema.parse(response)).toEqual(response);
    });

    it("generate chat completion - stream", async () => {
        const response = await client.generateChatCompletionsStream(requestDataChat);

        expect(response).toBeInstanceOf(ReadableStream);
        const reader = response.getReader();
        let count: number = 0;
        while (true) {
            const { done, value } = await reader.read();

            if (done) {
                break;
            }
            count += 1;
        }
        expect(count).toBeGreaterThan(2);
    });

    it("generate embedding", async () => {
        const response = await client.generateEmbeddings({
            type: "document",
            model: "ellm/BAAI/bge-m3",
            input: "This is embedding test"
        });

        expect(EmbeddingResponseSchema.parse(response)).toEqual(response);
    });
});
