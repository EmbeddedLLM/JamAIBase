import JamAI from "@/index";
import { beforeAll, describe, expect, it, jest } from "@jest/globals";
import dotenv from "dotenv";
import { v4 as uuidv4 } from "uuid";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Auth", () => {
    let client: JamAI;
    let testContext: TestContext;
    jest.setTimeout(30000);
    jest.retryTimes(1, {
        logErrorsBeforeRetry: true
    });

    beforeAll(async () => {
        testContext = await setupTestEnvironment();
        client = testContext.client;
    });

    afterAll(async function () {
        await cleanupTestEnvironment(testContext);
    });

    async function* _getUser() {
        const uniqueId = uuidv4();
        const testUser = {
            name: `Test User ${uniqueId}`,
            email: `test-${uniqueId}@example.com`,
            password: "TestPassword123!"
        };

        const response = await client.auth.registerPassword(testUser);

        try {
            yield {
                ...response,
                password: testUser.password
            };
        } finally {
            const deleteClient = new JamAI({
                baseURL: process.env["BASEURL"]!,
                token: process.env["JAMAI_API_KEY"]!,
                userId: response.id
            });
            await deleteClient.users.deleteUser();
        }
    }

    it("register user with password", async () => {
        for await (const user of _getUser()) {
            expect(user).toHaveProperty("id");
            expect(user).toHaveProperty("name");
            expect(user).toHaveProperty("email");
            expect(user).toHaveProperty("created_at");
            expect(user).toHaveProperty("updated_at");
        }
    });

    it("login user with password", async () => {
        for await (const user of _getUser()) {
            const loginResponse = await client.auth.loginPassword({
                email: user.email,
                password: user.password
            });

            expect(loginResponse).toHaveProperty("id");
            expect(loginResponse).toHaveProperty("email");
            expect(loginResponse.email).toEqual(user.email);
        }
    });

    it("change user password", async () => {
        for await (const user of _getUser()) {
            const userClient = new JamAI({
                baseURL: process.env["BASEURL"]!,
                token: process.env["JAMAI_API_KEY"]!,
                userId: user.id
            });

            const newPassword = "NewPassword456!";

            // Change the password
            const changeResponse = await userClient.auth.changePassword({
                email: user.email,
                password: user.password,
                new_password: newPassword
            });

            expect(changeResponse).toHaveProperty("id");
            expect(changeResponse).toHaveProperty("email");
            expect(changeResponse.email).toEqual(user.email);

            // Try to login with new password
            const loginResponse = await userClient.auth.loginPassword({
                email: user.email,
                password: newPassword
            });

            expect(loginResponse).toHaveProperty("id");
            expect(loginResponse.email).toEqual(user.email);
        }
    });

    it("fail to login with incorrect password", async () => {
        for await (const user of _getUser()) {
            // Try to login with wrong password
            await expect(
                client.auth.loginPassword({
                    email: user.email,
                    password: "WrongPassword123!"
                })
            ).rejects.toThrow();
        }
    });
});
