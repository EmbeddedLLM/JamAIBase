import JamAI from "@/index";
import { beforeAll, describe, expect, it, jest } from "@jest/globals";
import dotenv from "dotenv";
import { v4 as uuidv4 } from "uuid";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Users", () => {
    let client: JamAI;
    let testContext: TestContext;
    jest.setTimeout(30000);
    jest.retryTimes(1, {
        logErrorsBeforeRetry: true
    });

    beforeAll(async () => {
        testContext = await setupTestEnvironment();
        client = testContext.client;
    });

    afterAll(async function () {
        await cleanupTestEnvironment(testContext);
    });

    it("get current user", async () => {
        const response = await client.users.getUser();

        expect(response).toHaveProperty("id");
        expect(response).toHaveProperty("name");
        expect(response).toHaveProperty("email");
        expect(response).toHaveProperty("created_at");
        expect(response).toHaveProperty("updated_at");
    });

    it("list users - without limit and offset", async () => {
        const response = await client.users.listUsers({});

        expect(response).toHaveProperty("items");
        expect(Array.isArray(response.items)).toBe(true);
        expect(response).toHaveProperty("offset");
        expect(response).toHaveProperty("limit");
        expect(response).toHaveProperty("total");
        expect(response.items.length).toBeGreaterThanOrEqual(1);
    });

    it("list users - with limit", async () => {
        const limit = 2;
        const response = await client.users.listUsers({ limit });

        expect(response.items.length).toBeLessThanOrEqual(limit);
        expect(response.limit).toEqual(limit);
    });

    it("list users - with offset", async () => {
        const offset = 0;
        const response = await client.users.listUsers({ offset });

        expect(response.offset).toEqual(offset);
        expect(Array.isArray(response.items)).toBe(true);
    });

    it("list users - with limit and offset", async () => {
        const limit = 3;
        const offset = 0;
        const response = await client.users.listUsers({ limit, offset });

        expect(response.limit).toEqual(limit);
        expect(response.offset).toEqual(offset);
        expect(response.items.length).toBeLessThanOrEqual(limit);
    });

    it("update current user", async () => {
        const currentUser = await client.users.getUser();
        const newName = `Updated User ${uuidv4().substring(0, 8)}`;

        const response = await client.users.updateUser({
            name: newName
        });

        expect(response).toHaveProperty("id");
        expect(response.id).toEqual(currentUser.id);
        expect(response.name).toEqual(newName);

        // Restore original name
        await client.users.updateUser({
            name: currentUser.name
        });
    });
    if (process.env["JAMAI_API_KEY"]) {
        it("create personal access token", async () => {
            const patName = `Test PAT ${uuidv4().substring(0, 8)}`;

            const response = await client.users.createPat({
                name: patName
            });

            expect(response).toHaveProperty("id");
            expect(response).toHaveProperty("name");
            expect(response.name).toEqual(patName);
            expect(response.id).toBeTruthy();

            // Cleanup
            await client.users.deletePat(response.id);
        });

        it("list personal access tokens - without limit and offset", async () => {
            // Create a test PAT first
            const patName = `Test PAT ${uuidv4().substring(0, 8)}`;
            const createdPat = await client.users.createPat({ name: patName });

            try {
                const response = await client.users.listPats({});

                expect(response).toHaveProperty("items");
                expect(Array.isArray(response.items)).toBe(true);
                expect(response).toHaveProperty("offset");
                expect(response).toHaveProperty("limit");
                expect(response).toHaveProperty("total");

                const foundPat = response.items.find((pat) => pat.id === createdPat.id);
                expect(foundPat).toBeDefined();
            } finally {
                // Cleanup
                await client.users.deletePat(createdPat.id);
            }
        });

        it("list personal access tokens - with limit", async () => {
            const limit = 2;
            const response = await client.users.listPats({ limit });

            expect(response.items.length).toBeLessThanOrEqual(limit);
            expect(response.limit).toEqual(limit);
        });

        it("update personal access token", async () => {
            const patName = `Test PAT ${uuidv4().substring(0, 8)}`;
            const createdPat = await client.users.createPat({ name: patName });

            try {
                const updatedName = `Updated PAT ${uuidv4().substring(0, 8)}`;
                const response = await client.users.updatePat(createdPat.id, {
                    name: updatedName
                });

                expect(response).toHaveProperty("id");
                expect(response.id).toEqual(createdPat.id);
                expect(response.name).toEqual(updatedName);
            } finally {
                // Cleanup
                await client.users.deletePat(createdPat.id);
            }
        });

        it("delete personal access token", async () => {
            const patName = `Test PAT ${uuidv4().substring(0, 8)}`;
            const createdPat = await client.users.createPat({ name: patName });

            const deleteResponse = await client.users.deletePat(createdPat.id);

            expect(deleteResponse).toHaveProperty("ok");
            expect(deleteResponse.ok).toBeTruthy();

            // Verify PAT is deleted
            const listResponse = await client.users.listPats({});
            const foundPat = listResponse.items.find((pat) => pat.id === createdPat.id);
            expect(foundPat).toBeUndefined();
        });


        it("create email verification code", async () => {
            const response = await client.users.createEmailVerificationCode();

            expect(response).toHaveProperty("id");
            expect(response).toHaveProperty("created_at");
        });

        it("list email verification codes", async () => {
            const response = await client.users.listEmailVerificationCodes({});

            expect(response).toHaveProperty("items");
            expect(Array.isArray(response.items)).toBe(true);
            expect(response).toHaveProperty("offset");
            expect(response).toHaveProperty("limit");
            expect(response).toHaveProperty("total");
        });

        it("get email verification code", async () => {
            // Create a verification code first
            const createdCode = await client.users.createEmailVerificationCode();

            const response = await client.users.getEmailVerificationCode(createdCode.id);

            expect(response).toHaveProperty("id");

            // Cleanup
            await client.users.revokeEmailVerificationCode(createdCode.id);
        });

        it("revoke email verification code", async () => {
            // Create a verification code first
            const createdCode = await client.users.createEmailVerificationCode();

            const deleteResponse = await client.users.revokeEmailVerificationCode(createdCode.id);

            expect(deleteResponse).toHaveProperty("ok");
            expect(deleteResponse.ok).toBeTruthy();
        });
    }
});
