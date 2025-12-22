import { Base } from "@/resources/base";
import {
    PasswordChangeRequest,
    PasswordChangeRequestSchema,
    PasswordLoginRequest,
    PasswordLoginRequestSchema,
    UserCreate,
    UserCreateSchema,
    UserRead,
    UserReadSchema
} from "@/resources/auth/types";

export class Auth extends Base {
    /**
     * Register a new user with password
     * @param body User registration data
     * @returns User information
     */
    public async registerPassword(body: UserCreate): Promise<UserRead> {
        const parsedBody = UserCreateSchema.parse(body);
        const response = await this.httpClient.post("/api/v2/auth/register/password", parsedBody);

        return this.handleResponse(response, UserReadSchema);
    }

    /**
     * Login with email and password
     * @param body Login credentials
     * @returns User information
     */
    public async loginPassword(body: PasswordLoginRequest): Promise<UserRead> {
        const parsedBody = PasswordLoginRequestSchema.parse(body);
        const response = await this.httpClient.post("/api/v2/auth/login/password", parsedBody);

        return this.handleResponse(response, UserReadSchema);
    }

    /**
     * Change user password
     * @param body Password change request
     * @returns User information
     */
    public async changePassword(body: PasswordChangeRequest): Promise<UserRead> {
        const parsedBody = PasswordChangeRequestSchema.parse(body);
        const response = await this.httpClient.patch("/api/v2/auth/login/password", parsedBody);

        return this.handleResponse(response, UserReadSchema);
    }
}
