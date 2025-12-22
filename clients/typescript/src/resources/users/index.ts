import { Base } from "@/resources/base";
import { UserCreate, UserCreateSchema, UserRead, UserReadSchema } from "@/resources/auth/types";
import { OkResponse, OkResponseSchema } from "@/resources/shared/types";
import {
    ListPatsParams,
    ListPatsParamsSchema,
    ListUsersParams,
    ListUsersParamsSchema,
    ListVerificationCodesParams,
    ListVerificationCodesParamsSchema,
    PageProjectKeyRead,
    PageProjectKeyReadSchema,
    PageUserRead,
    PageUserReadSchema,
    PageVerificationCodeRead,
    PageVerificationCodeReadSchema,
    ProjectKeyCreate,
    ProjectKeyCreateSchema,
    ProjectKeyRead,
    ProjectKeyReadSchema,
    ProjectKeyUpdate,
    ProjectKeyUpdateSchema,
    UserUpdate,
    UserUpdateSchema,
    VerificationCodeRead,
    VerificationCodeReadSchema
} from "@/resources/users/types";

export class Users extends Base {
    /**
     * Create a new user
     * @param body User data
     * @returns Created user
     */
    public async createUser(body: UserCreate): Promise<UserRead> {
        const parsedBody = UserCreateSchema.parse(body);
        const response = await this.httpClient.post("/api/v2/users", parsedBody);

        return this.handleResponse(response, UserReadSchema);
    }

    /**
     * List users with pagination
     * @param params Query parameters
     * @returns Paginated list of users
     */
    public async listUsers(params?: ListUsersParams): Promise<PageUserRead> {
        const parsedParams = ListUsersParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/users/list", { params: parsedParams });

        return this.handleResponse(response, PageUserReadSchema);
    }

    /**
     * Get user by ID
     * @param userId User ID (optional, defaults to current user)
     * @returns User information
     */
    public async getUser(userId?: string): Promise<UserRead> {
        const response = await this.httpClient.get("/api/v2/users", {
            params: userId ? { user_id: userId } : undefined
        });

        return this.handleResponse(response, UserReadSchema);
    }

    /**
     * Update user information
     * @param body User update data
     * @returns Updated user
     */
    public async updateUser(body: UserUpdate): Promise<UserRead> {
        const parsedBody = UserUpdateSchema.parse(body);
        const response = await this.httpClient.patch("/api/v2/users", parsedBody);

        return this.handleResponse(response, UserReadSchema);
    }

    /**
     * Delete user
     * @param missingOk If true, don't throw error if user doesn't exist
     * @returns Success response
     */
    public async deleteUser(missingOk: boolean = true): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/users");

        if (response.status === 404 && missingOk) {
            return { ok: true };
        }

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Create a Personal Access Token (PAT)
     * @param body PAT creation data
     * @returns Created PAT with key
     */
    public async createPat(body: ProjectKeyCreate): Promise<ProjectKeyRead> {
        const parsedBody = ProjectKeyCreateSchema.parse(body);
        const response = await this.httpClient.post("/api/v2/pats", parsedBody);

        return this.handleResponse(response, ProjectKeyReadSchema);
    }

    /**
     * List Personal Access Tokens
     * @param params Query parameters
     * @returns Paginated list of PATs
     */
    public async listPats(params?: ListPatsParams): Promise<PageProjectKeyRead> {
        const parsedParams = ListPatsParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/pats/list", { params: parsedParams });

        return this.handleResponse(response, PageProjectKeyReadSchema);
    }

    /**
     * Update a Personal Access Token
     * @param patId PAT ID
     * @param body Update data
     * @returns Updated PAT
     */
    public async updatePat(patId: string, body: ProjectKeyUpdate): Promise<ProjectKeyRead> {
        const parsedBody = ProjectKeyUpdateSchema.parse(body);
        const response = await this.httpClient.patch("/api/v2/pats", parsedBody, {
            params: { pat_id: patId }
        });

        return this.handleResponse(response, ProjectKeyReadSchema);
    }

    /**
     * Delete a Personal Access Token
     * @param patId PAT ID
     * @param missingOk If true, don't throw error if PAT doesn't exist
     * @returns Success response
     */
    public async deletePat(patId: string, missingOk: boolean = true): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/pats", {
            params: { pat_id: patId }
        });

        if (response.status === 404 && missingOk) {
            return { ok: true };
        }

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Create email verification code
     * @param validDays Number of days the code is valid
     * @returns Verification code
     */
    public async createEmailVerificationCode(validDays: number = 7): Promise<VerificationCodeRead> {
        const response = await this.httpClient.post("/api/v2/users/verify/email/code", null, {
            params: { valid_days: validDays }
        });

        return this.handleResponse(response, VerificationCodeReadSchema);
    }

    /**
     * List email verification codes
     * @param params Query parameters
     * @returns Paginated list of verification codes
     */
    public async listEmailVerificationCodes(params?: ListVerificationCodesParams): Promise<PageVerificationCodeRead> {
        const parsedParams = ListVerificationCodesParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/users/verify/email/code/list", { params: parsedParams });

        return this.handleResponse(response, PageVerificationCodeReadSchema);
    }

    /**
     * Get email verification code
     * @param code Verification code
     * @returns Verification code details
     */
    public async getEmailVerificationCode(code: string): Promise<VerificationCodeRead> {
        const response = await this.httpClient.get("/api/v2/users/verify/email/code", {
            params: { verification_code: code }
        });

        return this.handleResponse(response, VerificationCodeReadSchema);
    }

    /**
     * Revoke email verification code
     * @param code Verification code
     * @param missingOk If true, don't throw error if code doesn't exist
     * @returns Success response
     */
    public async revokeEmailVerificationCode(code: string, missingOk: boolean = true): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/users/verify/email/code", {
            params: { verification_code: code }
        });

        if (response.status === 404 && missingOk) {
            return { ok: true };
        }

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Verify email with verification code
     * @param code Verification code
     * @returns Success response
     */
    public async verifyEmail(code: string): Promise<OkResponse> {
        const response = await this.httpClient.post("/api/v2/users/verify/email", null, {
            params: { verification_code: code }
        });

        return this.handleResponse(response, OkResponseSchema);
    }
}
