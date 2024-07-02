import { Base } from "@/resources/base";

import { AddActionColumnRequest, CreateActionTableRequest } from "@/resources/gen_tables/action";
import {
    CreateChatTableRequest,
    GenTableRowsChatCompletionChunks,
    GenTableRowsChatCompletionChunksSchema,
    GenTableStreamChatCompletionChunk,
    GenTableStreamChatCompletionChunkSchema,
    GenTableStreamReferences,
    GenTableStreamReferencesSchema,
    GetConversationThreadRequest,
    GetConversationThreadResponse,
    GetConversationThreadResponseSchema
} from "@/resources/gen_tables/chat";
import { CreateKnowledgeTableRequest, UploadFileRequest } from "@/resources/gen_tables/knowledge";
import {
    AddColumnRequest,
    AddRowRequest,
    DeleteRowRequest,
    DeleteRowsRequest,
    DeleteTableRequest,
    DropColumnsRequest,
    DuplicateTableRequest,
    GetRowRequest,
    GetRowResponse,
    GetRowResponseSchema,
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResponseSchema,
    ListTableRequest,
    ListTableRowsRequest,
    OkResponse,
    OkResponseSchema,
    PageListTableMetaResponse,
    PageListTableMetaResponseSchema,
    PageListTableRowsResponse,
    PageListTableRowsResponseSchema,
    RegenRowRequest,
    RenameColumnsRequest,
    RenameTableRequest,
    ReorderColumnsRequest,
    TableMetaRequest,
    TableMetaResponse,
    TableMetaResponseSchema,
    UpdateGenConfigRequest,
    UpdateRowRequest
} from "@/resources/gen_tables/tables";
import { ChunkError } from "@/resources/shared/error";

