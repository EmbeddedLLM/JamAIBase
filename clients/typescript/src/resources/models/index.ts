import { Base } from "@/resources/base";
import {
    DeploymentCreate,
    DeploymentCreateSchema,
    DeploymentRead,
    DeploymentReadSchema,
    DeploymentUpdate,
    DeploymentUpdateSchema,
    ListDeploymentsParams,
    ListDeploymentsParamsSchema,
    ListModelConfigsParams,
    ListModelConfigsParamsSchema,
    ModelConfigCreate,
    ModelConfigCreateSchema,
    ModelConfigRead,
    ModelConfigReadSchema,
    ModelConfigUpdate,
    ModelConfigUpdateSchema,
    PageDeploymentRead,
    PageDeploymentReadSchema,
    PageModelConfigRead,
    PageModelConfigReadSchema
} from "@/resources/models/types";
import { OkResponse, OkResponseSchema } from "@/resources/shared/types";

export class Models extends Base {
    /**
     * Create a model config
     * @param body Model config data
     * @returns Created model config
     */
    public async createModelConfig(body: ModelConfigCreate): Promise<ModelConfigRead> {
        const parsedBody = ModelConfigCreateSchema.parse(body);
        const response = await this.httpClient.post("/api/v2/models/configs", parsedBody);

        return this.handleResponse(response, ModelConfigReadSchema);
    }

    /**
     * List model configs
     * @param params Query parameters
     * @returns Paginated list of model configs
     */
    public async listModelConfigs(params?: ListModelConfigsParams): Promise<PageModelConfigRead> {
        const parsedParams = ListModelConfigsParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/models/configs/list", { params: parsedParams });

        return this.handleResponse(response, PageModelConfigReadSchema);
    }

    /**
     * Get model config by ID
     * @param modelId Model ID
     * @returns Model config information
     */
    public async getModelConfig(modelId: string): Promise<ModelConfigRead> {
        const response = await this.httpClient.get("/api/v2/models/configs", {
            params: { model_id: modelId }
        });

        return this.handleResponse(response, ModelConfigReadSchema);
    }

    /**
     * Update model config
     * @param modelId Model ID
     * @param body Update data
     * @returns Updated model config
     */
    public async updateModelConfig(modelId: string, body: ModelConfigUpdate): Promise<ModelConfigRead> {
        const parsedBody = ModelConfigUpdateSchema.parse(body);
        const response = await this.httpClient.patch("/api/v2/models/configs", parsedBody, {
            params: { model_id: modelId }
        });

        return this.handleResponse(response, ModelConfigReadSchema);
    }

    /**
     * Delete model config
     * @param modelId Model ID
     * @param missingOk If true, don't throw error if model doesn't exist
     * @returns Success response
     */
    public async deleteModelConfig(modelId: string, missingOk: boolean = true): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/models/configs", {
            params: { model_id: modelId }
        });

        if (response.status === 404 && missingOk) {
            return { ok: true };
        }

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Create a deployment
     * @param body Deployment data
     * @param timeout Optional timeout (default: 300s)
     * @returns Created deployment
     */
    public async createDeployment(body: DeploymentCreate, timeout?: number): Promise<DeploymentRead> {
        const parsedBody = DeploymentCreateSchema.parse(body);
        const response = await this.httpClient.post("/api/v2/models/deployments/cloud", parsedBody, {
            timeout: timeout || 300000
        });

        return this.handleResponse(response, DeploymentReadSchema);
    }

    /**
     * List deployments
     * @param params Query parameters
     * @returns Paginated list of deployments
     */
    public async listDeployments(params?: ListDeploymentsParams): Promise<PageDeploymentRead> {
        const parsedParams = ListDeploymentsParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/models/deployments/list", { params: parsedParams });

        return this.handleResponse(response, PageDeploymentReadSchema);
    }

    /**
     * Get deployment by ID
     * @param deploymentId Deployment ID
     * @returns Deployment information
     */
    public async getDeployment(deploymentId: string): Promise<DeploymentRead> {
        const response = await this.httpClient.get("/api/v2/models/deployments", {
            params: { deployment_id: deploymentId }
        });

        return this.handleResponse(response, DeploymentReadSchema);
    }

    /**
     * Update deployment
     * @param deploymentId Deployment ID
     * @param body Update data
     * @returns Updated deployment
     */
    public async updateDeployment(deploymentId: string, body: DeploymentUpdate): Promise<DeploymentRead> {
        const parsedBody = DeploymentUpdateSchema.parse(body);
        const response = await this.httpClient.patch("/api/v2/models/deployments", parsedBody, {
            params: { deployment_id: deploymentId }
        });

        return this.handleResponse(response, DeploymentReadSchema);
    }

    /**
     * Delete deployment
     * @param deploymentId Deployment ID
     * @returns Success response
     */
    public async deleteDeployment(deploymentId: string): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/models/deployments", {
            params: { deployment_id: deploymentId }
        });

        return this.handleResponse(response, OkResponseSchema);
    }
}
