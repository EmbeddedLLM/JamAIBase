import { Base } from "@/resources/base";
import {
    GetTableRequestSchema,
    GetTableResponseSchema,
    GetTemplateRequestSchema,
    GetTemplateResponseSchema,
    IGetTableRequest,
    IGetTableResponse,
    IGetTemplateRequest,
    IGetTemplateResponse,
    IListTableRowsRequest,
    IListTableRowsResponse,
    IListTablesRequest,
    IListTablesResponse,
    IListTemplatesRequest,
    IListTemplatesResponse,
    ListTableRowsRequestSchema,
    ListTableRowsResponseSchema,
    ListTablesRequestSchema,
    ListTablesResponseSchema,
    ListTemplatesRequestSchema,
    ListTemplatesResponseSchema
} from "./types";

export class Templates extends Base {
    public async listTemplates(params?: IListTemplatesRequest): Promise<IListTemplatesResponse> {
        const parsedParams = ListTemplatesRequestSchema.parse(params ?? {});

        let getURL = `/api/v2/templates/list`;

        const response = await this.httpClient.get(getURL, {
            params: parsedParams
        });

        return this.handleResponse(response, ListTemplatesResponseSchema);
    }

    public async getTemplate(params: IGetTemplateRequest): Promise<IGetTemplateResponse> {
        const parsedParams = GetTemplateRequestSchema.parse(params);
        let getURL = `/api/v2/templates`;

        const response = await this.httpClient.get(getURL, {
            params: parsedParams
        });

        return this.handleResponse(response, GetTemplateResponseSchema);
    }

    public async listTables(params: IListTablesRequest): Promise<IListTablesResponse> {
        const parsedParams = ListTablesRequestSchema.parse(params);
        let getURL = `/api/v2/templates/gen_tables/${parsedParams.table_type}/list`;

        const response = await this.httpClient.get(getURL, {
            params: parsedParams
        });

        return this.handleResponse(response, ListTablesResponseSchema);
    }

    public async getTable(params: IGetTableRequest): Promise<IGetTableResponse> {
        const parsedParams = GetTableRequestSchema.parse(params);
        let getURL = `/api/v2/templates/gen_tables/${parsedParams.table_type}`;

        const response = await this.httpClient.get(getURL, {
            params: parsedParams
        });

        return this.handleResponse(response, GetTableResponseSchema);
    }

    public async listTableRows(params: IListTableRowsRequest): Promise<IListTableRowsResponse> {
        const parsedParams = ListTableRowsRequestSchema.parse(params);
        let getURL = `/api/v2/templates/gen_tables/${parsedParams.table_type}/rows/list`;

        const response = await this.httpClient.get(getURL, {
            params: parsedParams
        });

        return this.handleResponse(response, ListTableRowsResponseSchema);
    }

    /**
     * Get a specific row from a template table
     * @param params Request parameters
     * @returns Row data
     */
    public async getTableRow(params: {
        template_id: string;
        table_type: string;
        table_id: string;
        row_id: string;
        columns?: string[];
        float_decimals?: number;
        vec_decimals?: number;
    }): Promise<Record<string, any>> {
        const response = await this.httpClient.get(`/api/v2/templates/gen_tables/${params.table_type}/rows`, {
            params: {
                template_id: params.template_id,
                table_id: params.table_id,
                row_id: params.row_id,
                columns: params.columns,
                float_decimals: params.float_decimals,
                vec_decimals: params.vec_decimals
            }
        });

        return this.handleResponse(response);
    }
}
