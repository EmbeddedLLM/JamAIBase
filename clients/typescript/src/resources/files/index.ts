import { isRunningInBrowser } from "@/helpers/utils";
import { getFileName, getMimeType, readFile } from "@/helpers/utils.node";
import { Base } from "@/resources/base";
import {
    GetUrlRequestSchema,
    GetUrlResponseSchema,
    IGetUrlRequest,
    IGetUrlResponse,
    IUploadFileRequest,
    IUploadFileResponse,
    UploadFileRequestSchema,
    UploadFileResponseSchema
} from "./types";

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
export class Files extends Base {
    public async uploadFile(params: IUploadFileRequest): Promise<IUploadFileResponse> {
        const apiURL = `/api/v1/files/upload`;

        const parsedParams = UploadFileRequestSchema.parse(params);

        // Create FormData to send as multipart/form-data
        const formData = createFormData();
        if (parsedParams.file) {
            formData.append("file", parsedParams.file, parsedParams.file.name);
        } else if (parsedParams.file_path) {
            if (!isRunningInBrowser()) {
                const mimeType = await getMimeType(parsedParams.file_path!);
                const fileName = await getFileName(parsedParams.file_path!);
                const data = await readFile(parsedParams.file_path!);
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

        const response = await this.httpClient.post<IUploadFileResponse>(apiURL, formData, {
            headers: {
                "Content-Type": "multipart/form-data"
            }
        });

        return this.handleResponse(response, UploadFileResponseSchema);
    }

    public async getRawUrls(params: IGetUrlRequest): Promise<IGetUrlResponse> {
        const parsedParams = GetUrlRequestSchema.parse(params);
        const apiURL = `/api/v1/files/url/raw`;
        const response = await this.httpClient.post(apiURL, {
            uris: parsedParams.uris
        });
        return this.handleResponse(response, GetUrlResponseSchema);
    }

    public async getThumbUrls(params: IGetUrlRequest): Promise<IGetUrlResponse> {
        const parsedParams = GetUrlRequestSchema.parse(params);
        const apiURL = `/api/v1/files/url/thumb`;
        const response = await this.httpClient.post(apiURL, {
            uris: parsedParams.uris
        });
        return this.handleResponse(response, GetUrlResponseSchema);
    }
}
