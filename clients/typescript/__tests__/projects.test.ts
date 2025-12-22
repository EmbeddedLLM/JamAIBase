import JamAI from "@/index";
import { beforeAll, describe, expect, it, jest } from "@jest/globals";
import dotenv from "dotenv";
import { v4 as uuidv4 } from "uuid";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Projects", () => {
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

        // Get the first organization to use for project tests
        const orgsResponse = await client.organizations.listOrganizations({});
        if (orgsResponse.items.length > 0) {
            testOrganizationId = orgsResponse.items[0]!.id;
        } else {
            // Create a test organization if none exists
            const org = await client.organizations.createOrganization({
                name: `Test Org ${uuidv4().substring(0, 8)}`
            });
            testOrganizationId = org.id;
        }
    });

    afterAll(async function () {
        await cleanupTestEnvironment(testContext);
    });

    async function* _getProject() {
        const projectName = `Test Project ${uuidv4().substring(0, 8)}`;

        const project = await client.projects.createProject({
            organization_id: testOrganizationId,
            name: projectName
        });

        try {
            yield project;
        } finally {
            // Cleanup
            await client.projects.deleteProject(project.id);
        }
    }

    it("create project", async () => {
        const projectName = `Test Project ${uuidv4().substring(0, 8)}`;

        const response = await client.projects.createProject({
            organization_id: testOrganizationId,
            name: projectName
        });

        expect(response).toHaveProperty("id");
        expect(response).toHaveProperty("name");
        expect(response).toHaveProperty("organization_id");
        expect(response).toHaveProperty("created_by");
        expect(response).toHaveProperty("owner");
        expect(response).toHaveProperty("created_at");
        expect(response).toHaveProperty("updated_at");
        expect(response.name).toEqual(projectName);
        expect(response.organization_id).toEqual(testOrganizationId);

        // Cleanup
        await client.projects.deleteProject(response.id);
    });

    it("list projects - without limit and offset", async () => {
        for await (const project of _getProject()) {
            const response = await client.projects.listProjects(testOrganizationId, {});

            expect(response).toHaveProperty("items");
            expect(Array.isArray(response.items)).toBe(true);
            expect(response).toHaveProperty("offset");
            expect(response).toHaveProperty("limit");
            expect(response).toHaveProperty("total");

            const foundProject = response.items.find((item) => item.id === project.id);
            expect(foundProject).toBeDefined();
        }
    });

    it("list projects - with limit", async () => {
        const limit = 2;
        const response = await client.projects.listProjects(testOrganizationId, { limit });

        expect(response.items.length).toBeLessThanOrEqual(limit);
        expect(response.limit).toEqual(limit);
    });

    it("list projects - with offset", async () => {
        const offset = 0;
        const response = await client.projects.listProjects(testOrganizationId, { offset });

        expect(response.offset).toEqual(offset);
        expect(Array.isArray(response.items)).toBe(true);
    });

    it("list projects - with limit and offset", async () => {
        const limit = 3;
        const offset = 0;
        const response = await client.projects.listProjects(testOrganizationId, { limit, offset });

        expect(response.limit).toEqual(limit);
        expect(response.offset).toEqual(offset);
        expect(response.items.length).toBeLessThanOrEqual(limit);
    });

    it("get project", async () => {
        for await (const project of _getProject()) {
            const response = await client.projects.getProject(project.id);

            expect(response).toHaveProperty("id");
            expect(response.id).toEqual(project.id);
            expect(response.name).toEqual(project.name);
        }
    });

    it("update project", async () => {
        for await (const project of _getProject()) {
            const updatedName = `Updated Project ${uuidv4().substring(0, 8)}`;
            const updatedDescription = "Updated project description";

            const response = await client.projects.updateProject(project.id, {
                name: updatedName,
                description: updatedDescription
            });

            expect(response).toHaveProperty("id");
            expect(response.id).toEqual(project.id);
            expect(response.name).toEqual(updatedName);
            expect(response.description).toEqual(updatedDescription);
        }
    });

    it("delete project", async () => {
        const projectName = `Test Project ${uuidv4().substring(0, 8)}`;
        const project = await client.projects.createProject({
            organization_id: testOrganizationId,
            name: projectName
        });

        const deleteResponse = await client.projects.deleteProject(project.id);

        expect(deleteResponse).toHaveProperty("ok");
        expect(deleteResponse.ok).toBeTruthy();

        // Verify project is deleted
        const listResponse = await client.projects.listProjects(testOrganizationId, {});
        const foundProject = listResponse.items.find((item) => item.id === project.id);
        expect(foundProject).toBeUndefined();
    });

    it("list project members", async () => {
        for await (const project of _getProject()) {
            const response = await client.projects.listMembers(project.id, {});

            expect(response).toHaveProperty("items");
            expect(Array.isArray(response.items)).toBe(true);
            expect(response).toHaveProperty("offset");
            expect(response).toHaveProperty("limit");
            expect(response).toHaveProperty("total");
            expect(response.items.length).toBeGreaterThanOrEqual(1);
        }
    });

    it("get project member", async () => {
        for await (const project of _getProject()) {
            const currentUser = await client.users.getUser();

            const response = await client.projects.getMember(currentUser.id, project.id);

            expect(response).toHaveProperty("user_id");
            expect(response).toHaveProperty("project_id");
            expect(response).toHaveProperty("role");
            expect(response.user_id).toEqual(currentUser.id);
            expect(response.project_id).toEqual(project.id);
        }
    });

    if (process.env["JAMAI_API_KEY"]) {
        it("create and revoke project invite", async () => {
            for await (const project of _getProject()) {
                const inviteEmail = `invite-${uuidv4()}@example.com`;

                const createResponse = await client.projects.createInvite({
                    user_email: inviteEmail,
                    project_id: project.id,
                    role: "MEMBER",
                    valid_days: 7
                });

                expect(createResponse).toHaveProperty("id");
                expect(createResponse).toHaveProperty("user_email");
                expect(createResponse.user_email).toEqual(inviteEmail);

                // Revoke the invite
                const revokeResponse = await client.projects.revokeInvite(createResponse.id);

                expect(revokeResponse).toHaveProperty("ok");
                expect(revokeResponse.ok).toBeTruthy();
            }
        });

        it("list project invites", async () => {
            for await (const project of _getProject()) {
                const response = await client.projects.listInvites(project.id, {});

                expect(response).toHaveProperty("items");
                expect(Array.isArray(response.items)).toBe(true);
                expect(response).toHaveProperty("offset");
                expect(response).toHaveProperty("limit");
                expect(response).toHaveProperty("total");
            }
        });
    }

    it("export project", async () => {
        for await (const project of _getProject()) {
            const newClient = new JamAI({
                baseURL: process.env["BASEURL"]!,
                token: process.env["JAMAI_API_KEY"]!,
                userId: testContext.userId
            });

            newClient.setProjId(project.id);

            // Create a table first so the project is not empty
            const tableName = `export_test_table_${Date.now()}`;
            await newClient.table.createActionTable({
                id: tableName,
                cols: [{ id: "input", dtype: "str" }]
            });

            const response = await newClient.projects.exportProject(project.id);

            expect(response).toBeInstanceOf(Uint8Array);
            expect(response.length).toBeGreaterThan(0);

            // Clean up the table
            await newClient.table.deleteTable({ table_type: "action", table_id: tableName });
        }
    });
});
