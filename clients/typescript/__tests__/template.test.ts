import JamAI from "@/index";
import {
    GetTableResponseSchema,
    GetTemplateResponseSchema,
    ListTableRowsResponseSchema,
    ListTablesResponseSchema,
    ListTemplatesResponseSchema
} from "@/resources/templates/types";
import dotenv from "dotenv";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Templates", () => {
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
