import { createHttpAgent, createHttpsAgent } from "@/utils";
import Agent from "agentkeepalive";
import axios, { AxiosInstance, AxiosResponse } from "axios";
import axiosRetry from "axios-retry";

/**
 * Configuration type for initializing the APIClient.
 */
type BaseConfig = {
    maxRetries?: number;
    httpClient?: AxiosInstance;
    timeout?: number;
};

type ConfigWithBaseURL = BaseConfig & {
    baseURL: string;
    apiKey?: string;
    projectId?: string;
};

type ConfigWithoutBaseURL = BaseConfig & {
    baseURL?: string;
    apiKey: string;
    projectId: string;
};

type Config = ConfigWithBaseURL | ConfigWithoutBaseURL;

export abstract class Base {
    protected maxRetries: number;
    protected httpClient: AxiosInstance;
    protected timeout: number | undefined;

    /**
     * Creates an instance of APIClient.
     * @param {string} baseURL Base URL for the API requests. Default url is - https://app.jamaibase.com
     * @param {string} apiKey apiKey.
     * @param {string} projectId Project ID.
     * @param {number=} [maxRetries=0] Maximum number of retries for failed requests. Defaults value is 0.
     * @param {AxiosInstance} [httpClient] Axios instance for making HTTP requests. If not provided, a default instance will be created.
     * @param {number} [timeout] Timeout (ms) for the requests. Default value is none.
     */
    constructor({ baseURL, apiKey, projectId, maxRetries = 0, httpClient, timeout }: Config) {
        this.maxRetries = maxRetries;
        this.httpClient = httpClient || axios.create({});
        this.timeout = timeout;

        // add baseurl to axios instance
        this.httpClient.defaults.baseURL = baseURL || "https://app.jamaibase.com";

        // add apikey and project id to header if provided
        if (apiKey && projectId) {
            this.setApiKeyProjId(apiKey, projectId);
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
        this.httpClient.defaults.httpAgent = createHttpAgent();
        this.httpClient.defaults.httpsAgent = createHttpsAgent();
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
    public setHttpagentConfig(payload: Agent.HttpOptions) {
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
    public setHttpsagentConfig(payload: Agent.HttpsOptions) {
        this.httpClient.defaults.httpsAgent = createHttpsAgent(payload);
    }

    public async getHealth(): Promise<AxiosResponse> {
        let getURL = `/health`;
        return this.httpClient.get(getURL);
    }
    public setApiKeyProjId(apiKey: string, projectId: string) {
        this.httpClient.defaults.headers.common["Authorization"] = `Bearer ${apiKey}`;
        this.httpClient.defaults.headers.common["X-PROJECT-ID"] = projectId;
    }

    public setAuthHeader(header: string) {
        this.httpClient.defaults.headers.common["Authorization"] = header;
    }
}
