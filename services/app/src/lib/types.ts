import { z } from 'zod';
import type { actionTableDTypes, userRoles } from './constants';

export interface AvailableModel {
	id: string;
	contextLength: number;
	languages: string[];
	owned_by: string;
}

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
	activeFile: File | null;
	progress: number;
	queue: {
		file: File;
		uploadTo: string;
		table_id?: string;
	}[];
}

// Action Table
export interface ActionTable {
	id: string;
	cols: ActionTableCol[];
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

export interface ActionTableCol {
	id: string;
	dtype: (typeof actionTableDTypes)[number];
	vlen: number;
	index: boolean;
	gen_config: (Partial<ChatRequest> & { embedding_model?: string; source_column?: string }) | null;
}

export type ActionTableRow = {
	ID: string;
	'Updated at': string;
} & {
	[key: string]: {
		value: any;
	};
};

export type GenTableStreamEvent = {
	id: string;
	object: 'gen_table.completion.chunk';
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
	name: string;
	tier: string;
	active: boolean;
	quotas: {
		credit: number;
		credit_grant: number;
		[key: string]: number;
	};
	stripe_id: string;
	openmeter_id: string;
	external_keys?: {
		openai_api_key: string;
		anthropic_api_key: string;
		cohere_api_key: string;
		together_api_key: string;
		[key: string]: string;
	};
	created_at: string;
	updated_at: string;
	users?: {
		organization_id: string;
		role: (typeof userRoles)[number];
		user_id: string;
		name: string;
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
};

export type API_Key = {
	user_id: string;
	organization_id: string;
	write: boolean;
	id: string;
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
	organizations: Organization[];
	api_keys: API_Key[];
};

// Openmeter
export type TUsageData = {
	model: string;
	data: {
		date: string;
		amount: number;
	}[];
};

export const openmeterTokenUsageItemSchema = z
	.object({
		value: z.number(),
		subject: z.string(),
		windowStart: z.string(),
		windowEnd: z.string(),
		groupBy: z.object({ model: z.string() })
	})
	.passthrough();

export const openmeterTokenUsageSchema = z.array(openmeterTokenUsageItemSchema);
