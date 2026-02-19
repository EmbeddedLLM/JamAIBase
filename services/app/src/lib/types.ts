import type { AxiosRequestConfig } from 'axios';
import type { Component } from 'svelte';
import { z } from 'zod';
import type { genTableDTypes, MODEL_CAPABILITIES, userRoles } from './constants';

export type AvailableModel = {
	id: string;
	name: string;
	context_length: number;
	languages: string[];
	owned_by: string;
	capabilities: string[];
	object: string;
};

export type ModelConfig = {
	meta: Record<string, unknown>;
	created_at: string;
	updated_at: string;
	id: string;
	type: 'completion' | 'llm' | 'embed' | 'rerank' | 'image_gen';
	name: string;
	owned_by: string | null;
	capabilities: (keyof typeof MODEL_CAPABILITIES)[];
	context_length: number;
	languages: string[];
	max_output_tokens: number | null;
	timeout: number;
	priority: number;
	allowed_orgs: string[];
	blocked_orgs: string[];
	llm_input_cost_per_mtoken: number;
	llm_output_cost_per_mtoken: number;
	image_input_cost_per_mtoken: number;
	image_output_cost_per_mtoken: number;
	embedding_size: number | null;
	embedding_dimensions: number | null;
	embedding_transform_query: string | null;
	embedding_cost_per_mtoken: number;
	reranking_cost_per_ksearch: number;
	is_private: boolean;
	deployments: Omit<ModelDeployment, 'model'>[];
};

export type ModelDeployment = {
	meta: Record<string, unknown>;
	created_at: string;
	updated_at: string;
	id: string;
	name: string;
	routing_id: string;
	api_base: string;
	/**  Standard providers are [<CloudProvider.ANTHROPIC: 'anthropic'>, <CloudProvider.AZURE: 'azure'>, <CloudProvider.AZURE_AI: 'azure_ai'>, <CloudProvider.BEDROCK: 'bedrock'>, <CloudProvider.CEREBRAS: 'cerebras'>, <CloudProvider.COHERE: 'cohere'>, <CloudProvider.DEEPSEEK: 'deepseek'>, <CloudProvider.ELLM: 'ellm'>, <CloudProvider.GEMINI: 'gemini'>, <CloudProvider.GROQ: 'groq'>, <CloudProvider.HYPERBOLIC: 'hyperbolic'>, <CloudProvider.JINA_AI: 'jina_ai'>, <CloudProvider.OPENAI: 'openai'>, <CloudProvider.OPENROUTER: 'openrouter'>, <CloudProvider.SAGEMAKER: 'sagemaker'>, <CloudProvider.SAMBANOVA: 'sambanova'>, <CloudProvider.TOGETHER_AI: 'together_ai'>, <CloudProvider.VERTEX_AI: 'vertex_ai'>, <CloudProvider.VOYAGE: 'voyage'>]. */
	provider: string;
	weight: number;
	cooldown_until: string;
	model_id: string;
	model: any;
};

export type SideDockLink = {
	type: 'link';
	title: string;
	href: string;
	openNewTab?: boolean;
	Icon: Component;
	iconClass?: string;
	EndIcon?: Component;
	exclude?: boolean;
};

type SideDockCategory = {
	type: 'category';
	title: string;
	exclude?: boolean;
};

export type SideDockItem = SideDockLink | SideDockCategory;

export interface Timestamp {
	today: number | null;
	yesterday: number | null;
	two_days: number | null;
	three_days: number | null;
	last_week: number | null;
	last_month: number | null;
	older: number | null;
}

export interface UploadQueue {
	activeFile: UploadQueueItem | null;
	progress: number;
	queue: UploadQueueItem[];
}

export interface UploadQueueItem {
	file: File;
	request: AxiosRequestConfig;
	completeText: string;
	successText: string;
	invalidate?: () => void;
}

