import JamAI from "@/index";
import { beforeAll, describe, expect, it, jest } from "@jest/globals";
import dotenv from "dotenv";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Meters", () => {
    let client: JamAI;
    let testContext: TestContext;
    let testOrganizationId: string;
    jest.setTimeout(30000);
    jest.retryTimes(1, {
        logErrorsBeforeRetry: true
    });

    beforeAll(async () => {
        testContext = await setupTestEnvironment();
        client = testContext.client;

        // Get the first organization to use for meter tests
        const orgsResponse = await client.organizations.listOrganizations({});
        if (orgsResponse.items.length > 0) {
            testOrganizationId = orgsResponse.items[0]!.id;
        } else {
            throw new Error("No organization available for meter tests");
        }
    });

    afterAll(async function () {
        await cleanupTestEnvironment(testContext);
    });

    it("get usage metrics - llm", async () => {
        // Get current date and date from 7 days ago
        const to = new Date().toISOString();
        const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

        const response = await client.meters.getUsageMetrics({
            type: "llm",
            from: from,
            to: to,
            windowSize: "1d",
            orgIds: [testOrganizationId]
        });

        expect(response).toHaveProperty("data");
        expect(Array.isArray(response.data)).toBe(true);
    });

    it("get usage metrics - embedding", async () => {
        const to = new Date().toISOString();
        const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

        const response = await client.meters.getUsageMetrics({
            type: "embedding",
            from: from,
            to: to,
            windowSize: "1d",
            orgIds: [testOrganizationId]
        });

        expect(response).toHaveProperty("data");
        expect(Array.isArray(response.data)).toBe(true);
    });

    it("get usage metrics - reranking", async () => {
        const to = new Date().toISOString();
        const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

        const response = await client.meters.getUsageMetrics({
            type: "reranking",
            from: from,
            to: to,
            windowSize: "1d",
            orgIds: [testOrganizationId]
        });

        expect(response).toHaveProperty("data");
        expect(Array.isArray(response.data)).toBe(true);
    });

    it("get billing metrics", async () => {
        const to = new Date().toISOString();
        const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

        const response = await client.meters.getBillingMetrics({
            from: from,
            to: to,
            windowSize: "1d",
            orgIds: [testOrganizationId]
        });

        expect(response).toHaveProperty("data");
        expect(Array.isArray(response.data)).toBe(true);
    });

    it("get bandwidth metrics", async () => {
        const to = new Date().toISOString();
        const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

        const response = await client.meters.getBandwidthMetrics({
            from: from,
            to: to,
            windowSize: "1d",
            orgIds: [testOrganizationId]
        });

        expect(response).toHaveProperty("data");
        expect(Array.isArray(response.data)).toBe(true);
    });

    it("get storage metrics", async () => {
        const to = new Date().toISOString();
        const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

        const response = await client.meters.getStorageMetrics({
            from: from,
            to: to,
            windowSize: "1d",
            orgIds: [testOrganizationId]
        });

        expect(response).toHaveProperty("data");
        expect(Array.isArray(response.data)).toBe(true);
    });

    it("get usage metrics with different window sizes", async () => {
        const to = new Date().toISOString();
        const from = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(); // 30 days ago

        // Test different window sizes
        const windowSizes = ["1h", "1d", "7d"];

        for (const windowSize of windowSizes) {
            const response = await client.meters.getUsageMetrics({
                type: "llm",
                from: from,
                to: to,
                windowSize: windowSize,
                orgIds: [testOrganizationId]
            });

            expect(response).toHaveProperty("data");
            expect(Array.isArray(response.data)).toBe(true);
        }
    });

    it("get usage metrics with groupBy parameter", async () => {
        const to = new Date().toISOString();
        const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

        const response = await client.meters.getUsageMetrics({
            type: "llm",
            from: from,
            to: to,
            windowSize: "1d",
            orgIds: [testOrganizationId],
            groupBy: ["org_id"]
        });

        expect(response).toHaveProperty("data");
        expect(Array.isArray(response.data)).toBe(true);
    });
});
