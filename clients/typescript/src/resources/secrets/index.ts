import { Base } from "@/resources/base";
import { OkResponse, OkResponseSchema } from "@/resources/shared/types";
import {
    ListSecretsParams,
    ListSecretsParamsSchema,
    PageSecretRead,
    PageSecretReadSchema,
    SecretCreate,
    SecretCreateSchema,
    SecretRead,
    SecretReadSchema,
    SecretUpdate,
    SecretUpdateSchema
} from "@/resources/secrets/types";

export class Secrets extends Base {
    /**
     * Create a secret
     * @param body Secret data
     * @param organizationId Organization ID
     * @returns Created secret
     */
    public async createSecret(body: SecretCreate, organizationId: string): Promise<SecretRead> {
        const parsedBody = SecretCreateSchema.parse(body);
        const response = await this.httpClient.post("/api/v2/secrets", parsedBody, {
            params: { organization_id: organizationId }
        });

        return this.handleResponse(response, SecretReadSchema);
    }

    /**
     * List secrets
     * @param organizationId Organization ID
     * @param params Query parameters
     * @returns Paginated list of secrets
     */
    public async listSecrets(organizationId: string, params?: ListSecretsParams): Promise<PageSecretRead> {
        const parsedParams = ListSecretsParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/secrets/list", {
            params: { organization_id: organizationId, ...parsedParams }
        });

        return this.handleResponse(response, PageSecretReadSchema);
    }

    /**
     * Get secret by name
     * @param organizationId Organization ID
     * @param name Secret name
     * @returns Secret information (value is masked)
     */
    public async getSecret(organizationId: string, name: string): Promise<SecretRead> {
        const response = await this.httpClient.get("/api/v2/secrets", {
            params: { organization_id: organizationId, name }
        });

        return this.handleResponse(response, SecretReadSchema);
    }

    /**
     * Update secret
     * @param organizationId Organization ID
     * @param name Secret name
     * @param body Update data
     * @returns Updated secret (value is unmasked)
     */
    public async updateSecret(organizationId: string, name: string, body: SecretUpdate): Promise<SecretRead> {
        const parsedBody = SecretUpdateSchema.parse(body);
        const response = await this.httpClient.patch("/api/v2/secrets", parsedBody, {
            params: { organization_id: organizationId, name }
        });

        return this.handleResponse(response, SecretReadSchema);
    }

    /**
     * Delete secret
     * @param organizationId Organization ID
     * @param name Secret name
     * @param missingOk If true, don't throw error if secret doesn't exist
     * @returns Success response
     */
    public async deleteSecret(organizationId: string, name: string, missingOk: boolean = true): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/secrets", {
            params: { organization_id: organizationId, name }
        });

        if (response.status === 404 && missingOk) {
            return { ok: true };
        }

        return this.handleResponse(response, OkResponseSchema);
    }
}
