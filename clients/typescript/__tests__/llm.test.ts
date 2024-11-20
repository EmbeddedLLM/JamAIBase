import JamAI from "@/index";
import { ChatCompletionChunkSchema, ChatRequest } from "@/resources/llm/chat";
import { EmbeddingResponseSchema } from "@/resources/llm/embedding";
import { ModelInfoResponseSchema, ModelNamesResponseSchema } from "@/resources/llm/model";
import dotenv from "dotenv";
import { v4 as uuidv4 } from "uuid";

dotenv.config({
    path: "__tests__/.env"
});

let llmModel: string;
let embeddingModel: string;

describe("APIClient LLM", () => {
    let client: JamAI;
    jest.setTimeout(30000);
    jest.retryTimes(1, {
        logErrorsBeforeRetry: true
    });

    let myuuid = uuidv4();
    let projectName = `unittest-project-${myuuid}`;

    let projectId: string;
    let organizationId: string;
    let userId = `unittest-user-${myuuid}`;
    let requestDataChat: ChatRequest;

    beforeAll(async () => {
        // cloud
        if (process.env["JAMAI_API_KEY"]) {
            // create user
            const responseUser = await fetch(`${process.env["BASEURL"]}/api/admin/backend/v1/users`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${process.env["JAMAI_API_KEY"]}`
                },
                body: JSON.stringify({
                    id: userId,
                    name: "TS SDK Tester",
                    description: "I am a TS SDK Tester",
                    email: "kamil.kzs2017@gmail.com"
                })
            });
            const userData = await responseUser.json();

            userId = userData.id;

            // create organization
            const responseOrganization = await fetch(`${process.env["BASEURL"]}/api/admin/backend/v1/organizations`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${process.env["JAMAI_API_KEY"]}`
                },
                body: JSON.stringify({
                    creator_user_id: userId,
                    tier: "free",
                    name: "Company",
                    active: true,
                    credit: 30.0,
                    credit_grant: 1.0,
                    llm_tokens_usage_mtok: 70,
                    db_usage_gib: 2.0,
                    file_usage_gib: 3.0,
                    egress_usage_gib: 4.0
                })
            });
            const organizationData = await responseOrganization.json();

            organizationId = organizationData?.id;
        } else {
            // OSS
            // fetch organization

            const responseOrganization = await fetch(`${process.env["BASEURL"]}/api/admin/backend/v1/organizations/default`);

            const organizationData = await responseOrganization.json();
            organizationId = organizationData?.id;
        }

        // create project
        const responseProject = await fetch(`${process.env["BASEURL"]}/api/admin/org/v1/projects`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${process.env["JAMAI_API_KEY"]}`
            },
            body: JSON.stringify({
                name: projectName,
                organization_id: organizationId
            })
        });

        const projectData = await responseProject.json();

        projectId = projectData?.id;

        client = new JamAI({
            baseURL: process.env["BASEURL"]!,
            token: process.env["JAMAI_API_KEY"]!,
            projectId: projectId
        });

        const models = await client.llm.modelInfo();

        const selectedLlmModel = models.data.find((model) => model.capabilities.includes("chat"));
        llmModel = selectedLlmModel?.id ? selectedLlmModel.id : "openai/gpt-4o-mini";

        const selectedEmbeddingModel = models.data.find((model) => model.capabilities.includes("embed"));
        embeddingModel = selectedEmbeddingModel?.id ? selectedEmbeddingModel.id : "ellm/sentence-transformers/all-MiniLM-L6-v2";

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
        // delete project
        const responseProject = await fetch(`${process.env["BASEURL"]}/api/admin/org/v1/projects/${projectId}`, {
            method: "DELETE",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${process.env["JAMAI_API_KEY"]}`
            }
        });
        const projectData = await responseProject.json();

        if (process.env["JAMAI_API_KEY"]) {
            // delete organization
            const responseOrganization = await fetch(`${process.env["BASEURL"]}/api/admin/backend/v1/organizations/${organizationId}`, {
                method: "DELETE",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${process.env["JAMAI_API_KEY"]}`
                }
            });
            const organizationData = await responseOrganization.json();
            // delete user
            const responseUser = await fetch(`${process.env["BASEURL"]}/api/admin/backend/v1/users/${userId}`, {
                method: "DELETE",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${process.env["JAMAI_API_KEY"]}`
                }
            });
            const userData = await responseUser.json();
        }
    });

    it("get model info", async () => {
        const response = await client.llm.modelInfo();

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get model info with capabilities", async () => {
        const response = await client.llm.modelInfo({
            capabilities: ["chat"]
        });

        const parsedData = ModelInfoResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
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
        try {
            console.log("model: ", requestDataChat.model);
            const response = await client.llm.generateChatCompletions(requestDataChat);

            expect(ChatCompletionChunkSchema.parse(response)).toEqual(response);
        } catch (err: any) {
            console.log("error: ", err.response.data);
        }
    });

    it("generate chat completion - stream", async () => {
        const response = await client.llm.generateChatCompletionsStream(requestDataChat);

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
        const response = await client.llm.generateEmbeddings({
            type: "document",
            model: embeddingModel,
            input: "This is embedding test"
        });

        expect(EmbeddingResponseSchema.parse(response)).toEqual(response);
    });
});
