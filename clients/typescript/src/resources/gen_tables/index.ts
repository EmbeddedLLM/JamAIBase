import { Base } from "@/resources/base";

import { isRunningInBrowser, serializeParams } from "@/helpers/utils";
import { getFileName, getMimeType, readFile } from "@/helpers/utils.node";
import {
    AddActionColumnRequest,
    AddActionColumnRequestSchema,
    CreateActionTableRequest,
    CreateActionTableRequestSchema
} from "@/resources/gen_tables/action";
import {
    CellCompletionResponse,
    CellReferencesResponse,
    ColumnCompletionResponseSchema,
    CreateChatTableRequest,
    CreateChatTableRequestSchema,
    GetConversationThreadRequest,
    GetConversationThreadRequestSchema,
    GetConversationThreadResponse,
    GetConversationThreadResponseSchema,
    MultiRowCompletionResponse,
    MultiRowCompletionResponseSchema,
    RowReferencesResponseSchema
} from "@/resources/gen_tables/chat";
import { CreateKnowledgeTableRequest, CreateKnowledgeTableRequestSchema, UploadFileRequest } from "@/resources/gen_tables/knowledge";
import {
    AddColumnRequest,
    AddColumnRequestSchema,
    AddRowRequest,
    AddRowRequestSchema,
    DeleteRowsRequest,
    DeleteRowsRequestSchema,
    DeleteTableRequest,
    DeleteTableRequestSchema,
    DropColumnsRequest,
    DropColumnsRequestSchema,
    DuplicateTableRequest,
    DuplicateTableRequestSchema,
    ExportTableRequest,
    ExportTableRequestSchema,
    GetRowRequest,
    GetRowRequestSchema,
    GetRowResponse,
    GetRowResponseSchema,
    HybridSearchRequest,
    HybridSearchRequestSchema,
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
    RegenRowRequestSchema,
    RenameColumnsRequest,
    RenameColumnsRequestSchema,
    RenameTableRequest,
    RenameTableRequestSchema,
    ReorderColumnsRequest,
    ReorderColumnsRequestSchema,
    TableMetaRequest,
    TableMetaRequestSchema,
    TableMetaResponse,
    TableMetaResponseSchema,
    UpdateGenConfigRequest,
    UpdateGenConfigRequestSchema,
    UpdateRowRequest,
    UpdateRowRequestSchema
} from "@/resources/gen_tables/tables";
import { ChunkError } from "@/resources/shared/error";
import axios, { AxiosResponse } from "axios";
// import { Blob, FormData } from "formdata-node";

async function createFormData() {
    if (!isRunningInBrowser()) {
        // Node environment
        // (import from `formdata-node`)
        const { FormData } = await import("formdata-node");

        return new FormData();
    } else {
        // Browser environment
        return new FormData();
    }
}

