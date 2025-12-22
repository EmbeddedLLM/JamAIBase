import JamAI from "@/index";
import { TableTypes } from "@/resources/gen_tables/tables";
import { v4 as uuidv4 } from "uuid";

export interface TestContext {
    client: JamAI;
    projectId: string;
    organizationId: string;
    userId: string;
    shouldDeleteProject: boolean;
    shouldDeleteOrganization: boolean;
    shouldDeleteUser: boolean;
    modelConfigs?: {
        completionModelId: string;
        embeddingModelId: string;
        completionDeploymentId: string;
        embeddingDeploymentId: string;
    };
}

/**
 * Setup test environment: creates user, organization, project, and initializes client
 * Also cleans up existing tables for gentable tests
 * Optionally creates model configs and deployments
 */
export async function setupTestEnvironment(options?: {
    cleanupTables?: boolean;
    createModels?: boolean;
}): Promise<TestContext> {
    // Default cleanupTables to true if not provided
    const { cleanupTables = true, createModels = false } = options ?? {};
    const myuuid = uuidv4();
    const projectName = `unittest-project-${myuuid}`;
    let userId = `0`;
    let projectId: string;
    let organizationId: string;
    let shouldDeleteProject = false;
    let shouldDeleteOrganization = false;
    let shouldDeleteUser = false;

    // Create a temporary client for setup
    const setupClient = new JamAI({
        baseURL: process.env["BASEURL"]!,
        token: process.env["JAMAI_API_KEY"]!,
        userId: "0"
    });

    if (process.env["JAMAI_API_KEY"]) {
        // Cloud: Check for existing resources with id="0" or create new ones

        // Check for existing user with id="0"
        const users = await setupClient.users.listUsers();
        const existingUser = users.items.find(u => u.id === "0");
        userId = "0"
        

        if (existingUser) {
            shouldDeleteUser = false;
        } else {
            // Create new user with random email and name to avoid clashes
            const user = await setupClient.users.createUser({
                id: userId,
                name: `TS SDK Tester ${myuuid.substring(0, 8)}`,
                email: `tester-${myuuid}@test.local`,
                password: "TempPassword123"
            });
            userId = user.id;
            shouldDeleteUser = true;
        }

        // Check for existing organization with id="0"
        const orgs = await setupClient.organizations.listOrganizations();
        const existingOrg = orgs.items.find(o => o.id === "0");

        if (existingOrg) {
            organizationId = existingOrg.id;
            shouldDeleteOrganization = false;
        } else {
            // Create new organization
            const org = await setupClient.organizations.createOrganization({
                name: `Test Company ${myuuid.substring(0, 8)}`
            });
            organizationId = org.id;
            shouldDeleteOrganization = true;
        }

        // Check for existing project or create new one
        const projects = await setupClient.projects.listProjects(organizationId);

        if (projects.items.length > 0) {
            // Use the first existing project
            projectId = projects.items[0]!.id;
            shouldDeleteProject = false;
        } else {
            // No projects exist, create one
            const project = await setupClient.projects.createProject({
                organization_id: organizationId,
                name: projectName
            });
            projectId = project.id;
            shouldDeleteProject = true;
        }
    } else {
        // OSS: Use organization with ID "0" and find/create project
        organizationId = "0";

        // List existing projects under organization ID "0"
        const projects = await setupClient.projects.listProjects(organizationId);

        if (projects.items.length > 0) {
            // Use the first existing project
            projectId = projects.items[0]!.id;
            shouldDeleteProject = false;
        } else {
            // No projects exist, create one
            const project = await setupClient.projects.createProject({
                organization_id: organizationId,
                name: projectName
            });
            projectId = project.id;
            shouldDeleteProject = true;
        }
    }

    // Create main client with project ID
    const client = new JamAI({
        baseURL: process.env["BASEURL"]!,
        token: process.env["JAMAI_API_KEY"]!,
        projectId: projectId,
        userId: userId
    });

    // Delete all existing tables if requested (for gentable tests)
    if (cleanupTables) {
        const tableTypes: TableTypes[] = ["action", "knowledge", "chat"];
        for (const tableType of tableTypes) {
            const tables = await client.table.listTables({
                table_type: tableType
            });

            for (const table of tables.items) {
                await client.table.deleteTable({
                    table_id: table.id,
                    table_type: tableType
                });
            }
        }
    }

    // Create model configs and deployments if requested
    let modelConfigs: TestContext["modelConfigs"] | undefined;
    if (createModels) {
        const completionModelId = `openai/gpt-4o-mini-test-${uuidv4().substring(0, 8)}`;
        const completionRoutingId = 'gpt-4o-mini'
        const embeddingDimention = 1536
        const embeddingModelId = `openai/text-embedding-test-${uuidv4().substring(0, 8)}`;
        const embeddingRoutingId = "text-embedding-3-small"

        // Create completion model config (similar to GPT_4O_MINI_CONFIG)
        await client.models.createModelConfig({
            id: completionModelId,
            name: `OpenAI GPT-4o mini Test ${uuidv4().substring(0, 8)}`,
            type: "completion",
            capabilities: ["chat", "image", "tool"],
            context_length: 128000
        });

        // Create embedding model config (similar to TEXT_EMBEDDING_3_SMALL_CONFIG)
        await client.models.createModelConfig({
            id: embeddingModelId,
            name: `OpenAI Text Embedding Test ${uuidv4().substring(0, 8)}`,
            type: "embed",
            capabilities: ["embed"],
            context_length: 8192,
            embedding_dimensions: embeddingDimention
        });

        // Create completion deployment (similar to GPT_4O_MINI_DEPLOYMENT)
        const completionDeployment = await client.models.createDeployment({
            model_id: completionModelId,
            name: `OpenAI GPT-4o mini Test ${uuidv4().substring(0, 8)} Deployment`,
            provider: "openai",
            routing_id: completionRoutingId,
            api_base: ""
        });

        // Create embedding deployment (similar to TEXT_EMBEDDING_3_SMALL_DEPLOYMENT)
        const embeddingDeployment = await client.models.createDeployment({
            model_id: embeddingModelId,
            name: `OpenAI Text Embedding Test ${uuidv4().substring(0, 8)} Deployment`,
            provider: "openai",
            routing_id: embeddingRoutingId,
            api_base: ""
        });

        modelConfigs = {
            completionModelId,
            embeddingModelId,
            completionDeploymentId: completionDeployment.id,
            embeddingDeploymentId: embeddingDeployment.id
        };
    }

    const context: TestContext = {
        client,
        projectId,
        organizationId,
        userId,
        shouldDeleteProject,
        shouldDeleteOrganization,
        shouldDeleteUser
    };

    if (modelConfigs) {
        context.modelConfigs = modelConfigs;
    }

    return context;
}

