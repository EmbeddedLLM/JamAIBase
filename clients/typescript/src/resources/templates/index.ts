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
    public async listTemplates(params: IListTemplatesRequest = {}): Promise<IListTemplatesResponse> {
        const parsedParams = ListTemplatesRequestSchema.parse(params);

        let getURL = `/api/public/v1/templates`;

        const response = await this.httpClient.get(getURL, {
            params: {
                search_query: encodeURIComponent(parsedParams.search_query)
            }
        });

        return this.handleResponse(response, ListTemplatesResponseSchema);
    }

    public async getTemplate(params: IGetTemplateRequest): Promise<IGetTemplateResponse> {
        const parsedParams = GetTemplateRequestSchema.parse(params);
        let getURL = `/api/public/v1/templates/${parsedParams.template_id}`;

        const response = await this.httpClient.get(getURL);

        return this.handleResponse(response, GetTemplateResponseSchema);
    }

    public async listTables(params: IListTablesRequest): Promise<IListTablesResponse> {
        const parsedParams = ListTablesRequestSchema.parse(params);
        let getURL = `/api/public/v1/templates/${parsedParams.template_id}/gen_tables/${parsedParams.table_type}`;

        const response = await this.httpClient.get(getURL);

        return this.handleResponse(response, ListTablesResponseSchema);
    }

    public async getTable(params: IGetTableRequest): Promise<IGetTableResponse> {
        const parsedParams = GetTableRequestSchema.parse(params);
        let getURL = `/api/public/v1/templates/${parsedParams.template_id}/gen_tables/${parsedParams.table_type}/${parsedParams.table_id}`;

        const response = await this.httpClient.get(getURL);

        return this.handleResponse(response, GetTableResponseSchema);
    }

    public async listTableRows(params: IListTableRowsRequest): Promise<IListTableRowsResponse> {
        const parsedParams = ListTableRowsRequestSchema.parse(params);
        let getURL = `/api/public/v1/templates/${parsedParams.template_id}/gen_tables/${parsedParams.table_type}/${parsedParams.table_id}/rows`;

        delete (parsedParams as any).template_id;
        delete (parsedParams as any).table_type;
        delete (parsedParams as any).table_id;

        const response = await this.httpClient.get(getURL, {
            params: parsedParams
        });

        return this.handleResponse(response, ListTableRowsResponseSchema);
    }
}
