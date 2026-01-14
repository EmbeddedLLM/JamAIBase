import { Base } from "@/resources/base";
import { serializeParams } from "@/helpers/utils";
import {
    ListInvitesParams,
    ListInvitesParamsSchema,
    ListMembersParams,
    ListMembersParamsSchema,
    ListOrganizationsParams,
    ListOrganizationsParamsSchema,
    ModelCatalogueParams,
    ModelCatalogueParamsSchema,
    OrgInviteCodeRead,
    OrgInviteCodeReadSchema,
    OrgInviteCodeRequest,
    OrgInviteCodeRequestSchema,
    OrgMemberRead,
    OrgMemberReadSchema,
    OrganizationCreate,
    OrganizationCreateSchema,
    OrganizationRead,
    OrganizationReadSchema,
    OrganizationUpdate,
    OrganizationUpdateSchema,
    PageInviteCodeRead,
    PageInviteCodeReadSchema,
    PageModelConfigRead,
    PageModelConfigReadSchema,
    PageOrgMemberRead,
    PageOrgMemberReadSchema,
    PageOrganizationRead,
    PageOrganizationReadSchema,
    StripePaymentInfo,
    StripePaymentInfoSchema
} from "@/resources/organizations/types";
import { OkResponse, OkResponseSchema, Role } from "@/resources/shared/types";

export class Organizations extends Base {
    /**
     * Create a new organization
     * @param body Organization data
     * @returns Created organization
     */
    public async createOrganization(body: OrganizationCreate): Promise<OrganizationRead> {
        const parsedBody = OrganizationCreateSchema.parse(body);
        const response = await this.httpClient.post("/api/v2/organizations", parsedBody);

        return this.handleResponse(response, OrganizationReadSchema);
    }

    /**
     * List organizations
     * @param params Query parameters
     * @returns Paginated list of organizations
     */
    public async listOrganizations(params?: ListOrganizationsParams): Promise<PageOrganizationRead> {
        const parsedParams = ListOrganizationsParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/organizations/list", { params: parsedParams });

        return this.handleResponse(response, PageOrganizationReadSchema);
    }

    /**
     * Get organization by ID
     * @param organizationId Organization ID
     * @returns Organization information
     */
    public async getOrganization(organizationId: string): Promise<OrganizationRead> {
        const response = await this.httpClient.get("/api/v2/organizations", {
            params: { organization_id: organizationId }
        });

        return this.handleResponse(response, OrganizationReadSchema);
    }

    /**
     * Update organization
     * @param organizationId Organization ID
     * @param body Update data
     * @returns Updated organization
     */
    public async updateOrganization(organizationId: string, body: OrganizationUpdate): Promise<OrganizationRead> {
        const parsedBody = OrganizationUpdateSchema.parse(body);
        const response = await this.httpClient.patch("/api/v2/organizations", parsedBody, {
            params: { organization_id: organizationId }
        });

        return this.handleResponse(response, OrganizationReadSchema);
    }