/**
 * Cleanup test environment: deletes project, organization, and user
 * Also cleans up model configs and deployments if they were created
 * Only deletes resources that were manually created (based on shouldDelete flags)
 */
export async function cleanupTestEnvironment(context: TestContext): Promise<void> {
    const {
        projectId,
        organizationId,
        userId,
        shouldDeleteProject,
        shouldDeleteOrganization,
        shouldDeleteUser,
        modelConfigs
    } = context;

    // Create cleanup client
    const cleanupClient = new JamAI({
        baseURL: process.env["BASEURL"]!,
        token: process.env["JAMAI_API_KEY"]!,
        projectId: projectId,
        userId: userId
    });

    // Delete model deployments and configs if they were created
    if (modelConfigs) {
        try {
            // Delete deployments first (they depend on model configs)
            await cleanupClient.models.deleteDeployment(modelConfigs.completionDeploymentId);
            await cleanupClient.models.deleteDeployment(modelConfigs.embeddingDeploymentId);

            // Then delete model configs
            await cleanupClient.models.deleteModelConfig(modelConfigs.completionModelId);
            await cleanupClient.models.deleteModelConfig(modelConfigs.embeddingModelId);
        } catch (error) {
            console.warn("Error cleaning up model configs/deployments:", error);
        }
    }

    // Only delete project if we created it
    if (shouldDeleteProject) {
        await cleanupClient.projects.deleteProject(projectId, true);
    }

    if (process.env["JAMAI_API_KEY"]) {
        // Only delete organization if we created it
        if (shouldDeleteOrganization) {
            await cleanupClient.organizations.deleteOrganization(organizationId, true);
        }

        // Only delete user if we created it
        if (shouldDeleteUser) {
            await cleanupClient.users.deleteUser(true);
        }
    }
}

/**
 * Helper function to check if an error is an API key authentication error
 */
export function isApiKeyError(error: any): boolean {
    const errorMessage = error?.message || error?.toString() || "";
    return (
        errorMessage.includes("Invalid API key") ||
        errorMessage.includes("ExternalAuthError") ||
        (error?.status === 401 && errorMessage.includes("API key"))
    );
}
