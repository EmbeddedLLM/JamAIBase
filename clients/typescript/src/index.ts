import { Auth } from "@/resources/auth";
import { Base, TConfig } from "@/resources/base";
import { Conversations } from "@/resources/conversations";
import { Files } from "@/resources/files";
import { GenTable } from "@/resources/gen_tables";
import { LLM } from "@/resources/llm";
import { Meters } from "@/resources/meters";
import { Models } from "@/resources/models";
import { Organizations } from "@/resources/organizations";
import { Prices } from "@/resources/prices";
import { Projects } from "@/resources/projects";
import { Secrets } from "@/resources/secrets";
import { Tasks } from "@/resources/tasks";
import { Templates } from "@/resources/templates";
import { Users } from "@/resources/users";
import Agent from "agentkeepalive";
import { AxiosResponse } from "axios";

class JamAI extends Base {
    public auth: Auth;
    public users: Users;
    public organizations: Organizations;
    public projects: Projects;
    public models: Models;
    public conversations: Conversations;
    public prices: Prices;
    public meters: Meters;
    public tasks: Tasks;
    public secrets: Secrets;
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
        // Share the parent's httpClient with all resource instances so header updates propagate
        const sharedConfig = { ...config, httpClient: this.httpClient };
        this.auth = new Auth(sharedConfig);
        this.users = new Users(sharedConfig);
        this.organizations = new Organizations(sharedConfig);
        this.projects = new Projects(sharedConfig);
        this.models = new Models(sharedConfig);
        this.conversations = new Conversations(sharedConfig);
        this.prices = new Prices(sharedConfig);
        this.meters = new Meters(sharedConfig);
        this.tasks = new Tasks(sharedConfig);
        this.secrets = new Secrets(sharedConfig);
        this.table = new GenTable(sharedConfig);
        this.llm = new LLM(sharedConfig);
        this.template = new Templates(sharedConfig);
        this.file = new Files(sharedConfig);
    }

    public override setApiKey(token: string) {
        super.setApiKey(token);
    }

    public override setProjId(projectId: string) {
        super.setProjId(projectId);
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
        super.setHttpsagentConfig(payload);
    }

    public override setAuthHeader(header: string) {
        super.setAuthHeader(header);
    }

    public override async health(): Promise<AxiosResponse> {
        return await super.health();
    }
}

// // Re-export types from internal modules for easier access
// export * from "@/resources/base";
// export * from "@/resources/files";
// export * from "@/resources/gen_tables/tables";
// export * from "@/resources/llm/chat";
// export * from "@/resources/templates";

export default JamAI;