export class GenTable extends Base {
    public async listTables({ table_type, limit = 100, offset = 0, parent_id }: ListTableRequest): Promise<PageListTableMetaResponse> {
        let getURL = `/api/v1/gen_tables/${table_type}?offset=${offset}&limit=${limit}`;
        if (parent_id) {
            getURL = getURL + `&parent_id=${parent_id}`;
        }

        const response = await this.httpClient.get(getURL);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = PageListTableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async getTable(params: TableMetaRequest): Promise<TableMetaResponse> {
        let getURL = `/api/v1/gen_tables/${params.table_type}/${params.table_id}`;

        const response = await this.httpClient.get(getURL);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async listRows({ columns, limit = 100, offset = 0, table_id, table_type }: ListTableRowsRequest): Promise<PageListTableRowsResponse> {
        let getURL = `/api/v1/gen_tables/${table_type}/${table_id}/rows?offset=${offset}&limit=${limit}`;

        if (columns) {
            const queryString = columns.map((param) => `columns=${encodeURIComponent(param)}`).join("&");
            getURL = getURL + "&" + queryString;
        }
        const response = await this.httpClient.get(getURL);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = PageListTableRowsResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async getRow(params: GetRowRequest): Promise<GetRowResponse> {
        let getURL = `/api/v1/gen_tables/${params.table_type}/${params.table_id}/rows/${params.row_id}`;

        if (params.columns) {
            const queryString = params.columns.map((param) => `columns=${encodeURIComponent(param)}`).join("&");
            getURL = getURL + "?" + queryString;
        }
        const response = await this.httpClient.get(getURL);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = GetRowResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async getConversationThread(params: GetConversationThreadRequest): Promise<GetConversationThreadResponse> {
        let getURL = `/api/v1/gen_tables/chat/${params.table_id}/thread?table_id=${params.table_id}`;
        const response = await this.httpClient.get(getURL);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = GetConversationThreadResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    /*
     *  Gen Table Create
     */
    public async createActionTable(params: CreateActionTableRequest): Promise<TableMetaResponse> {
        const apiURL = "/api/v1/gen_tables/action";
        const response = await this.httpClient.post(
            apiURL,
            {
                ...params,
                stream: false
            },
            {}
        );

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async createChatTable(params: CreateChatTableRequest): Promise<TableMetaResponse> {
        const apiURL = "/api/v1/gen_tables/chat";
        const response = await this.httpClient.post(apiURL, params);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async createKnowledgeTable(params: CreateKnowledgeTableRequest): Promise<TableMetaResponse> {
        const apiURL = "/api/v1/gen_tables/knowledge";
        const response = await this.httpClient.post(apiURL, params);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    /*
     *  Gen Table Delete
     */
    public async deleteTable(params: DeleteTableRequest): Promise<OkResponse> {
        let deleteURL = `/api/v1/gen_tables/${params.table_type}/${params.table_id}`;
        const response = await this.httpClient.delete(deleteURL);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = OkResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async deleteRow(params: DeleteRowRequest): Promise<OkResponse> {
        let deleteURL = `/api/v1/gen_tables/${params.table_type}/${params.table_id}/rows/${params.row_id}`;

        const response = await this.httpClient.delete(deleteURL, {
            params: {
                reindex: params?.reindex
            }
        });

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = OkResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    /**
     * @param {string} [params.where] - Optional. SQL where clause. If not provided, will match all rows and thus deleting all table content.
     */
    public async deleteRows(params: DeleteRowsRequest): Promise<OkResponse> {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/rows/delete`;
        const response = await this.httpClient.post(apiURL, {
            table_id: params.table_id,
            where: params.where // Optional. SQL where clause. If not provided, will match all rows and thus deleting all table content.
        });

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                resolve(OkResponseSchema.parse({ ok: true }));
            } else {
                console.error("Received Error Status: ", response.status);
                resolve(OkResponseSchema.parse({ ok: false }));
            }
        });
    }

    /*
     * Gen Table Update
     */

    public async renameTable(params: RenameTableRequest): Promise<TableMetaResponse> {
        let postURL = `/api/v1/gen_tables/${params.table_type}/rename/${params.table_id_src}/${params.table_id_dst}`;
        const response = await this.httpClient.post(postURL, {}, {});

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async duplicateTable({
        table_id_dst,
        table_id_src,
        table_type,
        include_data = true,
        deploy = false
    }: DuplicateTableRequest): Promise<TableMetaResponse> {
        let postURL = `/api/v1/gen_tables/${table_type}/duplicate/${table_id_src}/${table_id_dst}?include_data=${include_data}&deploy=${deploy}`;
        const response = await this.httpClient.post(postURL, {}, {});

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async renameColumns(params: RenameColumnsRequest): Promise<TableMetaResponse> {
        let postURL = `/api/v1/gen_tables/${params.table_type}/columns/rename`;
        const response = await this.httpClient.post(
            postURL,
            {
                table_id: params.table_id,
                column_map: params.column_map
            },
            {}
        );

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async reorderColumns(params: ReorderColumnsRequest): Promise<TableMetaResponse> {
        let postURL = `/api/v1/gen_tables/${params.table_type}/columns/reorder`;
        const response = await this.httpClient.post(
            postURL,
            {
                table_id: params.table_id,
                column_names: params.column_names
            },
            {}
        );

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async dropColumns(params: DropColumnsRequest): Promise<TableMetaResponse> {
        let postURL = `/api/v1/gen_tables/${params.table_type}/columns/drop`;
        const response = await this.httpClient.post(
            postURL,
            {
                table_id: params.table_id,
                column_names: params.column_names
            },
            {}
        );

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async addActionColumns(params: AddActionColumnRequest): Promise<TableMetaResponse> {
        let postURL = `/api/v1/gen_tables/action/columns/add`;

        const response = await this.httpClient.post(postURL, params);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async addKnowledgeColumns(params: AddColumnRequest): Promise<TableMetaResponse> {
        let postURL = `/api/v1/gen_tables/knowledge/columns/add`;
        const response = await this.httpClient.post(postURL, params);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async addChatColumns(params: AddColumnRequest): Promise<TableMetaResponse> {
        let postURL = `/api/v1/gen_tables/chat/columns/add`;
        const response = await this.httpClient.post(postURL, params);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async updateGenConfig(params: UpdateGenConfigRequest): Promise<TableMetaResponse> {
        let postURL = `/api/v1/gen_tables/${params.table_type}/gen_config/update`;
        const response = await this.httpClient.post(
            postURL,
            {
                table_id: params.table_id,
                column_map: params.column_map
            },
            {}
        );

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async addRowStream(params: AddRowRequest): Promise<ReadableStream<GenTableStreamChatCompletionChunk | GenTableStreamReferences>> {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/rows/add`;

        const response = await this.httpClient.post(
            apiURL,
            {
                table_id: params.table_id,
                data: params.data,
                stream: true,
                reindex: params.reindex,
                concurrent: params.concurrent
            },
            {
                responseType: "stream"
            }
        );

        if (response.status != 200) {
            throw new Error(`Received Error Status: ${response.status}`);
        }

        const stream = new ReadableStream<GenTableStreamChatCompletionChunk | GenTableStreamReferences>({
            async start(controller: ReadableStreamDefaultController<GenTableStreamChatCompletionChunk | GenTableStreamReferences>) {
                response.data.on("data", (data: any) => {
                    data = data.toString();
                    if (data.endsWith("\n\n")) {
                        const lines = data
                            .split("\n\n")
                            .filter((i: string) => i.trim())
                            .flatMap((line: string) => line.split("\n")); //? Split by \n to handle collation
                        for (const line of lines) {
                            const chunk = line
                                .toString()
                                .replace(/^data: /, "")
                                .replace(/data: \[DONE\]\s+$/, "");

                            if (chunk.trim() == "[DONE]") return;

                            try {
                                const parsedValue = JSON.parse(chunk);
                                if (parsedValue["object"] === "gen_table.completion.chunk") {
                                    controller.enqueue(GenTableStreamChatCompletionChunkSchema.parse(parsedValue));
                                } else if (parsedValue["object"] === "gen_table.references") {
                                    controller.enqueue(GenTableStreamReferencesSchema.parse(parsedValue));
                                } else {
                                    throw new ChunkError(`Unexpected SSE Chunk: ${parsedValue}`);
                                }
                            } catch (err: any) {
                                if (err instanceof ChunkError) {
                                    controller.error(new ChunkError(err.message));
                                } else {
                                    continue;
                                }
                            }
                        }
                    } else {
                        const chunk = data
                            .toString()
                            .replace(/^data: /, "")
                            .replace(/data: \[DONE\]\s+$/, "");

                        if (chunk.trim() == "[DONE]") return;

                        try {
                            const parsedValue = JSON.parse(chunk);
                            if (parsedValue["object"] === "gen_table.completion.chunk") {
                                controller.enqueue(GenTableStreamChatCompletionChunkSchema.parse(parsedValue));
                            } else if (parsedValue["object"] === "gen_table.references") {
                                controller.enqueue(GenTableStreamReferencesSchema.parse(parsedValue));
                            } else {
                                throw new ChunkError(`Unexpected SSE Chunk: ${parsedValue}`);
                            }
                        } catch (err: any) {
                            if (err instanceof ChunkError) {
                                controller.error(new ChunkError(err.message));
                            }
                        }
                    }
                });

                response.data.on("error", (data: any) => {
                    controller.error("Unexpected Error.");
                });

                response.data.on("end", () => {
                    if (controller.desiredSize !== null) {
                        controller.close();
                    }
                });
            }
        });

        return stream;
    }

    public async addRow(params: AddRowRequest): Promise<GenTableRowsChatCompletionChunks> {
        const url = `/api/v1/gen_tables/${params.table_type}/rows/add`;
        const response = await this.httpClient.post(
            url,
            {
                table_id: params.table_id,
                stream: false,
                data: params.data,
                reindex: params.reindex,
                concurrent: params.concurrent
            },
            {}
        );

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = GenTableRowsChatCompletionChunksSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async regenRowStream(params: RegenRowRequest) {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/rows/regen`;

        const response = await this.httpClient.post(
            apiURL,
            {
                table_id: params.table_id,
                row_ids: params.row_ids,
                stream: true,
                reindex: params.reindex,
                concurrent: params.concurrent
            },
            {
                responseType: "stream"
            }
        );

        if (response.status != 200) {
            throw new Error(`Received Error Status: ${response.status}`);
        }

        const stream = new ReadableStream<GenTableStreamChatCompletionChunk | GenTableStreamReferences>({
            async start(controller: ReadableStreamDefaultController<GenTableStreamChatCompletionChunk | GenTableStreamReferences>) {
                response.data.on("data", (data: any) => {
                    data = data.toString();
                    if (data.endsWith("\n\n")) {
                        const lines = data
                            .split("\n\n")
                            .filter((i: string) => i.trim())
                            .flatMap((line: string) => line.split("\n")); //? Split by \n to handle collation

                        for (const line of lines) {
                            const chunk = line
                                .toString()
                                .replace(/^data: /, "")
                                .replace(/data: \[DONE\]\s+$/, "");

                            if (chunk.trim() == "[DONE]") return;

                            try {
                                const parsedValue = JSON.parse(chunk);
                                if (parsedValue["object"] === "gen_table.completion.chunk") {
                                    controller.enqueue(GenTableStreamChatCompletionChunkSchema.parse(parsedValue));
                                } else if (parsedValue["object"] === "gen_table.references") {
                                    controller.enqueue(GenTableStreamReferencesSchema.parse(parsedValue));
                                } else {
                                    throw new ChunkError(`Unexpected SSE Chunk: ${parsedValue}`);
                                }
                            } catch (err) {
                                if (err instanceof ChunkError) {
                                    controller.error(new ChunkError(err.message));
                                }
                                continue;
                            }
                        }
                    } else {
                        const chunk = data
                            .toString()
                            .replace(/^data: /, "")
                            .replace(/data: \[DONE\]\s+$/, "");

                        if (chunk.trim() == "[DONE]") return;

                        try {
                            const parsedValue = JSON.parse(chunk);
                            if (parsedValue["object"] === "gen_table.completion.chunk") {
                                controller.enqueue(GenTableStreamChatCompletionChunkSchema.parse(parsedValue));
                            } else if (parsedValue["object"] === "gen_table.references") {
                                controller.enqueue(GenTableStreamReferencesSchema.parse(parsedValue));
                            } else {
                                throw new ChunkError(`Unexpected SSE Chunk: ${parsedValue}`);
                            }
                        } catch (err: any) {
                            if (err instanceof ChunkError) {
                                controller.error(new ChunkError(err.message));
                            }
                        }
                    }
                });

                response.data.on("error", (data: any) => {
                    controller.error("Unexpected error.");
                });

                response.data.on("end", () => {
                    if (controller.desiredSize !== null) {
                        controller.close();
                    }
                });
            }
        });

        return stream;
    }

    public async regenRow(params: RegenRowRequest): Promise<GenTableRowsChatCompletionChunks> {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/rows/regen`;
        const response = await this.httpClient.post(
            apiURL,
            {
                table_id: params.table_id,
                row_ids: params.row_ids,
                stream: false,
                reindex: params.reindex,
                concurrent: params.concurrent
            },
            {}
        );

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = GenTableRowsChatCompletionChunksSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async updateRow(params: UpdateRowRequest): Promise<OkResponse> {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/rows/update`;
        const response = await this.httpClient.post(apiURL, {
            table_id: params.table_id,
            row_id: params.row_id,
            data: params.data,
            reindex: params.reindex
        });

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                resolve(OkResponseSchema.parse({ ok: true }));
            } else {
                console.error("Received Error Status: ", response.status);
                resolve(OkResponseSchema.parse({ ok: false }));
            }
        });
    }

    public async hybridSearch(params: HybridSearchRequest): Promise<HybridSearchResponse> {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/hybrid_search`;

        const { table_type, ...requestBody } = params;

        const response = await this.httpClient.post(apiURL, requestBody);

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = HybridSearchResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    // Function to upload a file
    public async uploadFile(params: UploadFileRequest): Promise<OkResponse> {
        const apiURL = `/api/v1/gen_tables/knowledge/upload_file`;
        // Create FormData to send as multipart/form-data
        const formData = new FormData();
        formData.append("file", params.file);
        formData.append("file_name", params.file_name);
        formData.append("table_id", params.table_id);

        // Optional: Add additional fields if required by the API
        if (params?.chunk_size) {
            formData.append("chunk_size", params.chunk_size.toString());
        }
        if (params?.chunk_overlap) {
            formData.append("chunk_overlap", params.chunk_overlap.toString());
        }

        try {
            const response = await this.httpClient.post<OkResponse>(apiURL, formData, {
                headers: {
                    "Content-Type": "multipart/form-data"
                }
            });

            return response.data;
        } catch (error) {
            // Handle error here
            console.error("Error uploading file:", error);
            throw error;
        }
    }
}
