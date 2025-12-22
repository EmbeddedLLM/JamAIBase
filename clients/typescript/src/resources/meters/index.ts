import { Base } from "@/resources/base";
import {
    BandwidthMetricsParams,
    BandwidthMetricsParamsSchema,
    BillingMetricsParams,
    BillingMetricsParamsSchema,
    StorageMetricsParams,
    StorageMetricsParamsSchema,
    UsageMetricsParams,
    UsageMetricsParamsSchema,
    UsageResponse,
    UsageResponseSchema
} from "@/resources/meters/types";

export class Meters extends Base {
    /**
     * Get usage metrics
     * @param params Metrics query parameters
     * @returns Usage metrics
     */
    public async getUsageMetrics(params: UsageMetricsParams): Promise<UsageResponse> {
        const parsedParams = UsageMetricsParamsSchema.parse(params);
        const response = await this.httpClient.get("/api/v2/meters/usages", { params: parsedParams });

        return this.handleResponse(response, UsageResponseSchema);
    }

    /**
     * Get billing metrics
     * @param params Metrics query parameters
     * @returns Billing metrics
     */
    public async getBillingMetrics(params: BillingMetricsParams): Promise<UsageResponse> {
        const parsedParams = BillingMetricsParamsSchema.parse(params);
        const response = await this.httpClient.get("/api/v2/meters/billings", { params: parsedParams });

        return this.handleResponse(response, UsageResponseSchema);
    }

    /**
     * Get bandwidth metrics
     * @param params Metrics query parameters
     * @returns Bandwidth metrics
     */
    public async getBandwidthMetrics(params: BandwidthMetricsParams): Promise<UsageResponse> {
        const parsedParams = BandwidthMetricsParamsSchema.parse(params);
        const response = await this.httpClient.get("/api/v2/meters/bandwidths", { params: parsedParams });

        return this.handleResponse(response, UsageResponseSchema);
    }

    /**
     * Get storage metrics
     * @param params Metrics query parameters
     * @returns Storage metrics
     */
    public async getStorageMetrics(params: StorageMetricsParams): Promise<UsageResponse> {
        const parsedParams = StorageMetricsParamsSchema.parse(params);
        const response = await this.httpClient.get("/api/v2/meters/storages", { params: parsedParams });

        return this.handleResponse(response, UsageResponseSchema);
    }
}
