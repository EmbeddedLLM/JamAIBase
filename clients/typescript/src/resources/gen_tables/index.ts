import { Base } from "@/resources/base";

import { isRunningInBrowser } from "@/helpers/utils";
import { getFileName, getMimeType, readFile } from "@/helpers/utils.node";
import {
    AddActionColumnRequest,
    AddActionColumnRequestSchema,
    CreateActionTableRequest,
    CreateActionTableRequestSchema
} from "@/resources/gen_tables/action";
import {
    CreateChatTableRequest,
    CreateChatTableRequestSchema,
    GenTableRowsChatCompletionChunks,
    GenTableRowsChatCompletionChunksSchema,
    GenTableStreamChatCompletionChunk,
    GenTableStreamChatCompletionChunkSchema,
    GenTableStreamReferences,
    GenTableStreamReferencesSchema,
    GetConversationThreadRequest,
    GetConversationThreadRequestSchema,
    GetConversationThreadResponse,
    GetConversationThreadResponseSchema
} from "@/resources/gen_tables/chat";
import { CreateKnowledgeTableRequest, CreateKnowledgeTableRequestSchema, UploadFileRequest } from "@/resources/gen_tables/knowledge";
import {
    AddColumnRequest,
    AddColumnRequestSchema,
    AddRowRequest,
    DeleteRowRequest,
    DeleteRowsRequest,
    DeleteTableRequest,
    DropColumnsRequest,
    DuplicateTableRequest,
    DuplicateTableRequestSchema,
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
    ListTableRequestSchema,
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
    UpdateGenConfigRequestSchema,
    UpdateRowRequest
} from "@/resources/gen_tables/tables";
import { ChunkError } from "@/resources/shared/error";
import axios, { AxiosResponse } from "axios";
// import { Blob, FormData } from "formdata-node";

function createFormData() {
    if (isRunningInBrowser()) {
        // Node environment
        // (import from `formdata-node`)
        const { FormData } = require("formdata-node");
        return new FormData();
    } else {
        // Browser environment
        return new FormData();
    }
}

