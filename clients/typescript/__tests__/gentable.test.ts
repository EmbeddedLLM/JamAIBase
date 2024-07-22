import JamAI from "@/index";
import tmp from "tmp";

import { GenTableRowsChatCompletionChunksSchema, GetConversationThreadResponseSchema } from "@/resources/gen_tables/chat";
import {
    ColumnSchema,
    ColumnSchemaCreate,
    GetRowResponseSchema,
    HybridSearchResponseSchema,
    PageListTableMetaResponseSchema,
    PageListTableRowsResponseSchema,
    TableMetaResponseSchema
} from "@/resources/gen_tables/tables";
import { beforeAll, describe, expect, it, jest } from "@jest/globals";
import { AssertionError } from "assert";
import csvParser from "csv-parser";
import dotenv from "dotenv";
import { promises as fs } from "fs";
import { Readable } from "stream";
import { v4 as uuidv4 } from "uuid";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Gentable Action Table API", () => {
    let client: JamAI;
    jest.setTimeout(30000);
    jest.retryTimes(1, {
        logErrorsBeforeRetry: true
    });

    beforeAll(() => {
        client = new JamAI({
            baseURL: process.env["BASEURL"]!,
            apiKey: process.env["JAMAI_APIKEY"]!,
            projectId: process.env["PROJECT_ID"]!
        });
    });

    async function* _getTable(tableType: string) {
        // setup
        let myuuid = uuidv4();
        let table_id = `unittest-${myuuid}`;

        if (tableType === "action") {
            const createActionTableResponse = await client.createActionTable({
                id: table_id,
                cols: [
                    {
                        id: "question",
                        dtype: "str",
                        index: true
                    },
                    {
                        id: "suggestions",
                        dtype: "str",
                        gen_config: {
                            model: "openai/gpt-3.5-turbo",
                            messages: [
                                {
                                    role: "system",
                                    content: ""
                                },
                                {
                                    role: "user",
                                    content: "Suggest a followup questions on ${question}."
                                }
                            ],
                            temperature: 1,
                            max_tokens: 100,
                            top_p: 0.1
                        }
                    },
                    {
                        id: "suggestions2",
                        dtype: "str",
                        gen_config: {
                            model: "openai/gpt-3.5-turbo",
                            messages: [
                                {
                                    role: "system",
                                    content: ""
                                },
                                {
                                    role: "user",
                                    content: "Suggest a followup questions on ${question}."
                                }
                            ],
                            temperature: 1,
                            max_tokens: 100,
                            top_p: 0.1
                        }
                    }
                ]
            });
        } else if (tableType === "knowledge") {
            const response = await client.createKnowledgeTable({
                embedding_model: "openai/text-embedding-3-large-1024",
                id: table_id,
                cols: []
            });
            // console.log(`CONTEXT MANAGER: createKnowledgeTable ${tableType}`);
        } else if (tableType === "chat") {
            const response = await client.createChatTable({
                id: table_id,
                cols: [
                    {
                        id: "User",
                        dtype: "str"
                    },
                    {
                        id: "AI",
                        dtype: "str",
                        gen_config: {
                            model: "",
                            messages: [
                                {
                                    role: "system",
                                    content: ""
                                }
                            ]
                        }
                    }
                ]
            });
        } else {
            throw new AssertionError({
                message: "tableType must be `action`, `knowledge` or `chat`"
            });
        }

        const getTableResponse = await client.getTable({
            table_type: tableType,
            table_id: table_id
        });

        // console.log(`CONTEXT MANAGER: getTableResponse ${tableType}`);

        const parsedgetTableResponseData = TableMetaResponseSchema.parse(getTableResponse);
        expect(parsedgetTableResponseData).toEqual(getTableResponse);

        try {
            yield parsedgetTableResponseData;
        } finally {
            // cleanup
            const deleteTableResponse = await client.deleteTable({
                table_id: table_id,
                table_type: tableType
            });

            expect(deleteTableResponse).toHaveProperty("ok");
            expect(deleteTableResponse.ok).toBeTruthy();

            const listTablesResponse = await client.listTables({
                table_type: tableType
            });

            const parsedlistTablesResponseData = PageListTableMetaResponseSchema.parse(listTablesResponse);
            let tableList: string[] = [];
            for (const item of parsedlistTablesResponseData.items) {
                if (item.id === table_id) {
                    tableList.push(table_id);
                }
            }
            expect(tableList.length).toEqual(0);
        }
    }

    // Convert CSV to JSON
    async function _csvToJson(csvData: Uint8Array, separator?: string): Promise<{ [key: string]: any }[]> {
        const readableStream = new Readable();
        readableStream.push(Buffer.from(csvData));
        readableStream.push(null);

        if (!separator) {
            separator = ",";
        }

        return new Promise((resolve, reject) => {
            const results: { [key: string]: any }[] = [];
            readableStream
                .pipe(csvParser({ separator: separator }))
                .on("data", (data) => results.push(data))
                .on("end", () => resolve(results))
                .on("error", (error) => reject(error));
        });
    }

    async function _dfToCsv(data: any[], filePath: string): Promise<void> {
        const header = Object.keys(data[0]).join(",");
        const rows = data.map((row) =>
            Object.values(row)
                .map((value) => (typeof value === "string" ? `"${value}"` : value))
                .join(",")
        );
        const csvContent = [header, ...rows].join("\n");
        await fs.writeFile(filePath, csvContent);
    }

    it("get table - action table creation and deletion", async () => {
        // let myuuid = getRandomInt(1000);
        let myuuid = uuidv4();
        const actionTableId = `unittest-createActionTable-${myuuid}`;
        const createActionTableResponse = await client.createActionTable({
            id: actionTableId,
            cols: [
                {
                    id: "question",
                    dtype: "str",
                    index: true
                },
                {
                    id: "suggestions",
                    dtype: "str",
                    gen_config: {
                        model: "openai/gpt-3.5-turbo",
                        messages: [
                            {
                                role: "system",
                                content: ""
                            },
                            {
                                role: "user",
                                content: "Suggest a followup questions on ${question}."
                            }
                        ],
                        temperature: 1,
                        max_tokens: 100,
                        top_p: 0.1
                    }
                }
            ]
        });

        const getTableResponse = await client.getTable({
            table_type: "action",
            table_id: actionTableId
        });

        const parsedgetTableResponseData = TableMetaResponseSchema.parse(getTableResponse);
        expect(parsedgetTableResponseData).toEqual(getTableResponse);

        const deleteTableResponse = await client.deleteTable({
            table_id: actionTableId,
            table_type: "action"
        });

        expect(deleteTableResponse).toHaveProperty("ok");
        expect(deleteTableResponse.ok).toBeTruthy();

        const listTablesResponse = await client.listTables({
            table_type: "action"
        });

        const parsedlistTablesResponseData = PageListTableMetaResponseSchema.parse(listTablesResponse);
        let tableList = [];
        for (const item of parsedlistTablesResponseData.items) {
            if (item.id === actionTableId) {
                tableList.push();
            }
        }
        expect(tableList.length).toEqual(0);
    });

    it("list tables - action - without limit and offset", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.listTables({
                table_type: "action"
            });

            const parsedData = PageListTableMetaResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
            let tableList: string[] = [];
            for (const item of parsedData.items) {
                if (item.id === table_id) {
                    tableList.push(item.id);
                }
            }
            expect(tableList.length).toEqual(1);
        }
    });

    it("list tables - action - with limit", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.listTables({
                table_type: "action",
                limit: 3
            });

            const parsedData = PageListTableMetaResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
            let tableList: string[] = [];
            for (const item of parsedData.items) {
                if (item.id === table_id) {
                    tableList.push(item.id);
                }
            }
            expect(tableList.length).toEqual(1);
        }
    });

    it("list tables - action - with offset", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.listTables({
                table_type: "action",
                offset: 3
            });

            const parsedData = PageListTableMetaResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
        }
    });

    it("list tables - action - with limit and offset", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.listTables({
                table_type: "action",
                limit: 3,
                offset: 1
            });

            const parsedData = PageListTableMetaResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
        }
    });

    it("list tables - knowledge - with limit and offset", async () => {
        for await (const { id: table_id } of _getTable("knowledge")) {
            const response = await client.listTables({
                table_type: "knowledge",
                limit: 3,
                offset: 0
            });

            const parsedData = PageListTableMetaResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
            let tableList: string[] = [];
            for (const item of parsedData.items) {
                if (item.id === table_id) {
                    tableList.push(item.id);
                }
            }
            expect(tableList.length).toEqual(1);
        }
    });

    it("list tables - chat - with limit and offset", async () => {
        for await (const { id: table_id } of _getTable("chat")) {
            const response = await client.listTables({
                table_type: "chat",
                limit: 1
            });

            const parsedData = PageListTableMetaResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
            let tableList: string[] = [];
            for (const item of parsedData.items) {
                if (item.id === table_id) {
                    tableList.push(item.id);
                }
            }
            expect(tableList.length).toEqual(1);
        }
    });

    it("get table - action", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.getTable({
                table_type: "action",
                table_id: table_id
            });

            const parsedData = TableMetaResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
        }
    });

    it("get table - knowledge", async () => {
        for await (const { id: table_id } of _getTable("knowledge")) {
            const response = await client.getTable({
                table_type: "knowledge",
                table_id: table_id
            });

            const parsedData = TableMetaResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
        }
    });

    it("get table - chat", async () => {
        for await (const { id: table_id } of _getTable("chat")) {
            const response = await client.getTable({
                table_type: "chat",
                table_id: table_id
            });

            const parsedData = TableMetaResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
        }
    });

    it("add row to action table with reindex", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    }
                ],
                table_id: table_id,
                reindex: true,
                concurrent: true
            });

            const parsedData = GenTableRowsChatCompletionChunksSchema.parse(response);
            expect(parsedData).toEqual(response);
        }
    });

    it("add row to action table without reindex", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });

            const parsedData = GenTableRowsChatCompletionChunksSchema.parse(response);
            expect(parsedData).toEqual(response);
        }
    });

    it("add row to action table - stream with reindex", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRowStream({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    }
                ],
                table_id: table_id,
                reindex: true,
                concurrent: true
            });

            expect(response).toBeInstanceOf(ReadableStream);
            const reader = response.getReader();
            let chunk_count: number = 0;
            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    break;
                }
                // console.log(value) ;
                chunk_count += 1;
            }
            expect(chunk_count).toBeGreaterThan(2);
        }
    });

    it("add row to action table - stream without reindex", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRowStream({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });

            expect(response).toBeInstanceOf(ReadableStream);
            const reader = response.getReader();
            let chunk_count: number = 0;
            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    break;
                }
                // console.log(value) ;
                chunk_count += 1;
            }
            expect(chunk_count).toBeGreaterThan(2);
        }
    });

    it("list rows - without limit and offset", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });
            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id
            });

            const parsedData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedData).toEqual(listRowResponse);
            expect(parsedData.items.length).toEqual(4);
        }
    });

    it("list rows - without limit", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });

            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id,
                offset: 3
            });

            const parsedData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedData).toEqual(listRowResponse);
            expect(parsedData.items.length).toEqual(1);
        }
    });

    it("list rows - without offset", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });

            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id,
                limit: 2
            });

            const parsedData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedData).toEqual(listRowResponse);
            expect(parsedData.items.length).toEqual(2);
        }
    });

    it("list rows - with offset and limit", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });

            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id,
                offset: 0,
                limit: 1
            });

            const parsedData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedData).toEqual(listRowResponse);
            expect(parsedData.items.length).toEqual(1);
        }
    });

    it("list rows - with column ids", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });

            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id,
                columns: ["question"]
            });

            const parsedData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedData).toEqual(listRowResponse);
            expect(parsedData.items.length).toEqual(4);
        }
    });

    it("get row - with row id", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });

            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id,
                limit: 2
            });

            const parsedData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedData).toEqual(listRowResponse);
            expect(parsedData.items.length).toEqual(2);
            // console.log(parsedData.items);
            const getRowResponse = await client.getRow({
                table_type: "action",
                table_id: table_id,
                row_id: parsedData.items![0]!["ID"]!
            });
            const parsedgetRowResponseData = GetRowResponseSchema.parse(getRowResponse);
            expect(parsedgetRowResponseData).toEqual(getRowResponse);
        }
    });

    it("get row - with multiple columns", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });

            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id,
                limit: 2
            });

            const parsedData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedData).toEqual(listRowResponse);
            expect(parsedData.items.length).toEqual(2);
            // console.log(parsedData.items);
            const getRowResponse = await client.getRow({
                table_type: "action",
                table_id: table_id,
                row_id: parsedData.items![0]!["ID"]!,
                columns: ["question", "suggestions"]
            });
            const parsedgetRowResponseData = GetRowResponseSchema.parse(getRowResponse);
            expect(parsedgetRowResponseData).toEqual(getRowResponse);

            parsedgetRowResponseData!["question"]!;
            parsedgetRowResponseData!["suggestions"]!;
        }
    });

    it("delete row from action table", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });

            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id
            });

            const parsedData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedData).toEqual(listRowResponse);
            expect(parsedData.items.length).toEqual(4);

            // console.log(parsedData.items![0]!['ID']!);

            const deleteRowResponse = await client.deleteRow({
                table_id: table_id,
                table_type: "action",
                row_id: parsedData.items![0]!["ID"]!,
                reindex: true
            });

            expect(deleteRowResponse).toHaveProperty("ok");
            expect(deleteRowResponse.ok).toBeTruthy();

            const listRowResponse2 = await client.listRows({
                table_type: "action",
                table_id: table_id
            });

            const parsedlistRowResponse2Data = PageListTableRowsResponseSchema.parse(listRowResponse2);
            expect(parsedlistRowResponse2Data).toEqual(listRowResponse2);
            expect(parsedlistRowResponse2Data.items.length).toEqual(3);
        }
    });

    it("delete multiple rows", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });

            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id
            });

            const parsedData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedData).toEqual(listRowResponse);
            expect(parsedData.items.length).toEqual(4);

            let row_ids: string[] = [];

            for (const item of parsedData.items) {
                row_ids.push(item!["ID"]!);
            }

            // console.log(parsedData.items![0]!['ID']!);

            const deleteRowsResponse = await client.deleteRows({
                table_type: "action",
                table_id: table_id,
                where: `\`ID\` IN (${row_ids.map((i) => `'${i}'`).join(",")})`,
                reindex: true
            });

            expect(deleteRowsResponse).toHaveProperty("ok");
            expect(deleteRowsResponse.ok).toBeTruthy();

            const listRowResponse2 = await client.listRows({
                table_type: "action",
                table_id: table_id
            });

            const parsedlistRowResponse2Data = PageListTableRowsResponseSchema.parse(listRowResponse2);
            expect(parsedlistRowResponse2Data).toEqual(listRowResponse2);
            expect(parsedlistRowResponse2Data.items.length).toEqual(0);
        }
    });

    it("rename action table", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const table_id_dst = `unittest-rename-table-${uuidv4()}`;

            const renameTableResponse = await client.renameTable({
                table_id_src: table_id,
                table_type: "action",
                table_id_dst: table_id_dst
            });

            expect(renameTableResponse).toHaveProperty("id");
            expect(renameTableResponse["id"]).toEqual(table_id_dst);

            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id_dst,
                reindex: false,
                concurrent: true
            });

            const renameTableResponse2 = await client.renameTable({
                table_id_src: table_id_dst,
                table_type: "action",
                table_id_dst: table_id
            });
            expect(renameTableResponse2).toHaveProperty("id");
            expect(renameTableResponse2["id"]).toEqual(table_id);
        }
    });

    it("rename knowledge table", async () => {
        for await (const { id: table_id } of _getTable("knowledge")) {
            const table_id_dst = `unittest-rename-table-${uuidv4()}`;

            const renameTableResponse = await client.renameTable({
                table_id_src: table_id,
                table_type: "knowledge",
                table_id_dst: table_id_dst
            });

            expect(renameTableResponse).toHaveProperty("id");
            expect(renameTableResponse["id"]).toEqual(table_id_dst);

            const renameTableResponse2 = await client.renameTable({
                table_id_src: table_id_dst,
                table_type: "knowledge",
                table_id_dst: table_id
            });
            expect(renameTableResponse2).toHaveProperty("id");
            expect(renameTableResponse2["id"]).toEqual(table_id);
        }
    });

    it("duplicate table - without data", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const table_id_dst = `unittest-duplicated-without-data-${uuidv4()}`;

            const response = await client.duplicateTable({
                table_id_src: table_id,
                table_type: "action",
                table_id_dst: table_id_dst,
                include_data: false
            });

            expect(response).toHaveProperty("id");
            expect(response["id"]).toEqual(table_id_dst);

            const deleteTableResponse = await client.deleteTable({
                table_id: table_id_dst,
                table_type: "action"
            });
        }
    });

    it("get conversation thread", async () => {
        for await (const { id: table_id } of _getTable("chat")) {
            const response = await client.getConversationThread({
                table_id: table_id
            });

            const parsedData = GetConversationThreadResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
        }
    });

    it("rename column", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const columnMap = {
                question: "renamed-question"
            };

            const response = await client.renameColumns({
                table_type: "action",
                table_id: table_id,
                column_map: columnMap
            });

            expect(response).toHaveProperty("cols");

            const cols = response["cols"] as ColumnSchema[];

            const colsId = cols.map((col) => col.id);

            const expectedProperties = Object.values(columnMap);

            for (let i = 0; i < expectedProperties.length; i++) {
                const property = expectedProperties[i];

                expect(colsId.includes(property!)).toBeTruthy();
            }
        }
    });

    it("reorder columns", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.reorderColumns({
                table_id: table_id,
                table_type: "action",
                column_names: ["question", "suggestions2", "suggestions"]
            });

            const parsedData = TableMetaResponseSchema.parse(response);
            expect(parsedData).toEqual(response);
        }
    });

    it("add action columns", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const columnsToAdd: ColumnSchemaCreate[] = [
                {
                    id: "height2",
                    dtype: "str"
                }
            ];

            const response = await client.addActionColumns({
                id: table_id,
                cols: columnsToAdd
            });

            const colsIds = (response["cols"] as ColumnSchemaCreate[]).map((col) => col.id);

            expect(columnsToAdd.every((item) => colsIds.includes(item.id))).toBeTruthy();
        }
    });

    it("drop columns", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const dropedColumns = ["suggestions"];
            const response = await client.dropColumns({
                table_id: table_id,
                table_type: "action",
                column_names: dropedColumns
            });

            const colsIds = (response["cols"] as ColumnSchema[]).map((col) => col.id);

            expect(dropedColumns.every((item) => !colsIds.includes(item))).toBeTruthy();
        }
    });

    it("update gen config", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.updateGenConfig({
                table_type: "action",
                table_id: table_id,
                column_map: {
                    suggestions: {
                        model: "openai/gpt-3.5-turbo",
                        messages: [
                            {
                                role: "system",
                                content: "this is system prompt with updated config"
                            }
                        ]
                    }
                }
            });

            const parsedData = TableMetaResponseSchema.parse(response);
            expect(response).toEqual(parsedData);
        }
    });

    it("regen row - action table", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const response = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: true,
                concurrent: true
            });

            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id
            });

            const parsedlistRowResponseData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedlistRowResponseData).toEqual(listRowResponse);
            expect(parsedlistRowResponseData.items.length).toEqual(4);

            let row_ids: string[] = [];

            for (const item of parsedlistRowResponseData.items) {
                row_ids.push(item!["ID"]!);
            }

            // console.log(parsedlistRowResponseData);
            // console.log(row_ids);

            const regenRowResponse = await client.regenRow({
                table_type: "action",
                table_id: table_id,
                row_ids: row_ids,
                reindex: true,
                concurrent: true
            });

            // @TODO
            // verify that the suggestions output is different after regen

            // const parsedregenRowResponseData = GenTableRowsChatCompletionChunksSchema.parse(regenRowResponse);
            // expect(parsedregenRowResponseData).toEqual(regenRowResponse);

            // const listRowResponse2 = await client.listRows({
            //     table_type: "action",
            //     table_id: table_id,
            // });

            // const parsedlistRowResponse2Data = PageListTableRowsResponseSchema.parse(listRowResponse2);
            // expect(parsedlistRowResponse2Data).toEqual(listRowResponse2);
            // expect(parsedlistRowResponse2Data.items.length).toEqual(0);
        }
    });

    it("regen row - action table - stream", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: true,
                concurrent: true
            });

            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id
            });

            const parsedlistRowResponseData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedlistRowResponseData).toEqual(listRowResponse);
            expect(parsedlistRowResponseData.items.length).toEqual(4);

            let row_ids: string[] = [];

            for (const item of parsedlistRowResponseData.items) {
                row_ids.push(item!["ID"]!);
            }

            // console.log(parsedlistRowResponseData);
            // console.log(row_ids);

            const response = await client.regenRowStream({
                table_type: "action",
                table_id: table_id,
                row_ids: row_ids,
                reindex: null,
                concurrent: true
            });

            expect(response).toBeInstanceOf(ReadableStream);

            const reader = response.getReader();
            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    break;
                }
                // console.log(GenTableStreamChatCompletionChunkSchema.parse(value));
            }
        }
    });

    it("update row", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });
            const listRowResponse = await client.listRows({
                table_type: "action",
                table_id: table_id,
                limit: 2
            });

            const parsedData = PageListTableRowsResponseSchema.parse(listRowResponse);
            expect(parsedData).toEqual(listRowResponse);
            expect(parsedData.items.length).toEqual(2);

            const response = await client.updateRow({
                table_type: "action",
                data: {
                    question: "how to update rows on jamaibase?",
                    suggestions: "References at https://embeddedllm.github.io/jamaisdk-ts-docs/index.html"
                },
                table_id: table_id,
                row_id: parsedData.items![0]!["ID"]!,
                reindex: true
            });

            expect(response).toHaveProperty("ok");
            expect(response.ok).toBeTruthy();
        }
    });

    it("hybrid search", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: true,
                concurrent: true
            });
            const response = await client.hybridSearch({
                table_type: "action",
                table_id: table_id,
                query: "kong",
                where: null,
                limit: 3,
                metric: "dot",
                nprobes: 50,
                refine_factor: 50,
                reranking_model: null
            });
            const prasedData = HybridSearchResponseSchema.parse(response);
            expect(prasedData).toEqual(response);
        }
    });

    // @TODO test with api.jamaibase.com
    it("upload file to knowledge table", async () => {
        for await (const { id: table_id } of _getTable("knowledge")) {
            const file = new File(["My aim in life by chatgpt"], "sample.txt", { type: "text/plain" });
            const response = await client.uploadFile({
                file: file,
                table_id: table_id
            });

            expect(response?.ok).toBeTruthy();
        }
    });

    it("Export table data in csv", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const responseAddRow = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });
            const responseListRows = await client.listRows({
                table_type: "action",
                table_id: table_id
            });

            expect(responseAddRow.rows.length).toBe(responseListRows.items.length);

            const exportTableDataResponse = await client.exportTableData({
                table_type: "action",
                table_id: table_id
            });

            expect(exportTableDataResponse).toBeInstanceOf(Uint8Array);

            const exportedRows = await _csvToJson(exportTableDataResponse);
            expect(exportedRows.length).toBe(responseAddRow.rows.length);

            for (let i = 0; i < responseListRows.items.length; i++) {
                const row = exportedRows[exportedRows.length - 1 - i];
                const original = responseListRows.items[i];
                for (const key in original) {
                    if (row && key !== "ID" && key !== "Updated at") {
                        expect(row[key]).toEqual(original[key]["value"]);
                    }
                }
            }
        }
    });

    it("Export table data in tsv", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            const responseAddRow = await client.addRow({
                table_type: "action",
                data: [
                    {
                        question: "What is penguin?"
                    },
                    {
                        question: "What is help?"
                    },
                    {
                        question: "What is lol?"
                    },
                    {
                        question: "What is kong?"
                    }
                ],
                table_id: table_id,
                reindex: false,
                concurrent: true
            });
            const responseListRows = await client.listRows({
                table_type: "action",
                table_id: table_id
            });

            expect(responseAddRow.rows.length).toBe(responseListRows.items.length);

            const exportTableDataResponse = await client.exportTableData({
                table_type: "action",
                table_id: table_id,
                delimiter: "\t"
            });

            expect(exportTableDataResponse).toBeInstanceOf(Uint8Array);

            const exportedRows = await _csvToJson(exportTableDataResponse, "\t");
            expect(exportedRows.length).toBe(responseAddRow.rows.length);

            for (let i = 0; i < responseListRows.items.length; i++) {
                const row = exportedRows[exportedRows.length - 1 - i];
                const original = responseListRows.items[i];
                for (const key in original) {
                    if (row && key !== "ID" && key !== "Updated at") {
                        expect(row[key]).toEqual(original[key]["value"]);
                    }
                }
            }
        }
    });

    it("import table data", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            // Create CSV file
            const tmpobj = tmp.fileSync({ prefix: "prefix-", postfix: ".csv" });
            const filePath = tmpobj.name;

            const data = [
                {
                    question: "What is penguin?"
                },
                {
                    question: "What is help?"
                },
                {
                    question: "What is lol?"
                },
                {
                    question: "What is kong?"
                }
            ];

            await _dfToCsv(data, filePath);

            const importDataResponse = await client.importTableData({
                file_path: filePath,
                table_id: table_id,
                table_type: "action"
            });

            tmpobj.removeCallback();

            const rows = await client.listRows({
                table_type: "action",
                table_id: table_id
            });

            expect(importDataResponse.rows.length).toBe(rows.items.length);

            expect(Array.isArray(rows.items)).toBe(true);

            for (const [row, d] of rows.items.reverse().map((row: any, i) => [row, data[i]])) {
                for (const [k, v] of Object.entries(d!)) {
                    if (!(k in row!)) continue;
                    if (row && k in row) {
                        if (v === "") {
                            expect(row[k].value).toBeNull();
                        } else {
                            expect(row[k].value).toBe(v);
                        }
                    }
                }
            }
        }
    });

    it("import table data - stream", async () => {
        for await (const { id: table_id } of _getTable("action")) {
            // Create CSV file
            const tmpobj = tmp.fileSync({ prefix: "prefix-", postfix: ".csv" });
            const filePath = tmpobj.name;

            const data = [
                {
                    question: "What is penguin?"
                },
                {
                    question: "What is help?"
                },
                {
                    question: "What is lol?"
                },
                {
                    question: "What is kong?"
                }
            ];

            await _dfToCsv(data, filePath);

            const importDataResponse = await client.importTableDataStream({
                file_path: filePath,
                table_id: table_id,
                table_type: "action"
            });

            tmpobj.removeCallback();

            expect(importDataResponse).toBeInstanceOf(ReadableStream);
        }
    });
});
