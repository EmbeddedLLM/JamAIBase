import { createHttpAgent, createHttpsAgent, isRunningInBrowser } from "@/helpers/utils";
import { getOSInfoBrwoser } from "@/helpers/utils.browser";
import { getOSInfoNode } from "@/helpers/utils.node";
import Agent from "agentkeepalive";
import axios, { AxiosInstance, AxiosResponse } from "axios";
import axiosRetry from "axios-retry";
import { z, ZodSchema } from "zod";

/**
 * Configuration type for initializing the APIClient.
 */
type BaseConfig = {
    maxRetries?: number;
    httpClient?: AxiosInstance;
    timeout?: number;
    dangerouslyAllowBrowser?: boolean;
};

type ConfigWithBaseURL = BaseConfig & {
    baseURL: string;
    token?: string;
    projectId?: string;
    userId?: string;
};

type ConfigWithoutBaseURL = BaseConfig & {
    baseURL?: string;
    token: string;
    projectId: string;
    userId?: string;
};

export type TConfig = ConfigWithBaseURL | ConfigWithoutBaseURL;

export abstract class Base {
    protected maxRetries: number;
    protected httpClient: AxiosInstance;
    protected timeout: number | undefined;
    private sdkVersion = "0.3";

    /**
     * Creates an instance of APIClient.
     * @param {string} baseURL Base URL for the API requests. Default url is - https://api.jamaibase.com
     * @param {string} token PAT.
     * @param {string} projectId Project ID.
     * @param {number=} [maxRetries=0] Maximum number of retries for failed requests. Defaults value is 0.
     * @param {AxiosInstance} [httpClient] Axios instance for making HTTP requests. If not provided, a default instance will be created.
     * @param {number} [timeout] Timeout (ms) for the requests. Default value is none.
     */
    constructor({ baseURL, token, projectId, userId, maxRetries = 0, httpClient, timeout, dangerouslyAllowBrowser = false }: TConfig) {
        this.maxRetries = maxRetries;
        this.httpClient = httpClient || axios.create({});
        this.timeout = timeout;

        if (!dangerouslyAllowBrowser && isRunningInBrowser()) {
            throw new Error(
                "It looks like you're running in a browser-like environment.\n\nThis is disabled by default, as it risks exposing your secret API credentials to attackers.\nIf you understand the risks and have appropriate mitigations in place,\nyou can set the `dangerouslyAllowBrowser` option to `true`, e.g.,\n\nnew JamAI({ token, dangerouslyAllowBrowser: true });"
            );
        }

        // Setting up the request interceptor
        this.httpClient.interceptors.request.use(
            async (config) => {
                const userAgent = await this.generateUserAgent();
                config.headers["User-Agent"] = userAgent;

                return config;
            },
            (error) => {
                // Handle the request error here
                return Promise.reject(error);
            }
        );

        // Setting up the response interceptor for better error messages
        this.httpClient.interceptors.response.use(
            (response) => response,
            (error) => {
                if (error.response) {
                    // The request was made and the server responded with a status code
                    // that falls out of the range of 2xx
                    const { status, data, config } = error.response;
                    const method = config?.method?.toUpperCase() || "REQUEST";
                    const url = config?.url || "unknown";

                    let errorMessage = `${method} ${url} failed with status ${status}`;

                    // Add response body details if available
                    if (data) {
                        if (typeof data === "string") {
                            errorMessage += `\nResponse: ${data}`;
                        } else if (data.detail) {
                            errorMessage += `\nDetail: ${typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)}`;
                        } else if (data.message) {
                            errorMessage += `\nMessage: ${typeof data.message === "string" ? data.message : JSON.stringify(data.message)}`;
                        } else if (data.error) {
                            errorMessage += `\nError: ${typeof data.error === "string" ? data.error : JSON.stringify(data.error)}`;
                        } else {
                            errorMessage += `\nResponse: ${JSON.stringify(data)}`;
                        }
                    }

                    // Create a new error with the enhanced message
                    const enhancedError = new Error(errorMessage);
                    enhancedError.name = error.name;
                    // Preserve the original error properties
                    Object.assign(enhancedError, {
                        response: error.response,
                        request: error.request,
                        config: error.config,
                        code: error.code,
                        status
                    });

                    return Promise.reject(enhancedError);
                } else if (error.request) {
                    // The request was made but no response was received
                    const enhancedError = new Error(`No response received from server: ${error.message}`);
                    enhancedError.name = error.name;
                    Object.assign(enhancedError, {
                        request: error.request,
                        config: error.config,
                        code: error.code
                    });
                    return Promise.reject(enhancedError);
                } else {
                    // Something happened in setting up the request that triggered an Error
                    return Promise.reject(error);
                }
            }
        );

        // add baseurl to axios instance
        this.httpClient.defaults.baseURL = baseURL || "https://api.jamaibase.com";

        // add apikey and project id to header if provided
        if (token) {
            this.setApiKey(token);
        }

        if (projectId) {
            this.setProjId(projectId);
        }

        if (userId) {
            this.setUserId(userId);
        }

        // add timeout to client
        if (this.timeout) {
            this.httpClient.defaults.timeout = this.timeout;
        }

        // add retry on failed requests
        if (maxRetries > 0) {
            axiosRetry(this.httpClient, {
                retries: this.maxRetries,
                retryDelay: (retryCount) => {
                    console.log("Retry attempt: ", retryCount);
                    return retryCount * 1000;
                },
                retryCondition: (_error) => {
                    return true;
                }
            });
        }

        // add agent pool
        if (!isRunningInBrowser()) {
            this.httpClient.defaults.httpAgent = createHttpAgent();
            this.httpClient.defaults.httpsAgent = createHttpsAgent();
        }
        // (TODO): add agent for browser (default browser)
    }