// Action Table
export interface GenTable {
	id: string;
	version: string;
	cols: GenTableCol[];
	lock_till: number;
	updated_at: string;
	indexed_at_fts: any;
	indexed_at_vec: any;
	indexed_at_sca: any;
	parent_id: string | null;
	title: string;
}

//? temp name - based off backend typing
export type ChatRequest = {
	id: string;
	model: string;
	messages: {
		role: 'system' | 'user' | 'assistant' | 'function';
		content: string;
		name?: string;
	}[];
	rag_params?: {
		search_query?: string;
		k?: number;
		table_id: string;
		reranking_model: string | null;
		rerank?: boolean;
		concat_reranker_input?: boolean;
	};
	temperature: number;
	top_p: number;
	n: number;
	stream: boolean;
	stop: string[];
	max_tokens: number;
	presence_penalty: number;
	frequency_penalty: number;
	logit_bias: object;
	user: string;
};

type ThreadObj = ChatRequest['messages'][number] & { column_id: string };
type ThreadErr = { error?: number; message: any } & { column_id: string };
export type Thread = ThreadObj | ThreadErr;

export type Conversation = {
	conversation_id: string;
	meta: Record<string, unknown>;
	cols: GenTableCol[];
	parent_id: string | null;
	title: string;
	created_by: string | null;
	updated_at: string;
	num_rows: number;
	version: string;
};

export type ReferenceChunk = {
	text: string;
	title: string;
	context: object;
	page: number | null;
	file_name: string;
	file_path: string;
	document_id: string;
	chunk_id: string;
	metadata: {
		score?: string;
		table_id?: string;
		rrf_score?: string;
		project_id?: string;
	};
};

export type ChatReferences = {
	object: 'chat.references';
	chunks: ReferenceChunk[];
	search_query: string;
	/** @deprecated */
	finish_reason: string | null;
};

export type ChatThread = {
	object: 'chat.thread';
	thread: {
		reasoning_content?: string | null;
		reasoning_time?: number | null;
		row_id: string;
		role: string;
		content:
			| string
			| (
					| {
							type: 'text';
							text: string;
					  }
					| {
							type: 'input_s3';
							uri: string;
							column_name: string;
					  }
			  )[];
		name: string | null;
		user_prompt: string | null;
		references: ChatReferences | null;
	}[];
};

export type ChatThreads = {
	object: 'chat.threads';
	threads: Record<string, ChatThread>;
};

export interface GenTableCol {
	id: string;
	dtype: (typeof genTableDTypes)[string];
	vlen: number;
	index: boolean;
	gen_config:
		| (CodeGenConfig | LLMGenConfig | PythonGenConfig | EmbedGenConfig | ImageGenConfig)
		| null;
}

export interface CodeGenConfig {
	object: 'gen_config.code';
	source_column: string;
}

export interface PythonGenConfig {
	object: 'gen_config.python';
	python_code: string;
}

export interface WebSearchTool {
	type: 'web_search';
}
export interface CodeInterpreterTool {
	type: 'code_interpreter';
	container?: {
		type: 'auto';
	};
}
export interface FunctionTool {
	type: 'function';
	function: {
		name: string;
		description?: string | null;
		parameters?: {
			type: string;
			properties: {
				type: string;
				description: string;
				enum: string[];
			};
		} | null;
		strict?: boolean;
	};
}

export interface LLMGenConfig {
	object: 'gen_config.llm';
	model?: string;
	system_prompt?: string;
	prompt?: string;
	multi_turn?: boolean;
	rag_params?: {
		search_query?: string;
		k?: number;
		table_id: string;
		reranking_model: string | null;
		rerank?: boolean;
		concat_reranker_input?: boolean;
		inline_citations?: boolean;
	} | null;
	tools?: (WebSearchTool | CodeInterpreterTool | FunctionTool)[] | null;
	temperature?: number;
	top_p?: number;
	stop?: string[] | null;
	max_tokens?: number;
	presence_penalty?: number;
	frequency_penalty?: number;
	logit_bias?: object;
	reasoning_effort?: string | null;
}

