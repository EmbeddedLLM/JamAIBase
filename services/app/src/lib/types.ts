import type { ComponentType } from 'svelte';
import { z } from 'zod';
import type { genTableDTypes, userRoles } from './constants';
import type { AxiosRequestConfig } from 'axios';

export interface AvailableModel {
	id: string;
	name: string;
	context_length: number;
	languages: string[];
	owned_by: string;
	capabilities: string[];
	object: string;
}

export type SideDockLink = {
	type: 'link';
	title: string;
	href: string;
	openNewTab?: boolean;
	Icon: ComponentType;
	iconClass?: string;
	EndIcon?: ComponentType;
	excludeFromLocal?: boolean;
};

type SideDockCategory = {
	type: 'category';
	title: string;
	excludeFromLocal?: boolean;
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

export interface GenTableCol {
	id: string;
	dtype: (typeof genTableDTypes)[string];
	vlen: number;
	index: boolean;
	gen_config: (CodeGenConfig | LLMGenConfig | EmbedGenConfig) | null;
}

export interface CodeGenConfig {
	object: 'gen_config.code';
	source_column: string;
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
	} | null;
	temperature?: number;
	top_p?: number;
	stop?: string[] | null;
	max_tokens?: number;
	presence_penalty?: number;
	frequency_penalty?: number;
	logit_bias?: object;
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
			name: null;
		};
		index: number;
		finish_reason: 'stop' | string | null;
	}[];
	references: null;
	output_column_name: string;
	row_id: string;
};

//* Non-local
export type PriceRes = {
	plans: {
		[key: string]: {
			stripe_price_id: string;
			flat_amount_decimal: string;
			credit_grant: number;
			max_users: number;
			products: {
				[key: string]: {
					name: string;
					included: {
						unit_amount_decimal: string;
						up_to: number;
					};
					tiers: [
						{
							unit_amount_decimal: string;
							up_to: number | null;
						}
					];
					unit: string;
				};
			};
		};
	};
};

export type Organization = {
	organization_id: string;
	organization_name: string;
	role: (typeof userRoles)[number];
};

export type OrganizationReadRes = {
	id: string;
	creator_user_id: string;
	name: string;
	tier: string;
	active: boolean;
	credit: number;
	credit_grant: number;
	quotas: {
		[key: string]: {
			quota: number;
			usage: number;
		};
	};
	db_usage_gib: number;
	file_usage_gib: number;
	stripe_id: string;
	openmeter_id: string;
	external_keys?: Record<string, string>;
	created_at: string;
	updated_at: string;
	members?: {
		organization_id: string;
		user_id: string;
		role: (typeof userRoles)[number];
		created_at: string;
		updated_at: string;
	}[];
	api_keys?: {
		created_at: string;
		id: string;
		organization_id: string;
	}[];
	projects: {
		name: string;
		organization_id: string;
		updated_at: string;
		created_at: string;
		id: string;
	}[];
	timezone: string;
	currency: string;
	total_spent: number;
};

export type Project = {
	name: string;
	organization_id: string;
	id: string;
	created_at: string;
	updated_at: string;
	organization: Omit<OrganizationReadRes, 'api_keys'>;
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
	id: string;
	user_id: string;
	expiry: string;
	created_at: string;
};

export type UserRead = {
	id: string;
	name: string;
	description: string;
	email: string;
	meta: Record<string, string>;
	created_at: string;
	update_at: string;
	member_of: Organization[];
	pats: PATRead[];
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

export const openmeterUsageItemSchema = z
	.object({
		value: z.number(),
		subject: z.string(),
		windowStart: z.string(),
		windowEnd: z.string()
	})
	.passthrough();

export const openmeterTokenUsageSchema = z.array(
	openmeterUsageItemSchema.merge(
		z.object({
			groupBy: z.object({ model: z.string() })
		})
	)
);
export const openmeterStorageUsageSchema = z.array(
	openmeterUsageItemSchema.merge(
		z.object({
			groupBy: z.object({ type: z.enum(['file', 'db']) })
		})
	)
);
export const openmeterBaseUsageSchema = z.array(openmeterUsageItemSchema);
