import { Base } from "@/resources/base";
import {
    ListProjectInvitesParams,
    ListProjectInvitesParamsSchema,
    ListProjectMembersParams,
    ListProjectMembersParamsSchema,
    ListProjectsParams,
    ListProjectsParamsSchema,
    PageProjectInviteCodeRead,
    PageProjectInviteCodeReadSchema,
    PageProjectMemberRead,
    PageProjectMemberReadSchema,
    PageProjectRead,
    PageProjectReadSchema,
    ProjectCreate,
    ProjectCreateSchema,
    ProjectMemberRead,
    ProjectMemberReadSchema,
    ProjectRead,
    ProjectReadSchema,
    ProjectUpdate,
    ProjectUpdateSchema,
    ProjInviteCodeRead,
    ProjInviteCodeReadSchema,
    ProjInviteCodeRequest,
    ProjInviteCodeRequestSchema
} from "@/resources/projects/types";
import { OkResponse, OkResponseSchema, Role } from "@/resources/shared/types";

export class Projects extends Base {
    /**
     * Create a new project
     * @param body Project data
     * @returns Created project
     */
    public async createProject(body: ProjectCreate): Promise<ProjectRead> {
        const parsedBody = ProjectCreateSchema.parse(body);
        const response = await this.httpClient.post("/api/v2/projects", parsedBody);

        return this.handleResponse(response, ProjectReadSchema);
    }

