import { Base, TConfig } from "@/resources/base";
import { Files } from "@/resources/files";
import { GenTable } from "@/resources/gen_tables";
import { LLM } from "@/resources/llm";
import { Templates } from "@/resources/templates";
import Agent from "agentkeepalive";
import { AxiosResponse } from "axios";

class JamAI extends Base {
    public table: GenTable;
    public llm: LLM;
    public template: Templates;
    public file: Files;

    /**
     * Creates an instance of APIClient.
     * @param {string} baseURL Base URL for the API requests. Default url is - https://api.jamaibase.com
     * @param {string} token PAT.
     * @param {string} projectId Project ID.
     * @param {number=} [maxRetries=0] Maximum number of retries for failed requests. Defaults value is 0.
     * @param {AxiosInstance} [httpClient] Axios instance for making HTTP requests. If not provided, a default instance will be created.
     * @param {number} [timeout] Timeout (ms) for the requests. Default value is none.
     */
    constructor(config: TConfig) {
        super(config);
        this.table = new GenTable(config);
        this.llm = new LLM(config);
        this.template = new Templates(config);
        this.file = new Files(config);
    }

    public override setApiKey(token: string){
        super.setApiKey(token)
    }

    public override setProjId(projectId: string){
        super.setProjId(projectId)
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
    public override setHttpagentConfig(payload: Agent.HttpOptions) {
        super.setHttpagentConfig(payload);
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
    public override setHttpsagentConfig(payload: Agent.HttpsOptions) {
        super.setHttpsagentConfig(payload)
    }

    public override setAuthHeader(header: string) {
        super.setAuthHeader(header)
    }

    public override async health(): Promise<AxiosResponse> {
        return await super.health()
    }
}

// // Re-export types from internal modules for easier access
// export * from "@/resources/base";
// export * from "@/resources/files";
// export * from "@/resources/gen_tables/tables";
// export * from "@/resources/llm/chat";
// export * from "@/resources/templates";

export default JamAI; 
