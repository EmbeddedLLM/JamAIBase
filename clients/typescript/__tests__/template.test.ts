import JamAI from "@/index";
import {
    GetTableResponseSchema,
    GetTemplateResponseSchema,
    ListTableRowsResponseSchema,
    ListTablesResponseSchema,
    ListTemplatesResponseSchema
} from "@/resources/templates/types";
import dotenv from "dotenv";
import { v4 as uuidv4 } from "uuid";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Templates", () => {
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

    it("list templates", async () => {
        const response = await client.template.listTemplates();

        const parsedData = ListTemplatesResponseSchema.parse(response);
        expect(parsedData).toEqual(response);
    });

    it("get template", async () => {
        const templates = await client.template.listTemplates({});

        if (templates.items.length && templates.items[0]) {
            const response = await client.template.getTemplate({ template_id: templates.items[0].id });

            const parsedData = GetTemplateResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
        }
    });

    it("list tables", async () => {
        const templates = await client.template.listTemplates();

        if (templates.items.length && templates.items[0]) {
            const response = await client.template.listTables({
                template_id: templates.items[0].id,
                table_type: "action"
            });

            const parsedData = ListTablesResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
        }
    });

    it("get table", async () => {
        const templates = await client.template.listTemplates();

        if (templates.items.length && templates.items[0]) {
            const tables = await client.template.listTables({
                template_id: templates.items[0].id,
                table_type: "action"
            });

            if (tables.items.length && tables.items[0]) {
                const response = await client.template.getTable({
                    template_id: templates.items[0].id,
                    table_type: "action",
                    table_id: tables.items[0].id
                });

                const parsedData = GetTableResponseSchema.parse(response);
                expect(parsedData).toEqual(response);
            }
        }
    });

    it("list table rows", async () => {
        const templates = await client.template.listTemplates();

        if (templates.items.length && templates.items[0]) {
            const tables = await client.template.listTables({
                template_id: templates.items[0].id,
                table_type: "action"
            });

            if (tables.items.length && tables.items[0]) {
                const response = await client.template.listTableRows({
                    template_id: templates.items[0].id,
                    table_type: "action",
                    table_id: tables.items[0].id
                });

                const parsedData = ListTableRowsResponseSchema.parse(response);
                expect(parsedData).toEqual(response);
            }
        }
    });
});