    /**
     * Delete organization
     * @param organizationId Organization ID
     * @param missingOk If true, don't throw error if organization doesn't exist
     * @returns Success response
     */
    public async deleteOrganization(organizationId: string, missingOk: boolean = true): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/organizations", {
            params: { organization_id: organizationId }
        });

        if (response.status === 404 && missingOk) {
            return { ok: true };
        }

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Join an organization
     * @param userId User ID
     * @param params Join parameters (invite_code OR organization_id + role)
     * @returns Member information
     */
    public async joinOrganization(
        userId: string,
        params: { invite_code?: string; organization_id?: string; role?: Role }
    ): Promise<OrgMemberRead> {
        const response = await this.httpClient.post("/api/v2/organizations/members", null, {
            params: { user_id: userId, ...params }
        });

        return this.handleResponse(response, OrgMemberReadSchema);
    }

    /**
     * List organization members
     * @param organizationId Organization ID
     * @param params Query parameters
     * @returns Paginated list of members
     */
    public async listMembers(organizationId: string, params?: ListMembersParams): Promise<PageOrgMemberRead> {
        const parsedParams = ListMembersParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/organizations/members/list", {
            params: { organization_id: organizationId, ...parsedParams }
        });

        return this.handleResponse(response, PageOrgMemberReadSchema);
    }

    /**
     * Get organization member
     * @param userId User ID
     * @param organizationId Organization ID
     * @returns Member information
     */
    public async getMember(userId: string, organizationId: string): Promise<OrgMemberRead> {
        const response = await this.httpClient.get("/api/v2/organizations/members", {
            params: { user_id: userId, organization_id: organizationId }
        });

        return this.handleResponse(response, OrgMemberReadSchema);
    }

    /**
     * Update member role
     * @param userId User ID
     * @param organizationId Organization ID
     * @param role New role
     * @returns Updated member information
     */
    public async updateMemberRole(userId: string, organizationId: string, role: Role): Promise<OrgMemberRead> {
        const response = await this.httpClient.patch("/api/v2/organizations/members/role", null, {
            params: { user_id: userId, organization_id: organizationId, role }
        });

        return this.handleResponse(response, OrgMemberReadSchema);
    }

    /**
     * Leave organization
     * @param userId User ID
     * @param organizationId Organization ID
     * @returns Success response
     */
    public async leaveOrganization(userId: string, organizationId: string): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/organizations/members", {
            params: { user_id: userId, organization_id: organizationId }
        });

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Get model catalogue for organization
     * @param organizationId Organization ID
     * @param params Query parameters
     * @returns Paginated list of available models
     */
    public async modelCatalogue(organizationId: string, params?: ModelCatalogueParams): Promise<PageModelConfigRead> {
        const parsedParams = ModelCatalogueParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/organizations/models/catalogue", {
            params: { organization_id: organizationId, ...parsedParams }
        });

        return this.handleResponse(response, PageModelConfigReadSchema);
    }

    /**
     * Create invite to organization
     * @param params Invite parameters
     * @returns Invite code
     */
    public async createInvite(params: OrgInviteCodeRequest): Promise<OrgInviteCodeRead> {
        let parsedParams = OrgInviteCodeRequestSchema.parse(params)
        const response = await this.httpClient.post("/api/v2/organizations/invites", null, {
            params: parsedParams
        });

        return this.handleResponse(response, OrgInviteCodeReadSchema);
    }

    /**
     * List organization invites
     * @param organizationId Organization ID
     * @param params Query parameters
     * @returns Paginated list of invites
     */
    public async listInvites(organizationId: string, params?: ListInvitesParams): Promise<PageInviteCodeRead> {
        const parsedParams = ListInvitesParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/organizations/invites/list", {
            params: { organization_id: organizationId, ...parsedParams }
        });

        return this.handleResponse(response, PageInviteCodeReadSchema);
    }

    /**
     * Revoke organization invite
     * @param inviteId Invite ID
     * @param missingOk If true, don't throw error if invite doesn't exist
     * @returns Success response
     */
    public async revokeInvite(inviteId: string, missingOk: boolean = true): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/organizations/invites", {
            params: { invite_id: inviteId }
        });

        if (response.status === 404 && missingOk) {
            return { ok: true };
        }

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Subscribe to a price plan
     * @param organizationId Organization ID
     * @param pricePlanId Price plan ID
     * @returns Stripe payment info
     */
    public async subscribePlan(organizationId: string, pricePlanId: string): Promise<StripePaymentInfo> {
        const response = await this.httpClient.patch("/api/v2/organizations/plan", null, {
            params: { organization_id: organizationId, price_plan_id: pricePlanId }
        });

        return this.handleResponse(response, StripePaymentInfoSchema);
    }

    /**
     * Refresh organization quota
     * @param organizationId Organization ID
     * @returns Updated organization
     */
    public async refreshQuota(organizationId: string): Promise<OrganizationRead> {
        const response = await this.httpClient.post("/api/v2/organizations/plan/refresh", null, {
            params: { organization_id: organizationId }
        });

        return this.handleResponse(response, OrganizationReadSchema);
    }

    /**
     * Purchase credits
     * @param organizationId Organization ID
     * @param amount Credit amount
     * @param params Additional parameters
     * @returns Stripe payment info
     */
    public async purchaseCredits(
        organizationId: string,
        amount: number,
        params: { confirm?: boolean; off_session?: boolean } = {}
    ): Promise<StripePaymentInfo> {
        const response = await this.httpClient.post("/api/v2/organizations/credits", null, {
            params: {
                organization_id: organizationId,
                amount,
                confirm: false,
                off_session: false,
                ...params
            }
        });

        return this.handleResponse(response, StripePaymentInfoSchema);
    }

    /**
     * Set credit grant
     * @param organizationId Organization ID
     * @param amount Credit grant amount
     * @returns Success response
     */
    public async setCreditGrant(organizationId: string, amount: number): Promise<OkResponse> {
        const response = await this.put("/api/v2/organizations/credit_grant", null, {
            params: { organization_id: organizationId, amount }
        });

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Add credit grant
     * @param organizationId Organization ID
     * @param amount Credit grant amount to add
     * @returns Success response
     */
    public async addCreditGrant(organizationId: string, amount: number): Promise<OkResponse> {
        const response = await this.httpClient.patch("/api/v2/organizations/credit_grant", null, {
            params: { organization_id: organizationId, amount }
        });

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Get organization metrics
     * @param params Metrics query parameters
     * @returns Usage metrics
     */
    public async getOrganizationMetrics(params: {
        metricId: string;
        from: string;
        orgId: string;
        windowSize?: string;
        projIds?: string[];
        to?: string;
        groupBy?: string[];
        dataSource?: "clickhouse" | "victoriametrics";
    }): Promise<any> {
        const response = await this.httpClient.get("/api/v2/organizations/meters/query", {
            params,
            paramsSerializer: serializeParams
        });

        return this.handleResponse(response);
    }
}