export class GenTable extends Base {
    // Helper method to handle stream responses
    private handleGenTableStreamResponse(response: AxiosResponse<any, any>): ReadableStream<CellCompletionResponse | CellReferencesResponse> {
        this.logWarning(response);

        if (response.status != 200) {
            throw new Error(`Received Error Status: ${response.status}`);
        }

        return new ReadableStream<CellCompletionResponse | CellReferencesResponse>({
            async start(controller: ReadableStreamDefaultController<CellCompletionResponse | CellReferencesResponse>) {
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
                                    controller.enqueue(ColumnCompletionResponseSchema.parse(parsedValue));
                                } else if (parsedValue["object"] === "gen_table.references") {
                                    controller.enqueue(RowReferencesResponseSchema.parse(parsedValue));
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
                                controller.enqueue(ColumnCompletionResponseSchema.parse(parsedValue));
                            } else if (parsedValue["object"] === "gen_table.references") {
                                controller.enqueue(RowReferencesResponseSchema.parse(parsedValue));
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
        let getURL = `/api/v2/gen_tables/${params.table_type}/list`;

        const response = await this.httpClient.get(getURL, {
            params: parsedParams
        });

        return this.handleResponse(response, PageListTableMetaResponseSchema);
    }

    public async getTable(params: TableMetaRequest): Promise<TableMetaResponse> {
        const parsedParams = TableMetaRequestSchema.parse(params);
        let getURL = `/api/v2/gen_tables/${params.table_type}`;

        const response = await this.httpClient.get(getURL, {
            params: parsedParams
        });
        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async listRows(params: ListTableRowsRequest): Promise<PageListTableRowsResponse> {
        const parsedParams = ListTableRowsRequestSchema.parse(params);
        const response = await this.httpClient.get(`/api/v2/gen_tables/${parsedParams.table_type}/rows/list`, {
            params: parsedParams,
            paramsSerializer: serializeParams
        });

        return this.handleResponse(response, PageListTableRowsResponseSchema);
    }

    public async getRow(params: GetRowRequest): Promise<GetRowResponse> {
        const parsedParams = GetRowRequestSchema.parse(params);
        const response = await this.httpClient.get(`/api/v2/gen_tables/${params.table_type}/rows`, {
            params: parsedParams,
            paramsSerializer: serializeParams
        });

        return this.handleResponse(response, GetRowResponseSchema);
    }

    public async getConversationThread(params: GetConversationThreadRequest): Promise<GetConversationThreadResponse> {
        const parsedParams = GetConversationThreadRequestSchema.parse(params);

        let getURL = `/api/v2/gen_tables/${parsedParams.table_type}/threads`;
        const response = await this.httpClient.get(getURL, {
            params: parsedParams,
            paramsSerializer: serializeParams
        });

        return this.handleResponse(response, GetConversationThreadResponseSchema);
    }

    /*
     *  Gen Table Create
     */
    public async createActionTable(params: CreateActionTableRequest): Promise<TableMetaResponse> {
        const parsedParams = CreateActionTableRequestSchema.parse(params);
        const apiURL = "/api/v2/gen_tables/action";
        const response = await this.httpClient.post(apiURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async createChatTable(params: CreateChatTableRequest): Promise<TableMetaResponse> {
        const parsedParams = CreateChatTableRequestSchema.parse(params);
        const apiURL = "/api/v2/gen_tables/chat";
        const response = await this.httpClient.post(apiURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async createKnowledgeTable(params: CreateKnowledgeTableRequest): Promise<TableMetaResponse> {
        const parsedParams = CreateKnowledgeTableRequestSchema.parse(params);
        const apiURL = "/api/v2/gen_tables/knowledge";
        const response = await this.httpClient.post(apiURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    /*
     *  Gen Table Delete
     */
    public async deleteTable(params: DeleteTableRequest): Promise<OkResponse> {
        const parsedParams = DeleteTableRequestSchema.parse(params);
        let deleteURL = `/api/v2/gen_tables/${params.table_type}`;
        const response = await this.httpClient.delete(deleteURL, {
            params: parsedParams
        });

        return this.handleResponse(response, OkResponseSchema);
    }

    // public async deleteRow(params: DeleteRowRequest): Promise<OkResponse> {
    //     let deleteURL = `/api/v2/gen_tables/${params.table_type}/${params.table_id}/rows/${params.row_id}`;

    //     const response = await this.httpClient.delete(deleteURL, {
    //         params: {
    //             reindex: params?.reindex
    //         }
    //     });

    //     return this.handleResponse(response, OkResponseSchema);
    // }

    /**
     * @param {string} [params.where] - Optional. SQL where clause. If not provided, will match all rows and thus deleting all table content.
     */
    public async deleteRows(params: DeleteRowsRequest): Promise<OkResponse> {
        const parsedParams = DeleteRowsRequestSchema.parse(params);
        const apiURL = `/api/v2/gen_tables/${params.table_type}/rows/delete`;
        const response = await this.httpClient.post(apiURL, parsedParams);

        return this.handleResponse(response, OkResponseSchema);
    }

    /*
     * Gen Table Update
     */
    public async renameTable(params: RenameTableRequest): Promise<TableMetaResponse> {
        const parsedParams = RenameTableRequestSchema.parse(params);
        let postURL = `/api/v2/gen_tables/${params.table_type}/rename`;
        const response = await this.httpClient.post(postURL, undefined, { params: parsedParams });

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async duplicateTable(params: DuplicateTableRequest): Promise<TableMetaResponse> {
        if ("deploy" in params) {
            console.warn(`The "deploy" argument is deprecated, use "create_as_child" instead.`);
            params.create_as_child = params.deploy as boolean;

            delete params.deploy;
        }

        const parsedParams = DuplicateTableRequestSchema.parse(params);
        let postURL = `/api/v2/gen_tables/${params.table_type}/duplicate`;
        const response = await this.httpClient.post(postURL, undefined, {
            params: parsedParams
        });

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async renameColumns(params: RenameColumnsRequest): Promise<TableMetaResponse> {
        const parsedParams = RenameColumnsRequestSchema.parse(params);
        let postURL = `/api/v2/gen_tables/${params.table_type}/columns/rename`;
        const response = await this.httpClient.post(postURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async reorderColumns(params: ReorderColumnsRequest): Promise<TableMetaResponse> {
        const parsedParams = ReorderColumnsRequestSchema.parse(params);
        let postURL = `/api/v2/gen_tables/${params.table_type}/columns/reorder`;
        const response = await this.httpClient.post(postURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async dropColumns(params: DropColumnsRequest): Promise<TableMetaResponse> {
        const parsedParams = DropColumnsRequestSchema.parse(params);
        let postURL = `/api/v2/gen_tables/${params.table_type}/columns/drop`;
        const response = await this.httpClient.post(postURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async addActionColumns(params: AddActionColumnRequest): Promise<TableMetaResponse> {
        const parsedParams = AddActionColumnRequestSchema.parse(params);
        let postURL = `/api/v2/gen_tables/action/columns/add`;
        const response = await this.httpClient.post(postURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async addKnowledgeColumns(params: AddColumnRequest): Promise<TableMetaResponse> {
        const parsedParams = AddColumnRequestSchema.parse(params);
        let postURL = `/api/v2/gen_tables/knowledge/columns/add`;
        const response = await this.httpClient.post(postURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async addChatColumns(params: AddColumnRequest): Promise<TableMetaResponse> {
        const parsedParams = AddColumnRequestSchema.parse(params);
        let postURL = `/api/v2/gen_tables/chat/columns/add`;
        const response = await this.httpClient.post(postURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async updateGenConfig(params: UpdateGenConfigRequest): Promise<TableMetaResponse> {
        const parsedParams = UpdateGenConfigRequestSchema.parse(params);
        let postURL = `/api/v2/gen_tables/${params.table_type}/gen_config`;
        const response = await this.httpClient.patch(postURL, parsedParams);

        return this.handleResponse(response, TableMetaResponseSchema);
    }

    public async addRowStream(params: AddRowRequest): Promise<ReadableStream<CellCompletionResponse | CellReferencesResponse>> {
        const parsedParams = AddRowRequestSchema.parse(params);
        const apiURL = `/api/v2/gen_tables/${params.table_type}/rows/add`;
        const response = await this.httpClient.post(
            apiURL,
            {
                ...parsedParams,
                stream: true
            },
            {
                responseType: "stream"
            }
        );

        return this.handleGenTableStreamResponse(response);
    }

    public async addRow(params: AddRowRequest): Promise<MultiRowCompletionResponse> {
        const parsedParams = AddRowRequestSchema.parse(params);
        const url = `/api/v2/gen_tables/${params.table_type}/rows/add`;
        const response = await this.httpClient.post(
            url,
            {
                ...parsedParams,
                stream: false
            },
            {}
        );

        return this.handleResponse(response, MultiRowCompletionResponseSchema);
    }

    public async regenRowStream(params: RegenRowRequest) {
        const parsedParams = RegenRowRequestSchema.parse(params);
        const apiURL = `/api/v2/gen_tables/${params.table_type}/rows/regen`;
        const response = await this.httpClient.post(
            apiURL,
            {
                ...parsedParams,
                stream: true
            },
            {
                responseType: "stream"
            }
        );

        return this.handleGenTableStreamResponse(response);
    }

    public async regenRow(params: RegenRowRequest): Promise<MultiRowCompletionResponse> {
        const parsedParams = RegenRowRequestSchema.parse(params);
        const apiURL = `/api/v2/gen_tables/${params.table_type}/rows/regen`;
        const response = await this.httpClient.post(
            apiURL,
            {
                ...parsedParams,
                stream: false
            },
            {}
        );

        return this.handleResponse(response, MultiRowCompletionResponseSchema);
    }

    /**
     * @deprecated Deprecated since 0.4.0, use updateRows instead
     */
    public async updateRow(params: UpdateRowRequest & { row_id: string }): Promise<OkResponse> {
        const apiURL = `/api/v2/gen_tables/${params.table_type}/rows`;
        const response = await this.httpClient.patch(apiURL, {
            table_id: params.table_id,
            data: {
                [params.row_id]: params.data
            }
        });

        return this.handleResponse(response, OkResponseSchema);
    }

    public async updateRows(params: UpdateRowRequest): Promise<OkResponse> {
        const parsedParams = UpdateRowRequestSchema.parse(params);
        const apiURL = `/api/v2/gen_tables/${params.table_type}/rows`;
        const response = await this.httpClient.patch(apiURL, parsedParams);

        return this.handleResponse(response, OkResponseSchema);
    }

    public async hybridSearch(params: HybridSearchRequest): Promise<HybridSearchResponse> {
        const parsedParams = HybridSearchRequestSchema.parse(params);
        const apiURL = `/api/v2/gen_tables/${parsedParams.table_type}/hybrid_search`;

        const { table_type, ...requestBody } = parsedParams;

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
        const formData = await createFormData();
        if (params.file) {
            formData.append("file", params.file, params.file.name);
        } else if (params.file_path) {
            if (!isRunningInBrowser()) {
                const mimeType = await getMimeType(params.file_path!);
                const fileName = await getFileName(params.file_path!);
                const data = await readFile(params.file_path!);
                const { File } = await import("formdata-node");
                const file = new File([data], fileName, { type: mimeType });

                // @ts-ignore
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
        const apiURL = `/api/v2/gen_tables/knowledge/embed_file`;

        // Create FormData to send as multipart/form-data
        const formData = await createFormData();
        if (params.file) {
            formData.append("file", params.file, params.file.name);
        } else if (params.file_path) {
            if (!isRunningInBrowser()) {
                const mimeType = await getMimeType(params.file_path!);
                const fileName = await getFileName(params.file_path!);
                const data = await readFile(params.file_path!);
                const { File } = await import("formdata-node");
                const file = new File([data], fileName, { type: mimeType });

                // @ts-ignore
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

    public async importTableData(params: ImportTableRequest): Promise<MultiRowCompletionResponse> {
        const apiURL = `/api/v2/gen_tables/${params.table_type}/import_data`;

        const formData = await createFormData();
        if (params.file) {
            formData.append("file", params.file, params.file.name);
        } else if (params.file_path) {
            if (!isRunningInBrowser()) {
                const mimeType = await getMimeType(params.file_path!);
                const fileName = await getFileName(params.file_path!);
                const data = await readFile(params.file_path!);
                // const file = new Blob([data], { type: mimeType });
                const { File } = await import("formdata-node");
                const file = new File([data], fileName, { type: mimeType });
                // @ts-ignore
                formData.append("file", file, fileName);
            } else {
                throw new Error("Pass File instead of file path if you are using this function in client.");
            }
        } else {
            throw new Error("Either File or file_path is required.");
        }

        formData.append("table_id", params.table_id);
        if (params.delimiter) formData.append("delimiter", params.delimiter);
        formData.append("stream", JSON.stringify(false));

        const response = await this.httpClient.post(apiURL, formData, {
            headers: {
                "Content-Type": "multipart/form-data"
            }
        });

        return this.handleResponse(response, MultiRowCompletionResponseSchema);
    }

    public async importTableDataStream(params: ImportTableRequest): Promise<ReadableStream<CellCompletionResponse | CellReferencesResponse>> {
        const apiURL = `/api/v2/gen_tables/${params.table_type}/import_data`;
        // const fileName = params.file.name;
        const delimiter = params.delimiter ? params.delimiter : ",";

        const formData = await createFormData();
        if (params.file) {
            formData.append("file", params.file, params.file.name);
        } else if (params.file_path) {
            if (!isRunningInBrowser()) {
                const mimeType = await getMimeType(params.file_path!);
                const fileName = await getFileName(params.file_path!);
                const data = await readFile(params.file_path!);

                const { File } = await import("formdata-node");
                const file = new File([data], fileName, { type: mimeType });
                // @ts-ignore
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

        const apiURL = `/api/v2/gen_tables/${parsedParams.table_type}/export_data`;
        try {
            const response = await this.httpClient.get(apiURL, {
                params: parsedParams,
                paramsSerializer: serializeParams,
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

    /**
     * Get conversation threads (multi-column support)
     * @param params Request parameters
     * @returns Conversation threads
     */
    public async getConversationThreads(params: {
        table_type: string;
        table_id: string;
        column_ids?: string[];
        row_id?: string;
        include_row?: boolean;
    }): Promise<any> {
        const response = await this.httpClient.get(`/api/v2/gen_tables/${params.table_type}/threads`, {
            params: {
                table_id: params.table_id,
                column_ids: params.column_ids,
                row_id: params.row_id,
                include_row: params.include_row
            }
        });

        return this.handleResponse(response);
    }

    /**
     * Import table (schema and data) from parquet file
     * @param tableType Table type
     * @param params Import parameters
     * @returns Table metadata or OK response
     */
    public async importTable(params: { table_type: string; file: File; table_id?: string; blocking?: boolean }): Promise<any> {
        const formData = new FormData();
        formData.append("file", params.file);
        if (params.table_id) formData.append("table_id", params.table_id);
        if (params.blocking !== undefined) formData.append("blocking", JSON.stringify(params.blocking));

        const response = await this.httpClient.post(`/api/v2/gen_tables/${params.table_type}/import`, formData, {
            headers: { "Content-Type": "multipart/form-data" }
        });

        return this.handleResponse(response);
    }

    /**
     * Export table (schema and data) as parquet file
     * @param tableType Table type
     * @param tableId Table ID
     * @returns Table file as bytes
     */
    public async exportTable(tableType: string, tableId: string): Promise<Uint8Array> {
        const response = await this.httpClient.get(`/api/v2/gen_tables/${tableType}/export`, {
            params: { table_id: tableId },
            responseType: "arraybuffer"
        });

        return this.handleResponse(response);
    }
}
