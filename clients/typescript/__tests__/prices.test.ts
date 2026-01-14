import JamAI from "@/index";
import { beforeAll, describe, expect, it, jest } from "@jest/globals";
import dotenv from "dotenv";
import { v4 as uuidv4 } from "uuid";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Prices", () => {
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

    async function* _getPricePlan() {
        const planId = `test-plan-${uuidv4().substring(0, 8)}`;
        const planName = `Test Plan ${uuidv4().substring(0, 8)}`;

        const pricePlan = await client.prices.createPricePlan({
            id: planId,
            name: planName,
            stripe_price_id_live: `price_live_${uuidv4().substring(0, 8)}`,
            stripe_price_id_test: `price_test_${uuidv4().substring(0, 8)}`,
            flat_cost: 0.0,
            credit_grant: 0.0,
            max_users: null,
            products: {
                llm_tokens: {
                    name: "ELLM tokens",
                    included: { unit_cost: 0, up_to: 0.75 },
                    tiers: [],
                    unit: "Million Tokens"
                },
                embedding_tokens: {
                    name: "Embedding tokens",
                    included: { unit_cost: 0, up_to: 0.75 },
                    tiers: [],
                    unit: "Million Tokens"
                },
                reranker_searches: {
                    name: "Reranker searches",
                    included: { unit_cost: 0, up_to: 0.75 },
                    tiers: [],
                    unit: "Thousand Searches"
                },
                db_storage: {
                    name: "Database storage",
                    included: { unit_cost: 0, up_to: 0.75 },
                    tiers: [],
                    unit: "GiB"
                },
                file_storage: {
                    name: "File storage",
                    included: { unit_cost: 0, up_to: 0.75 },
                    tiers: [],
                    unit: "GiB"
                },
                egress: {
                    name: "Egress bandwidth",
                    included: { unit_cost: 0, up_to: 0.75 },
                    tiers: [],
                    unit: "GiB"
                },
                image_tokens: {
                    name: "Image tokens",
                    included: { unit_cost: 0, up_to: 0.75 },
                    tiers: [],
                    unit: "Million Tokens"
                }
            }
        });

        try {
            yield pricePlan;
        } finally {
            // Cleanup
            if (pricePlan.id) {
                await client.prices.deletePricePlan(pricePlan.id);
            }
        }
    }

    it("mock test because test suite must contain at least 1 test", () => {});

    if (process.env["JAMAI_API_KEY"]) {
        it("create price plan", async () => {
            const planId = `test-plan-${uuidv4().substring(0, 8)}`;
            const planName = `Test Plan ${uuidv4().substring(0, 8)}`;

            const response = await client.prices.createPricePlan({
                id: planId,
                name: planName,
                stripe_price_id_live: `price_live_${uuidv4().substring(0, 8)}`,
                stripe_price_id_test: `price_test_${uuidv4().substring(0, 8)}`,
                flat_cost: 10.0,
                credit_grant: 5.0,
                max_users: 10,
                products: {
                    llm_tokens: {
                        name: "ELLM tokens",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "Million Tokens"
                    },
                    embedding_tokens: {
                        name: "Embedding tokens",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "Million Tokens"
                    },
                    reranker_searches: {
                        name: "Reranker searches",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "Thousand Searches"
                    },
                    db_storage: {
                        name: "Database storage",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "GiB"
                    },
                    file_storage: {
                        name: "File storage",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "GiB"
                    },
                    egress: {
                        name: "Egress bandwidth",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "GiB"
                    },
                    image_tokens: {
                        name: "Image tokens",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "Million Tokens"
                    }
                }
            });

            expect(response).toHaveProperty("id");
            expect(response).toHaveProperty("name");
            expect(response).toHaveProperty("stripe_price_id_live");
            expect(response).toHaveProperty("stripe_price_id_test");
            expect(response).toHaveProperty("flat_cost");
            expect(response).toHaveProperty("credit_grant");
            expect(response).toHaveProperty("max_users");
            expect(response).toHaveProperty("products");
            expect(response).toHaveProperty("is_private");
            expect(response).toHaveProperty("stripe_price_id");
            expect(response).toHaveProperty("created_at");
            expect(response).toHaveProperty("updated_at");
            expect(response.id).toEqual(planId);
            expect(response.name).toEqual(planName);
            expect(response.flat_cost).toBe(10.0);
            expect(response.credit_grant).toBe(5.0);
            expect(response.max_users).toBe(10);

            // Cleanup
            if (response.id !== undefined) {
                await client.prices.deletePricePlan(response.id);
            }
        });

        it("list price plans - without limit and offset", async () => {
            for await (const pricePlan of _getPricePlan()) {
                const response = await client.prices.listPricePlans({});

                expect(response).toHaveProperty("items");
                expect(Array.isArray(response.items)).toBe(true);
                expect(response).toHaveProperty("offset");
                expect(response).toHaveProperty("limit");
                expect(response).toHaveProperty("total");

                const foundPlan = response.items.find((item) => item.id === pricePlan.id);
                expect(foundPlan).toBeDefined();
            }
        });

        it("list price plans - with limit", async () => {
            const limit = 2;
            const response = await client.prices.listPricePlans({ limit });

            expect(response.items.length).toBeLessThanOrEqual(limit);
            expect(response.limit).toEqual(limit);
        });

        it("list price plans - with offset", async () => {
            const offset = 0;
            const response = await client.prices.listPricePlans({ offset });

            expect(response.offset).toEqual(offset);
            expect(Array.isArray(response.items)).toBe(true);
        });

        it("list price plans - with limit and offset", async () => {
            const limit = 3;
            const offset = 0;
            const response = await client.prices.listPricePlans({ limit, offset });

            expect(response.limit).toEqual(limit);
            expect(response.offset).toEqual(offset);
            expect(response.items.length).toBeLessThanOrEqual(limit);
        });

        it("get price plan", async () => {
            for await (const pricePlan of _getPricePlan()) {
                const response = await client.prices.getPricePlan(pricePlan.id!);

                expect(response).toHaveProperty("id");
                expect(response.id).toEqual(pricePlan.id);
                expect(response.name).toEqual(pricePlan.name);
            }
        });

        it("update price plan", async () => {
            for await (const pricePlan of _getPricePlan()) {
                const updatedName = `Updated Plan ${uuidv4().substring(0, 8)}`;
                const updatedFlatCost = 20.0;

                const response = await client.prices.updatePricePlan(pricePlan.id!, {
                    name: updatedName,
                    flat_cost: updatedFlatCost
                });

                expect(response).toHaveProperty("id");
                expect(response.id).toEqual(pricePlan.id);
                expect(response.name).toEqual(updatedName);
                expect(response.flat_cost).toBe(updatedFlatCost);
            }
        });

        it("delete price plan", async () => {
            const planId = `test-plan-${uuidv4().substring(0, 8)}`;
            const planName = `Test Plan ${uuidv4().substring(0, 8)}`;

            const pricePlan = await client.prices.createPricePlan({
                id: planId,
                name: planName,
                stripe_price_id_live: `price_live_${uuidv4().substring(0, 8)}`,
                stripe_price_id_test: `price_test_${uuidv4().substring(0, 8)}`,
                flat_cost: 0.0,
                credit_grant: 0.0,
                max_users: null,
                products: {
                    llm_tokens: {
                        name: "ELLM tokens",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "Million Tokens"
                    },
                    embedding_tokens: {
                        name: "Embedding tokens",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "Million Tokens"
                    },
                    reranker_searches: {
                        name: "Reranker searches",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "Thousand Searches"
                    },
                    db_storage: {
                        name: "Database storage",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "GiB"
                    },
                    file_storage: {
                        name: "File storage",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "GiB"
                    },
                    egress: {
                        name: "Egress bandwidth",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "GiB"
                    },
                    image_tokens: {
                        name: "Image tokens",
                        included: { unit_cost: 0, up_to: 0.75 },
                        tiers: [],
                        unit: "Million Tokens"
                    }
                }
            });

            const deleteResponse = await client.prices.deletePricePlan(pricePlan.id!);

            expect(deleteResponse).toHaveProperty("ok");
            expect(deleteResponse.ok).toBeTruthy();

            // Verify price plan is deleted
            const listResponse = await client.prices.listPricePlans({});
            const foundPlan = listResponse.items.find((item) => item.id === pricePlan.id);
            expect(foundPlan).toBeUndefined();
        });

        it("list model prices", async () => {
            const response = await client.prices.listModelPrices();

            expect(response).toHaveProperty("object");
            expect(response.object).toBe("prices.models");
            expect(response).toHaveProperty("llm_models");
            expect(response).toHaveProperty("embed_models");
            expect(response).toHaveProperty("rerank_models");
            expect(Array.isArray(response.llm_models)).toBe(true);
            expect(Array.isArray(response.embed_models)).toBe(true);
            expect(Array.isArray(response.rerank_models)).toBe(true);
        });
    }
});