    /**
     * Options for configuring the HTTP agent.
     * @property {Boolean} [keepAlive=true] - Keep sockets around in a pool to be used by other requests in the future. Default is true.
     * @property {Number} [keepAliveMsecs=1000] - Initial delay for TCP Keep-Alive packets when keepAlive is enabled. Defaults to 1000 milliseconds. Only relevant if keepAlive is true.
     * @property {Number} [freeSocketTimeout=20000] - Timeout for free sockets after inactivity, in milliseconds. Default is 20000 milliseconds. Only relevant if keepAlive is true.
     * @property {Number} [timeout] - Timeout for working sockets after inactivity, in milliseconds. Default is calculated as freeSocketTimeout * 2 if greater than or equal to 8000 milliseconds, otherwise the default is 8000 milliseconds.
     * @property {Number} [maxSockets=Infinity] - Maximum number of sockets to allow per host. Default is Infinity.
     * @property {Number} [maxFreeSockets=10] - Maximum number of free sockets per host to keep open. Only relevant if keepAlive is true. Default is 10.
     * @property {Number} [socketActiveTTL=null] - Sets the time to live for active sockets, even if in use. If not set, sockets are released only when free. Default is null.
     */
    protected setHttpagentConfig(payload: Agent.HttpOptions) {
        this.httpClient.defaults.httpAgent = createHttpAgent(payload);
    }

    /**
     * Options for configuring the HTTP agent.
     * @property {Boolean} [keepAlive=true] - Keep sockets around in a pool to be used by other requests in the future. Default is true.
     * @property {Number} [keepAliveMsecs=1000] - Initial delay for TCP Keep-Alive packets when keepAlive is enabled. Defaults to 1000 milliseconds. Only relevant if keepAlive is true.
     * @property {Number} [freeSocketTimeout=20000] - Timeout for free sockets after inactivity, in milliseconds. Default is 20000 milliseconds. Only relevant if keepAlive is true.
     * @property {Number} [timeout] - Timeout for working sockets after inactivity, in milliseconds. Default is calculated as freeSocketTimeout * 2 if greater than or equal to 8000 milliseconds, otherwise the default is 8000 milliseconds.
     * @property {Number} [maxSockets=Infinity] - Maximum number of sockets to allow per host. Default is Infinity.
     * @property {Number} [maxFreeSockets=10] - Maximum number of free sockets per host to keep open. Only relevant if keepAlive is true. Default is 10.
     * @property {Number} [socketActiveTTL=null] - Sets the time to live for active sockets, even if in use. If not set, sockets are released only when free. Default is null.
     */
    protected setHttpsagentConfig(payload: Agent.HttpsOptions) {
        this.httpClient.defaults.httpsAgent = createHttpsAgent(payload);
    }

    protected async health(): Promise<AxiosResponse> {
        let getURL = `/api/health`;
        return this.httpClient.get(getURL);
    }

    protected async put(url: string, data?: any, config?: any): Promise<AxiosResponse> {
        return this.httpClient.put(url, data, config);
    }

    protected async options(url: string, config?: any): Promise<AxiosResponse> {
        return this.httpClient.options(url, config);
    }

    protected setApiKey(token: string) {
        this.httpClient.defaults.headers.common["Authorization"] = `Bearer ${token}`;
    }
    protected setProjId(projectId: string) {
        this.httpClient.defaults.headers.common["X-PROJECT-ID"] = projectId;
    }
    protected setUserId(projectId: string) {
        this.httpClient.defaults.headers.common["X-USER-ID"] = projectId;
    }

    protected setAuthHeader(header: string) {
        this.httpClient.defaults.headers.common["Authorization"] = header;
    }

    // Helper method to log warnings if present
    protected logWarning(response: AxiosResponse<any, any>): void {
        const warning = response.headers["warning"];
        if (warning) {
            console.warn(warning);
        }
    }

    // Helper method to handle response validation
    protected handleResponse<T extends ZodSchema<any>>(response: AxiosResponse<any, any>, schema?: T): z.infer<T> {
        this.logWarning(response);

        if (response.status !== 200) {
            throw new Error(`Received Error Status: ${response.status}`);
        }
        if (schema) {
            const parsedData = schema.parse(response.data) as z.infer<T>;
            return parsedData;
        } else {
            return response.data;
        }
    }

    // Method to get language and version (TypeScript or JavaScript)
    private getLanguageAndVersion(): { language: string; version: string } {
        try {
            // Check if TypeScript is being used
            const tsVersion = require("typescript").version;
            return { language: "TypeScript", version: tsVersion };
        } catch (error) {
            // Fallback to JavaScript if TypeScript is not detected
            return { language: "JavaScript", version: process.version };
        }
    }

    private async generateUserAgent(): Promise<string> {
        const sdkVersion = this.sdkVersion;
        const { language, version } = this.getLanguageAndVersion();
        let osInfo = "";
        if (isRunningInBrowser()) {
            osInfo = getOSInfoBrwoser();
        } else {
            osInfo = await getOSInfoNode();
        }
        return `SDK/${sdkVersion} (${language}/${version}; ${osInfo})`;
    }
}
