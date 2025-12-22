import JamAI from "@/index";
import { beforeAll, describe, expect, it, jest } from "@jest/globals";
import dotenv from "dotenv";
import { v4 as uuidv4 } from "uuid";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Models", () => {
    let client: JamAI;
    let testContext: TestContext;
    jest.setTimeout(30000);
    jest.retryTimes(1, {
        logErrorsBeforeRetry: true
    });

    beforeAll(async () => {
        testContext = await setupTestEnvironment({
            createModels: true
        });
        client = testContext.client;
    });

    afterAll(async function () {
        await cleanupTestEnvironment(testContext);
    });

    async function* _getModelConfig() {
        const modelId = `openai/test-model-${uuidv4().substring(0, 8)}`;
        const modelName = `Test Model ${uuidv4().substring(0, 8)}`;

        const modelConfig = await client.models.createModelConfig({
            id: modelId,
            name: modelName,
            type: "completion",
            capabilities: ["chat"],
            context_length: 4096
        });

        try {
            yield modelConfig;
        } finally {
            // Cleanup
            await client.models.deleteModelConfig(modelConfig.id);
        }
    }

    it("list model configs - without limit and offset", async () => {
        for await (const modelConfig of _getModelConfig()) {
            const response = await client.models.listModelConfigs();

            expect(response).toHaveProperty("items");
            expect(Array.isArray(response.items)).toBe(true);
            expect(response).toHaveProperty("offset");
            expect(response).toHaveProperty("limit");
            expect(response).toHaveProperty("total");

            const foundModel = response.items.find((item) => item.id === modelConfig.id);
            expect(foundModel).toBeDefined();
        }
    });

    it("list model configs - with limit", async () => {
        const limit = 2;
        const response = await client.models.listModelConfigs({ limit });

        expect(response.items.length).toBeLessThanOrEqual(limit);
        expect(response.limit).toEqual(limit);
    });

    it("list model configs - with offset", async () => {
        const offset = 0;
        const response = await client.models.listModelConfigs({ offset });

        expect(response.offset).toEqual(offset);
        expect(Array.isArray(response.items)).toBe(true);
    });

    it("list model configs - with limit and offset", async () => {
        const limit = 3;
        const offset = 0;
        const response = await client.models.listModelConfigs({ limit, offset });

        expect(response.limit).toEqual(limit);
        expect(response.offset).toEqual(offset);
        expect(response.items.length).toBeLessThanOrEqual(limit);
    });

    it("get model config", async () => {
        for await (const modelConfig of _getModelConfig()) {
            const response = await client.models.getModelConfig(modelConfig.id);

            expect(response).toHaveProperty("id");
            expect(response.id).toEqual(modelConfig.id);
            expect(response.name).toEqual(modelConfig.name);
        }
    });

    it("update model config", async () => {
        for await (const modelConfig of _getModelConfig()) {
            const updatedName = `Updated Model ${uuidv4().substring(0, 8)}`;

            const response = await client.models.updateModelConfig(modelConfig.id, {
                name: updatedName
            });

            expect(response).toHaveProperty("id");
            expect(response.id).toEqual(modelConfig.id);
            expect(response.name).toEqual(updatedName);
        }
    });

    it("delete model config", async () => {
        const modelId = `openai/test-model-${uuidv4().substring(0, 8)}`;
        const modelName = `Test Model ${uuidv4().substring(0, 8)}`;

        const modelConfig = await client.models.createModelConfig({
            id: modelId,
            name: modelName,
            type: "completion",
            capabilities: ["chat"],
            context_length: 4096
        });

        const deleteResponse = await client.models.deleteModelConfig(modelConfig.id);

        expect(deleteResponse).toHaveProperty("ok");
        expect(deleteResponse.ok).toBeTruthy();

        // Verify model config is deleted
        const listResponse = await client.models.listModelConfigs({});
        const foundModel = listResponse.items.find((item) => item.id === modelConfig.id);
        expect(foundModel).toBeUndefined();
    });

    it("create deployment", async () => {
        for await (const modelConfig of _getModelConfig()) {
            const deploymentName = `Test Deployment ${uuidv4().substring(0, 8)}`;

            const response = await client.models.createDeployment({
                model_id: modelConfig.id,
                name: deploymentName,
                provider: "openai",
                routing_id: "gpt-4o-mini"
            });

            expect(response).toHaveProperty("id");
            expect(response).toHaveProperty("name");
            expect(response).toHaveProperty("model_id");
            expect(response).toHaveProperty("created_at");
            expect(response).toHaveProperty("updated_at");
            expect(response.name).toEqual(deploymentName);
            expect(response.model_id).toEqual(modelConfig.id);

            // Cleanup
            await client.models.deleteDeployment(response.id);
        }
    });

    it("list deployments - without limit and offset", async () => {
        const response = await client.models.listDeployments({});

        expect(response).toHaveProperty("items");
        expect(Array.isArray(response.items)).toBe(true);
        expect(response).toHaveProperty("offset");
        expect(response).toHaveProperty("limit");
        expect(response).toHaveProperty("total");
    });

    it("list deployments - with limit", async () => {
        const limit = 2;
        const response = await client.models.listDeployments({ limit });

        expect(response.items.length).toBeLessThanOrEqual(limit);
        expect(response.limit).toEqual(limit);
    });

    it("get deployment", async () => {
        for await (const modelConfig of _getModelConfig()) {
            const deploymentName = `Test Deployment ${uuidv4().substring(0, 8)}`;
            const deployment = await client.models.createDeployment({
                model_id: modelConfig.id,
                name: deploymentName,
                provider: "openai",
                routing_id: "gpt-4o-mini"
            });

            const response = await client.models.getDeployment(deployment.id);

            expect(response).toHaveProperty("id");
            expect(response.id).toEqual(deployment.id);
            expect(response.name).toEqual(deployment.name);

            // Cleanup
            await client.models.deleteDeployment(deployment.id);
        }
    });

    it("update deployment", async () => {
        for await (const modelConfig of _getModelConfig()) {
            const deploymentName = `Test Deployment ${uuidv4().substring(0, 8)}`;
            const deployment = await client.models.createDeployment({
                model_id: modelConfig.id,
                name: deploymentName,
                provider: "openai",
                routing_id: "gpt-4o-mini"
            });

            const updatedName = `Updated Deployment ${uuidv4().substring(0, 8)}`;
            const response = await client.models.updateDeployment(deployment.id, {
                name: updatedName
            });

            expect(response).toHaveProperty("id");
            expect(response.id).toEqual(deployment.id);
            expect(response.name).toEqual(updatedName);

            // Cleanup
            await client.models.deleteDeployment(deployment.id);
        }
    });

    it("delete deployment", async () => {
        for await (const modelConfig of _getModelConfig()) {
            const deploymentName = `Test Deployment ${uuidv4().substring(0, 8)}`;
            const deployment = await client.models.createDeployment({
                model_id: modelConfig.id,
                name: deploymentName,
                provider: "openai",
                routing_id: "gpt-4o-mini"
            });

            const deleteResponse = await client.models.deleteDeployment(deployment.id);

            expect(deleteResponse).toHaveProperty("ok");
            expect(deleteResponse.ok).toBeTruthy();

            // Verify deployment is deleted
            const listResponse = await client.models.listDeployments({});
            const foundDeployment = listResponse.items.find((item) => item.id === deployment.id);
            expect(foundDeployment).toBeUndefined();
        }
    });
});
