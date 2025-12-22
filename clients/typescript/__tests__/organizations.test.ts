import JamAI from "@/index";
import { beforeAll, describe, expect, it, jest } from "@jest/globals";
import dotenv from "dotenv";
import { v4 as uuidv4 } from "uuid";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Organizations", () => {
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

    async function* _getOrganization() {
        const orgName = `Test Org ${uuidv4().substring(0, 8)}`;

        const org = await client.organizations.createOrganization({
            name: orgName
        });

        try {
            yield org;
        } finally {
            // Cleanup
            await client.organizations.deleteOrganization(org.id);
        }
    }

    it("create organization", async () => {
        const orgName = `Test Org ${uuidv4().substring(0, 8)}`;

        const response = await client.organizations.createOrganization({
            name: orgName
        });

        expect(response).toHaveProperty("id");
        expect(response).toHaveProperty("name");
        expect(response).toHaveProperty("created_by");
        expect(response).toHaveProperty("owner");
        expect(response).toHaveProperty("created_at");
        expect(response).toHaveProperty("updated_at");
        expect(response.name).toEqual(orgName);

        // Cleanup
        await client.organizations.deleteOrganization(response.id);
    });

    it("list organizations - without limit and offset", async () => {
        for await (const org of _getOrganization()) {
            const response = await client.organizations.listOrganizations({});

            expect(response).toHaveProperty("items");
            expect(Array.isArray(response.items)).toBe(true);
            expect(response).toHaveProperty("offset");
            expect(response).toHaveProperty("limit");
            expect(response).toHaveProperty("total");

            const foundOrg = response.items.find((item) => item.id === org.id);
            expect(foundOrg).toBeDefined();
        }
    });

    it("list organizations - with limit and offset", async () => {
        const limit = 3;
        const offset = 0;
        const response = await client.organizations.listOrganizations({ limit, offset });

        expect(response.limit).toEqual(limit);
        expect(response.offset).toEqual(offset);
        expect(response.items.length).toBeLessThanOrEqual(limit);
    });

    it("get organization", async () => {
        for await (const org of _getOrganization()) {
            const response = await client.organizations.getOrganization(org.id);

            expect(response).toHaveProperty("id");
            expect(response.id).toEqual(org.id);
            expect(response.name).toEqual(org.name);
        }
    });

    it("update organization", async () => {
        for await (const org of _getOrganization()) {
            const updatedName = `Updated Org ${uuidv4().substring(0, 8)}`;

            const response = await client.organizations.updateOrganization(org.id, {
                name: updatedName
            });

            expect(response).toHaveProperty("id");
            expect(response.id).toEqual(org.id);
            expect(response.name).toEqual(updatedName);
        }
    });

    it("delete organization", async () => {
        const orgName = `Test Org ${uuidv4().substring(0, 8)}`;
        const org = await client.organizations.createOrganization({ name: orgName });

        const deleteResponse = await client.organizations.deleteOrganization(org.id);

        expect(deleteResponse).toHaveProperty("ok");
        expect(deleteResponse.ok).toBeTruthy();

        // Verify organization is deleted
        const listResponse = await client.organizations.listOrganizations({});
        const foundOrg = listResponse.items.find((item) => item.id === org.id);
        expect(foundOrg).toBeUndefined();
    });

    it("list organization members", async () => {
        for await (const org of _getOrganization()) {
            const response = await client.organizations.listMembers(org.id, {});

            expect(response).toHaveProperty("items");
            expect(Array.isArray(response.items)).toBe(true);
            expect(response).toHaveProperty("offset");
            expect(response).toHaveProperty("limit");
            expect(response).toHaveProperty("total");
            expect(response.items.length).toBeGreaterThanOrEqual(1);
        }
    });

    it("get organization member", async () => {
        for await (const org of _getOrganization()) {
            const currentUser = await client.users.getUser();

            const response = await client.organizations.getMember(currentUser.id, org.id);

            expect(response).toHaveProperty("user_id");
            expect(response).toHaveProperty("organization_id");
            expect(response).toHaveProperty("role");
            expect(response.user_id).toEqual(currentUser.id);
            expect(response.organization_id).toEqual(org.id);
        }
    });

    it("model catalogue", async () => {
        for await (const org of _getOrganization()) {
            const response = await client.organizations.modelCatalogue(org.id, {});

            expect(response).toHaveProperty("items");
            expect(Array.isArray(response.items)).toBe(true);
            expect(response).toHaveProperty("offset");
            expect(response).toHaveProperty("limit");
            expect(response).toHaveProperty("total");
        }
    });

    if (process.env["JAMAI_API_KEY"]) {
        it("create and revoke organization invite", async () => {
            for await (const org of _getOrganization()) {
                const inviteEmail = `invite-${uuidv4()}@example.com`;

                const createResponse = await client.organizations.createInvite({
                    user_email: inviteEmail,
                    organization_id: org.id,
                    role: "MEMBER",
                    valid_days: 7
                });

                expect(createResponse).toHaveProperty("id");
                expect(createResponse).toHaveProperty("user_email");
                expect(createResponse.user_email).toEqual(inviteEmail);

                // Revoke the invite
                const revokeResponse = await client.organizations.revokeInvite(createResponse.id);

                expect(revokeResponse).toHaveProperty("ok");
                expect(revokeResponse.ok).toBeTruthy();
            }
        });

        it("list organization invites", async () => {
            for await (const org of _getOrganization()) {
                const response = await client.organizations.listInvites(org.id, {});

                expect(response).toHaveProperty("items");
                expect(Array.isArray(response.items)).toBe(true);
                expect(response).toHaveProperty("offset");
                expect(response).toHaveProperty("limit");
                expect(response).toHaveProperty("total");
            }
        });

        it("refresh organization quota", async () => {
            for await (const org of _getOrganization()) {
                const response = await client.organizations.refreshQuota(org.id);

                expect(response).toHaveProperty("id");
                expect(response.id).toEqual(org.id);
                expect(response).toHaveProperty("quota_reset_at");
            }
        });
    }
});