export interface ImageGenConfig {
	object: 'gen_config.image';
	model?: string;
	prompt?: string;
	// size/quality/style are supported by backend but not exposed in UI
}

export interface EmbedGenConfig {
	object: 'gen_config.embed';
	embedding_model: string;
	source_column: string;
}

export type GenTableRow = {
	ID: string;
	'Updated at': string;
} & {
	[key: string]: {
		value: any;
		reasoning_content?: string;
		reasoning_time?: number;
		references?: ChatReferences;
		error?: { message?: string } | string;
	};
};

export type GenTableStreamEvent = {
	id: string;
	object: string;
	created: number;
	model: string;
	usage: null;
	choices: {
		message: {
			role: 'assistant';
			content: string;
			reasoning_content: string | null;
			refusal: null;
			tool_calls: null;
			function_call: null;
			audio: null;
		};
		delta: {
			role: 'assistant';
			content: null;
			reasoning_content: string | null;
			refusal: null;
			tool_calls: null;
			function_call: null;
		};
		index: number;
		logprobs: null;
		finish_reason: 'stop' | string | null;
	}[];
	references: null;
	output_column_name: string;
	row_id: string;
};

//* Non-local
export type PriceRes = {
	meta: Record<string, unknown>;
	created_at: string;
	updated_at: string;
	id: string;
	name: string;
	stripe_price_id_live: string;
	stripe_price_id_test: string;
	flat_cost: number;
	credit_grant: number;
	max_users: number | null;
	products: {
		llm_tokens: PriceProduct;
		embedding_tokens: PriceProduct;
		reranker_searches: PriceProduct;
		image_tokens: PriceProduct;
		db_storage: PriceProduct;
		file_storage: PriceProduct;
		egress: PriceProduct;
	};
	allowed_orgs: string[];
	is_private: boolean;
	stripe_price_id: string;
};

export type PriceProduct = {
	name: string;
	included: {
		unit_cost: number;
		up_to: number | null;
	};
	tiers: {
		unit_cost: number;
		up_to: number | null;
	}[];
	unit: string;
};

export type VerificationCodeRead = {
	created_at: string;
	updated_at: string;
	meta: Record<string, unknown>;
	name: string;
	role?: (typeof userRoles)[number] | null;
	user_email: string;
	expiry: string;
	organization_id?: string | null;
	project_id?: string | null;
	id: string;
	purpose?: string | null;
	used_at?: string | null;
	revoked_at?: string | null;
};

export type Auth0User = {
	sid: string;
	given_name?: string;
	nickname: string;
	name: string;
	picture: string;
	locale?: string;
	updated_at: string;
	email: string;
	email_verified: boolean;
	sub: string;
};

export type User = {
	meta: Record<string, unknown>;
	created_at: string;
	updated_at: string;
	id: string;
	name: string;
	email: string;
	email_verified: boolean;
	picture_url: string | null;
	refresh_counter: number;
	google_id: string | null;
	google_name: string | null;
	google_username: string | null;
	google_email: string | null;
	google_picture_url: string | null;
	google_updated_at: string | null;
	github_id: string | null;
	github_name: string | null;
	github_username: string | null;
	github_email: string | null;
	github_picture_url: string | null;
	github_updated_at: string | null;
	password_hash: string | null;
	org_memberships: {
		meta: Record<string, unknown>;
		created_at: string;
		updated_at: string;
		user_id: string;
		organization_id: string;
		role: (typeof userRoles)[number];
	}[];
	proj_memberships: {
		meta: Record<string, unknown>;
		created_at: string;
		updated_at: string;
		user_id: string;
		project_id: string;
		role: (typeof userRoles)[number];
	}[];
	organizations: OrganizationReadRes[];
	projects: Project[];
	preferred_name: string;
	preferred_username: string | null;
	preferred_email: string;
	preferred_picture_url: string | null;
};

export type Organization = {
	organization_id: string;
	organization_name: string;
	role: (typeof userRoles)[number];
};

