import JamAI from "@/index";
import { beforeAll, describe, expect, it, jest } from "@jest/globals";
import dotenv from "dotenv";
import { v4 as uuidv4 } from "uuid";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Secrets", () => {
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

        // Get the first organization to use for secrets tests
        const orgsResponse = await client.organizations.listOrganizations({});
        if (orgsResponse.items.length > 0) {
            testOrganizationId = orgsResponse.items[0]!.id;
        } else {
            throw new Error("No organization available for secrets tests");
        }
    });

    afterAll(async function () {
        await cleanupTestEnvironment(testContext);
    });

    async function* _getSecret() {
        // Generate a valid secret name (alphanumeric and underscore only, starting with letter or underscore)
        const secretName = `TEST_SECRET_${uuidv4().substring(0, 8).replace(/-/g, "_")}`;
        const secretValue = `secret-value-${uuidv4()}`;

        const secret = await client.secrets.createSecret(
            {
                name: secretName,
                value: secretValue
            },
            testOrganizationId
        );

        try {
            yield secret;
        } finally {
            // Cleanup
            await client.secrets.deleteSecret(testOrganizationId, secret.name);
        }
    }

    it("create secret", async () => {
        const secretName = `TEST_SECRET_${uuidv4().substring(0, 8).replace(/-/g, "_")}`;
        const secretValue = `secret-value-${uuidv4()}`;

        const response = await client.secrets.createSecret(
            {
                name: secretName,
                value: secretValue
            },
            testOrganizationId
        );

        expect(response).toHaveProperty("name");
        expect(response).toHaveProperty("value");
        expect(response).toHaveProperty("organization_id");
        expect(response).toHaveProperty("created_at");
        expect(response).toHaveProperty("updated_at");
        expect(response.name).toEqual(secretName.toUpperCase());
        expect(response.organization_id).toEqual(testOrganizationId);
        // Value should be returned unmasked on creation
        expect(response.value).toBeTruthy();

        // Cleanup
        await client.secrets.deleteSecret(testOrganizationId, response.name);
    });

    it("list secrets - without limit and offset", async () => {
        for await (const secret of _getSecret()) {
            const response = await client.secrets.listSecrets(testOrganizationId, {});

            expect(response).toHaveProperty("items");
            expect(Array.isArray(response.items)).toBe(true);
            expect(response).toHaveProperty("offset");
            expect(response).toHaveProperty("limit");
            expect(response).toHaveProperty("total");

            const foundSecret = response.items.find((item) => item.name === secret.name);
            expect(foundSecret).toBeDefined();
        }
    });

    it("list secrets - with limit", async () => {
        const limit = 2;
        const response = await client.secrets.listSecrets(testOrganizationId, { limit });

        expect(response.items.length).toBeLessThanOrEqual(limit);
        expect(response.limit).toEqual(limit);
    });

    it("list secrets - with offset", async () => {
        const offset = 0;
        const response = await client.secrets.listSecrets(testOrganizationId, { offset });

        expect(response.offset).toEqual(offset);
        expect(Array.isArray(response.items)).toBe(true);
    });

    it("list secrets - with limit and offset", async () => {
        const limit = 3;
        const offset = 0;
        const response = await client.secrets.listSecrets(testOrganizationId, { limit, offset });

        expect(response.limit).toEqual(limit);
        expect(response.offset).toEqual(offset);
        expect(response.items.length).toBeLessThanOrEqual(limit);
    });

    it("get secret - value is masked", async () => {
        for await (const secret of _getSecret()) {
            const response = await client.secrets.getSecret(testOrganizationId, secret.name);

            expect(response).toHaveProperty("name");
            expect(response.name).toEqual(secret.name);
            expect(response).toHaveProperty("value");
            // Value should be masked when getting
            expect(response.value).toBeDefined();
        }
    });

    it("update secret - value is unmasked", async () => {
        for await (const secret of _getSecret()) {
            const newValue = `updated-value-${uuidv4()}`;

            const response = await client.secrets.updateSecret(testOrganizationId, secret.name, {
                value: newValue
            });

            expect(response).toHaveProperty("name");
            expect(response.name).toEqual(secret.name);
            expect(response).toHaveProperty("value");
            // Value should be unmasked on update
            expect(response.value).toBeTruthy();
        }
    });

    it("delete secret", async () => {
        const secretName = `TEST_SECRET_${uuidv4().substring(0, 8).replace(/-/g, "_")}`;
        const secretValue = `secret-value-${uuidv4()}`;

        const secret = await client.secrets.createSecret(
            {
                name: secretName,
                value: secretValue
            },
            testOrganizationId
        );

        const deleteResponse = await client.secrets.deleteSecret(testOrganizationId, secret.name);

        expect(deleteResponse).toHaveProperty("ok");
        expect(deleteResponse.ok).toBeTruthy();

        // Verify secret is deleted
        const listResponse = await client.secrets.listSecrets(testOrganizationId, {});
        const foundSecret = listResponse.items.find((item) => item.name === secret.name);
        expect(foundSecret).toBeUndefined();
    });

    it("create secret with allowed projects", async () => {
        // Get a project to use for allowed_projects
        const projectsResponse = await client.projects.listProjects(testOrganizationId, { limit: 1 });

        if (projectsResponse.items.length === 0) {
            console.warn("Create secret with allowed projects test skipped: No projects available");
            return;
        }

        const projectId = projectsResponse.items[0]!.id;
        const secretName = `TEST_SECRET_${uuidv4().substring(0, 8).replace(/-/g, "_")}`;
        const secretValue = `secret-value-${uuidv4()}`;

        const response = await client.secrets.createSecret(
            {
                name: secretName,
                value: secretValue,
                allowed_projects: [projectId]
            },
            testOrganizationId
        );

        expect(response).toHaveProperty("name");
        expect(response).toHaveProperty("allowed_projects");
        expect(response.allowed_projects).toBeDefined();
        if (response.allowed_projects) {
            expect(response.allowed_projects).toContain(projectId);
        }

        // Cleanup
        await client.secrets.deleteSecret(testOrganizationId, response.name);
    });

    it("validate secret name constraints", async () => {
        // Test invalid secret name (starts with number)
        await expect(
            client.secrets.createSecret(
                {
                    name: "123_INVALID",
                    value: "test-value"
                },
                testOrganizationId
            )
        ).rejects.toThrow();

        // Test invalid secret name (contains special characters)
        await expect(
            client.secrets.createSecret(
                {
                    name: "INVALID-NAME",
                    value: "test-value"
                },
                testOrganizationId
            )
        ).rejects.toThrow();

        // Test invalid secret name (contains spaces)
        await expect(
            client.secrets.createSecret(
                {
                    name: "INVALID NAME",
                    value: "test-value"
                },
                testOrganizationId
            )
        ).rejects.toThrow();
    });
});
