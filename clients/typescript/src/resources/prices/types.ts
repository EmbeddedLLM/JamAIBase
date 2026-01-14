import { PageSchema, PaginationParamsSchema } from "@/resources/shared/types";
import { z } from "zod";

/**
 * Price tier schema
 * https://docs.stripe.com/api/prices/object#price_object-tiers
 */
export const PriceTierSchema = z.object({
    unit_cost: z.number().describe("Per unit price for units relevant to the tier."),
    up_to: z.number().nullable().describe("Up to and including to this quantity will be contained in the tier. `null` means infinite quantity.")
});

export type PriceTier = z.infer<typeof PriceTierSchema>;

/**
 * Product schema
 */
export const ProductSchema = z.object({
    name: z.string().min(1).describe("Product name."),
    included: PriceTierSchema.describe("Free tier. The `unit_cost` of this tier will always be `0.0`."),
    tiers: z.array(PriceTierSchema).describe("Additional tiers so that we may charge a different price for the first usage band versus the next."),
    unit: z.string().min(1).describe("Unit of measurement for reference.")
});

export type Product = z.infer<typeof ProductSchema>;

/**
 * Products schema
 */
export const ProductsSchema = z.object({
    llm_tokens: ProductSchema.describe("LLM token quota to this plan or tier."),
    embedding_tokens: ProductSchema.describe("Embedding token quota to this plan or tier."),
    reranker_searches: ProductSchema.describe("Reranker search quota to this plan or tier."),
    db_storage: ProductSchema.describe("Database storage quota to this plan or tier."),
    file_storage: ProductSchema.describe("File storage quota to this plan or tier."),
    egress: ProductSchema.describe("Egress bandwidth quota to this plan or tier."),
    image_tokens: ProductSchema.describe("Image token quota to this plan or tier.")
});

export type Products = z.infer<typeof ProductsSchema>;

/**
 * Price plan update schema
 */
export const PricePlanUpdateSchema = z.object({
    stripe_price_id_live: z.string().min(1).optional().describe("Stripe price ID (live mode)."),
    stripe_price_id_test: z.string().min(1).optional().describe("Stripe price ID (test mode)."),
    name: z.string().min(1).max(255).optional().describe("Price plan name."),
    flat_cost: z.number().min(0).optional().describe("Base price for the entire tier."),
    credit_grant: z.number().min(0).optional().describe("Credit amount included in USD."),
    max_users: z.number().int().min(1).nullable().optional().describe("Maximum number of users per organization. `null` means no limit."),
    products: ProductsSchema.optional().describe("Mapping of product ID to product."),
    allowed_orgs: z
        .array(z.string())
        .optional()
        .describe("List of IDs of organizations allowed to use this price plan. If empty, all orgs are allowed."),
    meta: z.record(z.any()).optional().describe("Metadata.")
});

export type PricePlanUpdate = z.infer<typeof PricePlanUpdateSchema>;

/**
 * Price plan create schema
 */
export const PricePlanCreateSchema = z
    .object({
        id: z.string().default("").describe("Price plan ID."),
        stripe_price_id_live: z.string().min(1).describe("Stripe price ID (live mode)."),
        stripe_price_id_test: z.string().min(1).describe("Stripe price ID (test mode)."),
        name: z.string().min(1).max(255).describe("Price plan name."),
        flat_cost: z.number().min(0).describe("Base price for the entire tier."),
        credit_grant: z.number().min(0).describe("Credit amount included in USD."),
        max_users: z.number().int().min(1).nullable().describe("Maximum number of users per organization. `null` means no limit."),
        products: ProductsSchema.describe("Mapping of product ID to product."),
        allowed_orgs: z
            .array(z.string())
            .default([])
            .describe("List of IDs of organizations allowed to use this price plan. If empty, all orgs are allowed."),
        meta: z.record(z.any()).default({}).describe("Metadata.")
    })
    .partial({ id: true, allowed_orgs: true, meta: true });

export type PricePlanCreate = z.infer<typeof PricePlanCreateSchema>;

/**
 * Price plan read schema
 */
export const PricePlanReadSchema = PricePlanCreateSchema.extend({
    created_at: z.string().describe("Creation datetime (UTC)."),
    updated_at: z.string().describe("Update datetime (UTC)."),
    is_private: z.boolean().describe("Whether this is a private price plan visible only to select organizations."),
    stripe_price_id: z.string().describe("Stripe Price ID (either live or test based on API key).")
});

export type PricePlanRead = z.infer<typeof PricePlanReadSchema>;

/**
 * Base model price schema
 */
const BaseModelPriceSchema = z.object({
    id: z.string().describe('Unique identifier in the form of "{provider}/{model_id}". Users will specify this to select a model.'),
    name: z.string().describe("Name of the model.")
});

/**
 * LLM model price schema
 */
export const LLMModelPriceSchema = BaseModelPriceSchema.extend({
    llm_input_cost_per_mtoken: z.number().describe("Cost in USD per million input / prompt token."),
    llm_output_cost_per_mtoken: z.number().describe("Cost in USD per million output / completion token.")
});

export type LLMModelPrice = z.infer<typeof LLMModelPriceSchema>;

/**
 * Embedding model price schema
 */
export const EmbeddingModelPriceSchema = BaseModelPriceSchema.extend({
    embedding_cost_per_mtoken: z.number().describe("Cost in USD per million embedding tokens.")
});

export type EmbeddingModelPrice = z.infer<typeof EmbeddingModelPriceSchema>;

/**
 * Reranking model price schema
 */
export const RerankingModelPriceSchema = BaseModelPriceSchema.extend({
    reranking_cost_per_ksearch: z.number().describe("Cost in USD for a thousand (kilo) searches.")
});

export type RerankingModelPrice = z.infer<typeof RerankingModelPriceSchema>;

/**
 * Model price schema
 */
export const ModelPriceSchema = z.object({
    object: z.literal("prices.models").default("prices.models").describe("Type of API response object."),
    llm_models: z.array(LLMModelPriceSchema).default([]),
    embed_models: z.array(EmbeddingModelPriceSchema).default([]),
    rerank_models: z.array(RerankingModelPriceSchema).default([])
});

export type ModelPrice = z.infer<typeof ModelPriceSchema>;

/**
 * List price plans params
 */
export const ListPricePlansParamsSchema = PaginationParamsSchema;

export type ListPricePlansParams = z.infer<typeof ListPricePlansParamsSchema>;

// Page types
export const PagePricePlanReadSchema = PageSchema(PricePlanReadSchema);
export type PagePricePlanRead = z.infer<typeof PagePricePlanReadSchema>;
