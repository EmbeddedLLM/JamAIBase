import { Base } from "@/resources/base";
import { OkResponse, OkResponseSchema } from "@/resources/shared/types";
import {
    ListPricePlansParams,
    ListPricePlansParamsSchema,
    ModelPrice,
    ModelPriceSchema,
    PagePricePlanRead,
    PagePricePlanReadSchema,
    PricePlanCreate,
    PricePlanCreateSchema,
    PricePlanRead,
    PricePlanReadSchema,
    PricePlanUpdate,
    PricePlanUpdateSchema
} from "@/resources/prices/types";

export class Prices extends Base {
    /**
     * Create a price plan
     * @param body Price plan data
     * @returns Created price plan
     */
    public async createPricePlan(body: PricePlanCreate): Promise<PricePlanRead> {
        const parsedBody = PricePlanCreateSchema.parse(body);
        const response = await this.httpClient.post("/api/v2/prices/plans", parsedBody);

        return this.handleResponse(response, PricePlanReadSchema);
    }

    /**
     * List price plans
     * @param params Query parameters
     * @returns Paginated list of price plans
     */
    public async listPricePlans(params?: ListPricePlansParams): Promise<PagePricePlanRead> {
        const parsedParams = ListPricePlansParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/prices/plans/list", { params: parsedParams });

        return this.handleResponse(response, PagePricePlanReadSchema);
    }

    /**
     * Get price plan by ID
     * @param planId Price plan ID
     * @returns Price plan information
     */
    public async getPricePlan(planId: string): Promise<PricePlanRead> {
        const response = await this.httpClient.get("/api/v2/prices/plans", {
            params: { price_plan_id: planId }
        });

        return this.handleResponse(response, PricePlanReadSchema);
    }

    /**
     * Update price plan
     * @param planId Price plan ID
     * @param body Update data
     * @returns Updated price plan
     */
    public async updatePricePlan(planId: string, body: PricePlanUpdate): Promise<PricePlanRead> {
        const parsedBody = PricePlanUpdateSchema.parse(body);
        const response = await this.httpClient.patch("/api/v2/prices/plans", parsedBody, {
            params: { price_plan_id: planId }
        });

        return this.handleResponse(response, PricePlanReadSchema);
    }

    /**
     * Delete price plan
     * @param planId Price plan ID
     * @param missingOk If true, don't throw error if plan doesn't exist
     * @returns Success response
     */
    public async deletePricePlan(planId: string, missingOk: boolean = true): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/prices/plans", {
            params: { price_plan_id: planId }
        });

        if (response.status === 404 && missingOk) {
            return { ok: true };
        }

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * List model prices
     * @returns Model pricing information
     */
    public async listModelPrices(): Promise<ModelPrice> {
        const response = await this.httpClient.get("/api/v2/prices/models/list");

        return this.handleResponse(response, ModelPriceSchema);
    }
}