export class GenTable extends Base {
    // Helper method to handle stream responses
    private handleGenTableStreamResponse(
        response: AxiosResponse<any, any>
    ): ReadableStream<GenTableStreamChatCompletionChunk | GenTableStreamReferences> {
        this.logWarning(response);

        if (response.status != 200) {
            throw new Error(`Received Error Status: ${response.status}`);
        }

        return new ReadableStream<GenTableStreamChatCompletionChunk | GenTableStreamReferences>({
            async start(controller: ReadableStreamDefaultController<GenTableStreamChatCompletionChunk | GenTableStreamReferences>) {
                response.data.on("data", (data: any) => {
                    data = data.toString();
                    if (data.endsWith("\n\n")) {
                        const lines = data
                            .split("\n\n")
                            .filter((i: string) => i.trim())
                            .flatMap((line: string) => line.split("\n")); // Split by \n to handle collation

                        for (const line of lines) {
                            const chunk = line
                                .toString()
                                .replace(/^data: /, "")
                                .replace(/data: \[DONE\]\s+$/, "");

                            if (chunk.trim() === "[DONE]") return;

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

                        if (chunk.trim() === "[DONE]") return;

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
    }

    public async listTables(params: ListTableRequest): Promise<PageListTableMetaResponse> {
        const parsedParams = ListTableRequestSchema.parse(params);
        let getURL = `/api/v1/gen_tables/${params.table_type}`;

        delete (parsedParams as any).table_type;

        const response = await this.httpClient.get(getURL, {
            params: {
                ...parsedParams,
                search_query: encodeURIComponent(parsedParams.search_query)
            }
        });

        return this.handleResponse(response, PageListTableMetaResponseSchema);
    }

    public async getTable(params: TableMetaRequest): Promise<TableMetaResponse> {
        let getURL = `/api/v1/gen_tables/${params.table_type}/${params.table_id}`;

        const response = await this.httpClient.get(getURL);
        return this.handleResponse(response, TableMetaResponseSchema);
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
                vec_decimals: parsedParams.vec_decimals,
                order_descending: parsedParams.order_descending
            },
            paramsSerializer: (params) => {
                return Object.entries(params)
                    .flatMap(([key, value]) => (Array.isArray(value) ? value.map((val) => `${key}=${val}`) : `${key}=${value}`))
                    .join("&");
            }
        });

        return this.handleResponse(response, PageListTableRowsResponseSchema);
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

        return this.handleResponse(response, GetRowResponseSchema);
    }

    public async getConversationThread(params: GetConversationThreadRequest): Promise<GetConversationThreadResponse> {
        const parsedParams = GetConversationThreadRequestSchema.parse(params);

        let getURL = `/api/v1/gen_tables/${parsedParams.table_type}/${parsedParams.table_id}/thread`;
        const response = await this.httpClient.get(getURL, {
            params: {
                column_id: parsedParams.column_id,
                row_id: parsedParams.row_id,
                include: parsedParams.include
            }
        });

        return this.handleResponse(response, GetConversationThreadResponseSchema);
    }

    /*
     *  Gen Table Create
     */
    public async createActionTable(params: CreateActionTableRequest): Promise<TableMetaResponse> {
        const parsedParams = CreateActionTableRequestSchema.parse(params);
        const apiURL = "/api/v1/gen_tables/action";
        const response = await this.httpClient.post(
            apiURL,
            {
                ...parsedParams,
                stream: false
            },
            {}
        );
        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async createChatTable(params: CreateChatTableRequest): Promise<TableMetaResponse> {
        const parsedParams = CreateChatTableRequestSchema.parse(params);
        const apiURL = "/api/v1/gen_tables/chat";
        const response = await this.httpClient.post(apiURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async createKnowledgeTable(params: CreateKnowledgeTableRequest): Promise<TableMetaResponse> {
        const parsedParams = CreateKnowledgeTableRequestSchema.parse(params);
        const apiURL = "/api/v1/gen_tables/knowledge";
        const response = await this.httpClient.post(apiURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    /*
     *  Gen Table Delete
     */
    public async deleteTable(params: DeleteTableRequest): Promise<OkResponse> {
        let deleteURL = `/api/v1/gen_tables/${params.table_type}/${params.table_id}`;
        const response = await this.httpClient.delete(deleteURL);

        return this.handleResponse(response, OkResponseSchema);
    }

    public async deleteRow(params: DeleteRowRequest): Promise<OkResponse> {
        let deleteURL = `/api/v1/gen_tables/${params.table_type}/${params.table_id}/rows/${params.row_id}`;

        const response = await this.httpClient.delete(deleteURL, {
            params: {
                reindex: params?.reindex
            }
        });

        return this.handleResponse(response, OkResponseSchema);
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
        return this.handleResponse(response, OkResponseSchema);
    }

    /*
     * Gen Table Update
     */
    public async renameTable(params: RenameTableRequest): Promise<TableMetaResponse> {
        let postURL = `/api/v1/gen_tables/${params.table_type}/rename/${params.table_id_src}/${params.table_id_dst}`;
        const response = await this.httpClient.post(postURL, {}, {});

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async duplicateTable(params: DuplicateTableRequest): Promise<TableMetaResponse> {
        if ("deploy" in params) {
            console.warn(`The "deploy" argument is deprecated, use "create_as_child" instead.`);
            params.create_as_child = params.deploy as boolean;

            delete params.deploy;
        }

        const parsedParams = DuplicateTableRequestSchema.parse(params);

        let postURL = `/api/v1/gen_tables/${params.table_type}/duplicate/${params.table_id_src}`;
        const response = await this.httpClient.post(
            postURL,
            {},
            {
                params: {
                    table_id_dst: parsedParams.table_id_dst,
                    include_data: parsedParams.include_data,
                    create_as_child: parsedParams.create_as_child
                }
            }
        );

        return this.handleResponse(response, TableMetaResponseSchema);
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

        return this.handleResponse(response, TableMetaResponseSchema);
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

        return this.handleResponse(response, TableMetaResponseSchema);
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

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async addActionColumns(params: AddActionColumnRequest): Promise<TableMetaResponse> {
        const parsedParams = AddActionColumnRequestSchema.parse(params);
        let postURL = `/api/v1/gen_tables/action/columns/add`;

        const response = await this.httpClient.post(postURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async addKnowledgeColumns(params: AddColumnRequest): Promise<TableMetaResponse> {
        const parsedParams = AddColumnRequestSchema.parse(params);
        let postURL = `/api/v1/gen_tables/knowledge/columns/add`;
        const response = await this.httpClient.post(postURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async addChatColumns(params: AddColumnRequest): Promise<TableMetaResponse> {
        const parsedParams = AddColumnRequestSchema.parse(params);
        let postURL = `/api/v1/gen_tables/chat/columns/add`;
        const response = await this.httpClient.post(postURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async updateGenConfig(params: UpdateGenConfigRequest): Promise<TableMetaResponse> {
        const parsedParams = UpdateGenConfigRequestSchema.parse(params);
        let postURL = `/api/v1/gen_tables/${params.table_type}/gen_config/update`;
        const response = await this.httpClient.post(
            postURL,
            {
                table_id: parsedParams.table_id,
                column_map: parsedParams.column_map
            },
            {}
        );

        return this.handleResponse(response, TableMetaResponseSchema);
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

        return this.handleGenTableStreamResponse(response);
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

        return this.handleResponse(response, GenTableRowsChatCompletionChunksSchema);
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

        return this.handleGenTableStreamResponse(response);
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
        return this.handleResponse(response, GenTableRowsChatCompletionChunksSchema);
    }

    public async updateRow(params: UpdateRowRequest): Promise<OkResponse> {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/rows/update`;
        const response = await this.httpClient.post(apiURL, {
            table_id: params.table_id,
            row_id: params.row_id,
            data: params.data,
            reindex: params.reindex
        });

        return this.handleResponse(response, OkResponseSchema);
    }

    public async hybridSearch(params: HybridSearchRequest): Promise<HybridSearchResponse> {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/hybrid_search`;

        const { table_type, ...requestBody } = params;

        const response = await this.httpClient.post(apiURL, requestBody);

        return this.handleResponse(response, HybridSearchResponseSchema);
    }

    /**
     * @deprecated This method will be removed in future versions.
     * Use the embedFile method instead.
     */
    // Function to upload a file
    public async uploadFile(params: UploadFileRequest): Promise<OkResponse> {
        const apiURL = `/api/v1/gen_tables/knowledge/upload_file`;

        // Create FormData to send as multipart/form-data
        const formData = createFormData();
        if (params.file) {
            formData.append("file", params.file, params.file.name);
        } else if (params.file_path) {
            if (!isRunningInBrowser()) {
                const mimeType = await getMimeType(params.file_path!);
                const fileName = await getFileName(params.file_path!);
                const data = await readFile(params.file_path!);
                // const file = new Blob([data], { type: mimeType });
                const { File } = require("formdata-node");
                const file = new File([data], fileName, { type: mimeType });
                formData.append("file", file, fileName);
            } else {
                throw new Error("Pass File instead of file path if you are using this function in client.");
            }
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

        return this.handleResponse(response, OkResponseSchema);
    }

    public async embedFile(params: UploadFileRequest): Promise<OkResponse> {
        const apiURL = `/api/v1/gen_tables/knowledge/embed_file`;

        // Create FormData to send as multipart/form-data
        const formData = createFormData();
        if (params.file) {
            formData.append("file", params.file, params.file.name);
        } else if (params.file_path) {
            if (!isRunningInBrowser()) {
                const mimeType = await getMimeType(params.file_path!);
                const fileName = await getFileName(params.file_path!);
                const data = await readFile(params.file_path!);
                // const file = new Blob([data], { type: mimeType });
                const { File } = require("formdata-node");
                const file = new File([data], fileName, { type: mimeType });
                formData.append("file", file, fileName);
            } else {
                throw new Error("Pass File instead of file path if you are using this method in client.");
            }
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

        return this.handleResponse(response, OkResponseSchema);
    }

    public async importTableData(params: ImportTableRequest): Promise<GenTableRowsChatCompletionChunks> {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/import_data`;

        const delimiter = params.delimiter ? params.delimiter : ",";

        const formData = createFormData();
        if (params.file) {
            formData.append("file", params.file, params.file.name);
        } else if (params.file_path) {
            if (!isRunningInBrowser()) {
                const mimeType = await getMimeType(params.file_path!);
                const fileName = await getFileName(params.file_path!);
                const data = await readFile(params.file_path!);
                // const file = new Blob([data], { type: mimeType });
                const { File } = require("formdata-node");
                const file = new File([data], fileName, { type: mimeType });
                formData.append("file", file, fileName);
            } else {
                throw new Error("Pass File instead of file path if you are using this function in client.");
            }
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

        return this.handleResponse(response, GenTableRowsChatCompletionChunksSchema);
    }

    public async importTableDataStream(
        params: ImportTableRequest
    ): Promise<ReadableStream<GenTableStreamChatCompletionChunk | GenTableStreamReferences>> {
        const apiURL = `/api/v1/gen_tables/${params.table_type}/import_data`;
        // const fileName = params.file.name;
        const delimiter = params.delimiter ? params.delimiter : ",";

        const formData = new FormData();
        if (params.file) {
            formData.append("file", params.file, params.file.name);
        } else if (params.file_path) {
            if (!isRunningInBrowser()) {
                const mimeType = await getMimeType(params.file_path!);
                const fileName = await getFileName(params.file_path!);
                const data = await readFile(params.file_path!);
                // const file = new Blob([data], { type: mimeType });
                const { File } = require("formdata-node");
                const file = new File([data], fileName, { type: mimeType });

                formData.append("file", file, fileName);
            } else {
                throw new Error("Pass File instead of file path if you are using this function in client.");
            }
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

        return this.handleGenTableStreamResponse(response);
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

            return this.handleResponse(response);
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
