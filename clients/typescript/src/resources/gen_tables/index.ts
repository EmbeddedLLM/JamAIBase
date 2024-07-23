import { Base } from "@/resources/base";
import { promises as fs } from "fs";
import mime from "mime-types";

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
    ExportTableRequest,
    ExportTableRequestSchema,
    GetRowRequest,
    GetRowRequestSchema,
    GetRowResponse,
    GetRowResponseSchema,
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResponseSchema,
    ImportTableRequest,
    ListTableRequest,
    ListTableRowsRequest,
    ListTableRowsRequestSchema,
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
import axios from "axios";
import path from "path";

export class GenTable extends Base {
    public async listTables({ table_type, limit = 100, offset = 0, parent_id }: ListTableRequest): Promise<PageListTableMetaResponse> {
        let getURL = `/api/v1/gen_tables/${table_type}?offset=${offset}&limit=${limit}`;
        if (parent_id) {
            getURL = getURL + `&parent_id=${parent_id}`;
        }

        const response = await this.httpClient.get(getURL);

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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
        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = TableMetaResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async listRows(params: ListTableRowsRequest): Promise<PageListTableRowsResponse> {
        const parsedParams = ListTableRowsRequestSchema.parse(params);
        const response = await this.httpClient.get(`/api/v1/gen_tables/${parsedParams.table_type}/${parsedParams.table_id}/rows`, {
            params: {
                offset: parsedParams.offset,
                limit: parsedParams.limit,
                search_query: encodeURIComponent(parsedParams.search_query),
                columns: parsedParams.columns ? parsedParams.columns?.map(encodeURIComponent) : [],
                float_decimals: parsedParams.float_decimals,
                vec_decimals: parsedParams.vec_decimals
            },
            paramsSerializer: (params) => {
                return Object.entries(params)
                    .flatMap(([key, value]) => (Array.isArray(value) ? value.map((val) => `${key}=${val}`) : `${key}=${value}`))
                    .join("&");
            }
        });

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

        if (response.status == 200) {
            const parsedData = PageListTableRowsResponseSchema.parse(response.data);
            return parsedData;
        } else {
            throw new Error(`Received Error Status: ${response.status}`);
        }
    }

    public async getRow(params: GetRowRequest): Promise<GetRowResponse> {
        const parsedParams = GetRowRequestSchema.parse(params);
        const response = await this.httpClient.get(`/api/v1/gen_tables/${params.table_type}/${params.table_id}/rows/${params.row_id}`, {
            params: {
                columns: parsedParams.columns ? parsedParams.columns?.map(encodeURIComponent) : [],
                float_decimals: parsedParams.float_decimals,
                vec_decimals: parsedParams.vec_decimals
            },
            paramsSerializer: (params) => {
                return Object.entries(params)
                    .flatMap(([key, value]) => (Array.isArray(value) ? value.map((val) => `${key}=${val}`) : `${key}=${value}`))
                    .join("&");
            }
        });

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

        if (response.status == 200) {
            const parsedData = GetRowResponseSchema.parse(response.data);
            return parsedData;
        } else {
            throw new Error(`Received Error Status: ${response.status}`);
        }
    }

    public async getConversationThread(params: GetConversationThreadRequest): Promise<GetConversationThreadResponse> {
        let getURL = `/api/v1/gen_tables/chat/${params.table_id}/thread?table_id=${params.table_id}`;
        const response = await this.httpClient.get(getURL);

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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
        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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
        if (params.file) {
            formData.append("file", params.file);
            formData.append("file_name", params.file.name);
        } else if (params.file_path) {
            const mimeType = mime.lookup(params.file_path!) || "application/octet-stream";
            const fileName = path.basename(params.file_path!);
            const data = await fs.readFile(params.file_path!);
            const file = new Blob([data], { type: mimeType });
            formData.append("file", file);
            formData.append("file_name", fileName);
        } else {
            throw new Error("Either File or file_path is required.");
        }
        formData.append("table_id", params.table_id);

        // Optional: Add additional fields if required by the API
        if (params?.chunk_size) {
            formData.append("chunk_size", params.chunk_size.toString());
        }
        if (params?.chunk_overlap) {
            formData.append("chunk_overlap", params.chunk_overlap.toString());
        }

        const response = await this.httpClient.post<OkResponse>(apiURL, formData, {
            headers: {
                "Content-Type": "multipart/form-data"
            }
        });

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

        if (response.status != 200) {
            throw new Error(`Received Error Status: ${response.status}`);
        }

        return response.data;
    }

    public async importTableData(params: ImportTableRequest): Promise<GenTableRowsChatCompletionChunks> {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/import_data`;

        const delimiter = params.delimiter ? params.delimiter : ",";

        const formData = new FormData();

        if (params.file) {
            formData.append("file", params.file);
            formData.append("file_name", params.file.name);
        } else if (params.file_path) {
            const mimeType = mime.lookup(params.file_path!) || "application/octet-stream";
            const fileName = path.basename(params.file_path!);
            const data = await fs.readFile(params.file_path!);
            const file = new Blob([data], { type: mimeType });
            formData.append("file", file);
            formData.append("file_name", fileName);
        } else {
            throw new Error("Either File or file_path is required.");
        }

        formData.append("table_id", params.table_id);
        formData.append("delimiter", delimiter);
        formData.append("stream", JSON.stringify(false));

        const response = await this.httpClient.post(apiURL, formData, {
            headers: {
                "Content-Type": "multipart/form-data"
            }
        });

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

        if (response.status != 200) {
            throw new Error(`Received Error Status: ${response.status}`);
        }

        const parsedData = GenTableRowsChatCompletionChunksSchema.parse(response.data);

        return parsedData;
    }

    public async importTableDataStream(
        params: ImportTableRequest
    ): Promise<ReadableStream<GenTableStreamChatCompletionChunk | GenTableStreamReferences>> {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/import_data`;
        // const fileName = params.file.name;
        const delimiter = params.delimiter ? params.delimiter : ",";

        const formData = new FormData();

        if (params.file) {
            formData.append("file", params.file);
            formData.append("file_name", params.file.name);
        } else if (params.file_path) {
            const mimeType = mime.lookup(params.file_path!) || "application/octet-stream";
            const fileName = path.basename(params.file_path!);
            const data = await fs.readFile(params.file_path!);
            const file = new Blob([data], { type: mimeType });
            formData.append("file", file);
            formData.append("file_name", fileName);
        } else {
            throw new Error("Either File or file_path is required.");
        }

        formData.append("table_id", params.table_id);
        formData.append("delimiter", delimiter);
        formData.append("stream", JSON.stringify(true));

        const response = await this.httpClient.post(apiURL, formData, {
            headers: {
                "Content-Type": "multipart/form-data"
            },
            responseType: "stream"
        });

        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }

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

    public async exportTableData(params: ExportTableRequest): Promise<Uint8Array> {
        const parsedParams = ExportTableRequestSchema.parse(params);

        const apiURL = `/api/v1/gen_tables/${parsedParams.table_type}/${encodeURIComponent(parsedParams.table_id)}/export_data`;
        try {
            const response = await this.httpClient.get(apiURL, {
                params: {
                    delimiter: encodeURIComponent(parsedParams.delimiter),
                    columns: parsedParams.columns ? parsedParams.columns?.map(encodeURIComponent) : []
                },
                paramsSerializer: (params) => {
                    return Object.entries(params)
                        .flatMap(([key, value]) => (Array.isArray(value) ? value.map((val) => `${key}=${val}`) : `${key}=${value}`))
                        .join("&");
                },
                responseType: "arraybuffer"
            });

            const warning = response.headers["warning"];
            if (warning) {
                console.warn(warning);
            }

            if (response.status != 200) {
                throw new Error(`Received Error Status: ${response.status}`);
            }

            return new Uint8Array(response.data);
        } catch (error) {
            if (axios.isAxiosError(error)) {
                // Convert buffer data to string for better readability in error
                if (error.response && error.response.data) {
                    error.response.data = JSON.parse(new TextDecoder().decode(error.response.data));
                }
            }
            throw error;
        }
    }
}