export type OrganizationReadRes = {
	meta: Record<string, unknown>;
	created_at: string;
	updated_at: string;
	id: string;
	name: string;
	currency: string;
	external_keys: Record<string, string>;
	credit: number;
	credit_grant: number;
	created_by: string;
	owner: string;
	stripe_id: string | null;
	price_plan_id: string | null;
	payment_state: string | null;
	last_subscription_payment_at: string | null;
	quota_reset_at: string;
	llm_tokens_quota_mtok: number | null;
	llm_tokens_usage_mtok: number;
	embedding_tokens_quota_mtok: number | null;
	embedding_tokens_usage_mtok: number;
	reranker_quota_ksearch: number | null;
	reranker_usage_ksearch: number;
	db_quota_gib: number | null;
	db_usage_gib: number;
	file_quota_gib: number | null;
	file_usage_gib: number;
	egress_quota_gib: number | null;
	egress_usage_gib: number;
	image_tokens_quota_mtok: number | null;
	image_tokens_usage_mtok: number;
	price_plan: PriceRes | null;
	active: boolean;
	quotas: {
		[key: string]: {
			quota: number;
			usage: number;
		};
	};
};

export type OrgMemberRead = {
	meta: Record<string, unknown>;
	created_at: string;
	updated_at: string;
	user_id: string;
	organization_id: string;
	role: (typeof userRoles)[number];
	user: Omit<User, 'org_memberships' | 'proj_memberships' | 'organizations' | 'projects'>;
	organization: OrganizationReadRes;
};

export type SecretsRead = {
	organization_id: string;
	name: string;
	value: string | null;
	allowed_projects: string[] | null;
	created_at: string;
	updated_at: string;
};

export type Project = {
	meta: Record<string, unknown>;
	created_at: string;
	updated_at: string;
	id: string;
	name: string;
	description: string;
	quotas: Record<string, unknown>;
	tags: string[];
	profile_picture_url: string | null;
	cover_picture_url: string | null;
	created_by: string;
	owner: string;
	organization_id: string;
	organization: Omit<OrganizationReadRes, 'api_keys'>;
};

export type ProjectMemberRead = {
	meta: Record<string, unknown>;
	created_at: string;
	updated_at: string;
	user_id: string;
	project_id: string;
	role: (typeof userRoles)[number];
	user: Omit<
		User,
		| 'org_memberships'
		| 'proj_memberships'
		| 'organizations'
		| 'projects'
		| 'preferred_name'
		| 'preferred_username'
		| 'preferred_email'
		| 'preferred_picture_url'
	>;
	project: Project;
};

export type Template = {
	id: string;
	name: string;
	created_at: string;
	tags: {
		id: string;
	}[];
};

export type API_Key = {
	user_id: string;
	organization_id: string;
	write: boolean;
	id: string;
	created_at: string;
};

export type PATRead = {
	meta: Record<string, unknown>;
	created_at: string;
	updated_at: string;
	id: string;
	name: string;
	expiry: string | null;
	project_id: string | null;
	user_id: string;
};

// Openmeter
export type TUsageData = {
	model: string;
	data: {
		date: string;
		amount: number;
	}[];
};
export type TUsageDataStorage = Omit<TUsageData, 'model'> & {
	type: 'file' | 'db' | '';
};

export const usageItemSchema = z
	.object({
		value: z.number(),
		subject: z.string(),
		window_start: z.string(),
		window_end: z.string()
	})
	.passthrough();

export const tokenUsageSchema = z.array(
	usageItemSchema.merge(
		z.object({
			groupBy: z.object({ model: z.string() })
		})
	)
);
export const storageUsageSchema = z.array(
	usageItemSchema.merge(
		z.object({
			groupBy: z.object({ type: z.enum(['file', 'db']) })
		})
	)
);
export const bandwidthUsageSchema = z.array(
	usageItemSchema.merge(
		z.object({
			groupBy: z.object({ type: z.enum(['egress']) })
		})
	)
);
export const baseUsageSchema = z.array(usageItemSchema);