    /**
     * List projects
     * @param organizationId Organization ID
     * @param params Query parameters
     * @returns Paginated list of projects
     */
    public async listProjects(organizationId: string, params?: ListProjectsParams): Promise<PageProjectRead> {
        const parsedParams = ListProjectsParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/projects/list", {
            params: { organization_id: organizationId, ...parsedParams }
        });

        return this.handleResponse(response, PageProjectReadSchema);
    }

    /**
     * Get project by ID
     * @param projectId Project ID
     * @returns Project information
     */
    public async getProject(projectId: string): Promise<ProjectRead> {
        const response = await this.httpClient.get("/api/v2/projects", {
            params: { project_id: projectId }
        });

        return this.handleResponse(response, ProjectReadSchema);
    }

    /**
     * Update project
     * @param projectId Project ID
     * @param body Update data
     * @returns Updated project
     */
    public async updateProject(projectId: string, body: ProjectUpdate): Promise<ProjectRead> {
        const parsedBody = ProjectUpdateSchema.parse(body);
        const response = await this.httpClient.patch("/api/v2/projects", parsedBody, {
            params: { project_id: projectId }
        });

        return this.handleResponse(response, ProjectReadSchema);
    }

    /**
     * Delete project
     * @param projectId Project ID
     * @param missingOk If true, don't throw error if project doesn't exist
     * @returns Success response
     */
    public async deleteProject(projectId: string, missingOk: boolean = true): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/projects", {
            params: { project_id: projectId }
        });

        if (response.status === 404 && missingOk) {
            return { ok: true };
        }

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Create invite to project
     * @param params Invite parameters
     * @returns Invite code
     */
    public async createInvite(params: ProjInviteCodeRequest): Promise<ProjInviteCodeRead> {
        let parsedParams = ProjInviteCodeRequestSchema.parse(params)
        const response = await this.httpClient.post("/api/v2/projects/invites", null, {
            params: parsedParams
        });

        return this.handleResponse(response, ProjInviteCodeReadSchema);
    }

    /**
     * List project invites
     * @param projectId Project ID
     * @param params Query parameters
     * @returns Paginated list of invites
     */
    public async listInvites(projectId: string, params?: ListProjectInvitesParams): Promise<PageProjectInviteCodeRead> {
        const parsedParams = ListProjectInvitesParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/projects/invites/list", {
            params: { project_id: projectId, ...parsedParams }
        });

        return this.handleResponse(response, PageProjectInviteCodeReadSchema);
    }

    /**
     * Revoke project invite
     * @param inviteId Invite ID
     * @param missingOk If true, don't throw error if invite doesn't exist
     * @returns Success response
     */
    public async revokeInvite(inviteId: string, missingOk: boolean = true): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/projects/invites", {
            params: { invite_id: inviteId }
        });

        if (response.status === 404 && missingOk) {
            return { ok: true };
        }

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Join a project
     * @param userId User ID
     * @param params Join parameters (invite_code OR project_id + role)
     * @returns Member information
     */
    public async joinProject(
        userId: string,
        params: { invite_code?: string; project_id?: string; role?: Role }
    ): Promise<ProjectMemberRead> {
        const response = await this.httpClient.post("/api/v2/projects/members", null, {
            params: { user_id: userId, ...params }
        });

        return this.handleResponse(response, ProjectMemberReadSchema);
    }

    /**
     * List project members
     * @param projectId Project ID
     * @param params Query parameters
     * @returns Paginated list of members
     */
    public async listMembers(projectId: string, params?: ListProjectMembersParams): Promise<PageProjectMemberRead> {
        const parsedParams = ListProjectMembersParamsSchema.parse(params ?? {});
        const response = await this.httpClient.get("/api/v2/projects/members/list", {
            params: { project_id: projectId, ...parsedParams }
        });

        return this.handleResponse(response, PageProjectMemberReadSchema);
    }

    /**
     * Get project member
     * @param userId User ID
     * @param projectId Project ID
     * @returns Member information
     */
    public async getMember(userId: string, projectId: string): Promise<ProjectMemberRead> {
        const response = await this.httpClient.get("/api/v2/projects/members", {
            params: { user_id: userId, project_id: projectId }
        });

        return this.handleResponse(response, ProjectMemberReadSchema);
    }

    /**
     * Update member role
     * @param userId User ID
     * @param projectId Project ID
     * @param role New role
     * @returns Updated member information
     */
    public async updateMemberRole(userId: string, projectId: string, role: Role): Promise<ProjectMemberRead> {
        const response = await this.httpClient.patch("/api/v2/projects/members/role", null, {
            params: { user_id: userId, project_id: projectId, role }
        });

        return this.handleResponse(response, ProjectMemberReadSchema);
    }

    /**
     * Leave project
     * @param userId User ID
     * @param projectId Project ID
     * @returns Success response
     */
    public async leaveProject(userId: string, projectId: string): Promise<OkResponse> {
        const response = await this.httpClient.delete("/api/v2/projects/members", {
            params: { user_id: userId, project_id: projectId }
        });

        return this.handleResponse(response, OkResponseSchema);
    }

    /**
     * Import project from file
     * @param source File path or binary data
     * @param params Import parameters
     * @returns Imported project
     */
    public async importProject(
        source: File | string,
        params: { project_id?: string; organization_id?: string } = {}
    ): Promise<ProjectRead> {
        const formData = new FormData();

        if (source instanceof File) {
            formData.append("file", source);
        } else {
            throw new Error("File path not supported in browser. Please pass a File object.");
        }

        if (params.project_id) formData.append("project_id", params.project_id);
        if (params.organization_id) formData.append("organization_id", params.organization_id);

        const response = await this.httpClient.post("/api/v2/projects/import/parquet", formData, {
            headers: { "Content-Type": "multipart/form-data" }
        });

        return this.handleResponse(response, ProjectReadSchema);
    }

    /**
     * Export project to file
     * @param projectId Project ID
     * @returns Project file as bytes
     */
    public async exportProject(projectId: string): Promise<Uint8Array> {
        const response = await this.httpClient.get("/api/v2/projects/export", {
            params: { project_id: projectId },
            responseType: "arraybuffer"
        });

        return this.handleResponse(response);
    }

    /**
     * Import template into project
     * @param templateId Template ID
     * @param params Import parameters
     * @returns Imported project
     */
    public async importTemplate(
        templateId: string,
        params: { project_id?: string; organization_id?: string } = {}
    ): Promise<ProjectRead> {
        const response = await this.httpClient.post("/api/v2/projects/import/template", null, {
            params: {
                template_id: templateId,
                project_id: params.project_id || "",
                organization_id: params.organization_id || ""
            }
        });

        return this.handleResponse(response, ProjectReadSchema);
    }
}
