import type { GenTableCol, ModelConfig } from '$lib/types';
import { test as setup } from '@playwright/test';
import 'dotenv/config';
import { readFileSync } from 'fs';
import Stripe from 'stripe';

const { OWL_URL, OWL_SERVICE_KEY, OWL_STRIPE_API_KEY } = process.env;
const stripe = new Stripe(OWL_STRIPE_API_KEY!);

const testDataFile = 'tests/fixtures/sample-data.json';
const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

//TODO: Clean slate tests with teardown
setup.skip('create users', async () => {
	const users = JSON.parse(readFileSync(testDataFile, 'utf-8'));
	// const getUserRes = await fetch(
	// 	`${OWL_URL}/api/v2/users?${new URLSearchParams([['user_id', '0']])}`,
	// 	{
	// 		headers
	// 	}
	// );
	// const getUserBody = await getUserRes.json();

	// if (!getUserRes.ok) {
	// 	if (getUserRes.status !== 404) throw { code: 'get_user', ...getUserBody };

	// }
	const createAdminRes = await fetch(`${OWL_URL}/api/v2/auth/register/password`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(users.admin)
	});
	const createAdminBody = await createAdminRes.json();

	if (!createAdminRes.ok) throw { code: 'create_admin_user', ...createAdminBody };

	const createTestUserRes = await fetch(`${OWL_URL}/api/v2/auth/register/password`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(users.test)
	});
	const createTestUserBody = await createTestUserRes.json();

	if (!createTestUserRes.ok) throw { code: 'create_test_user', ...createTestUserBody };

	process.env.TEST_ADMIN_ID = createAdminBody.id;
	process.env.TEST_USER_ID = createTestUserBody.id;

	// Verify accounts
	const verifyAdminRes = await fetch(`${OWL_URL}/api/v2/users`, {
		method: 'POST',
		headers: {
			...headers,
			'x-user-id': process.env.TEST_ADMIN_ID!,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			id: process.env.TEST_ADMIN_ID!,
			email_verified: true
		})
	});
	if (!verifyAdminRes.ok) throw { code: 'verify_admin_user', ...(await verifyAdminRes.json()) };

	const verifyTestUserRes = await fetch(`${OWL_URL}/api/v2/users`, {
		method: 'POST',
		headers: {
			...headers,
			'x-user-id': process.env.TEST_ADMIN_ID!,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			id: process.env.TEST_USER_ID!,
			email_verified: true
		})
	});
	if (!verifyTestUserRes.ok)
		throw { code: 'verify_test_user', ...(await verifyTestUserRes.json()) };
});

setup.skip('add model config and deployment', async () => {
	// const modelPresetsRes = await fetch(
	// 	'https://raw.githubusercontent.com/EmbeddedLLM/JamAIBase/refs/heads/main/services/api/src/owl/configs/preset_models.json',
	// 	{
	// 		method: 'GET'
	// 	}
	// );

	// if (!modelPresetsRes.ok) {
	// 	const error = await modelPresetsRes.text();
	// 	throw { code: '', status: modelPresetsRes.status, message: error };
	// }

	// const modelPresetsBody = (await modelPresetsRes.json()) as ModelConfig[];

	const models = JSON.parse(readFileSync(testDataFile, 'utf-8'));

	const createModelConfigs = await Promise.allSettled([
		createModelConfig(models.chat_table),
		createModelConfig(models.embedding_model)
	]);

	if (createModelConfigs.some((val) => val.status === 'rejected')) {
		const rejected = await Promise.all(
			createModelConfigs.flatMap((val, index) =>
				val.status === 'rejected' ? { index, ...val.reason } : []
			)
		);
		throw { code: 'create_model_configs', rejected };
	}

	const createModelDeployments = await Promise.allSettled([
		createModelDeployment(models.chat_model_deployment),
		createModelDeployment(models.embedding_model_deployment)
	]);

	if (createModelDeployments.some((val) => val.status === 'rejected')) {
		const rejected = await Promise.all(
			createModelDeployments.flatMap((val, index) =>
				val.status === 'rejected' ? { index, ...val.reason } : []
			)
		);
		throw { code: 'create_model_deployments', rejected };
	}

	async function createModelConfig(body: any) {
		const createModelConfigRes = await fetch(`${OWL_URL}/api/v2/models/configs`, {
			method: 'POST',
			headers: {
				...headers,
				'x-user-id': process.env.TEST_ADMIN_ID!,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify(body)
		});
		if (!createModelConfigRes.ok) throw await createModelConfigRes.json();
	}

	async function createModelDeployment(body: any) {
		const createModelDeploymentRes = await fetch(`${OWL_URL}/api/v2/models/deployment/cloud`, {
			method: 'POST',
			headers: {
				...headers,
				'x-user-id': process.env.TEST_ADMIN_ID!,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify(body)
		});
		if (!createModelDeploymentRes.ok) throw await createModelDeploymentRes.json();
	}
});

setup.skip('create price plans', async () => {
	const prices = JSON.parse(readFileSync(testDataFile, 'utf-8'));

	const createPlans = await Promise.allSettled([createPricePlan(prices.pro_plan)]);

	if (createPlans.some((val) => val.status === 'rejected')) {
		const rejected = await Promise.all(
			createPlans.flatMap((val, index) =>
				val.status === 'rejected' ? { index, ...val.reason } : []
			)
		);
		throw { code: 'create_price_plan', rejected };
	}

	process.env.TEST_PRO_PLAN_ID =
		createPlans[0].status === 'fulfilled' ? createPlans[0].value.id : null;

	async function createPricePlan(body: any) {
		const createPricePlanRes = await fetch(`${OWL_URL}/api/v2/prices/plans`, {
			method: 'POST',
			headers: {
				...headers,
				'x-user-id': process.env.TEST_ADMIN_ID!,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify(body)
		});
		const createPricePlanBody = await createPricePlanRes.json();

		if (!createPricePlanRes.ok) throw createPricePlanBody;
		return createPricePlanBody;
	}
});

setup.skip('create admin org', async () => {
	const createOrgRes = await fetch(`${OWL_URL}/api/v2/organizations`, {
		method: 'POST',
		headers: {
			...headers,
			'x-user-id': process.env.TEST_ADMIN_ID!,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			name: 'admin-org',
			currency: 'USD'
		})
	});
	const createOrgBody = await createOrgRes.json();

	if (!createOrgRes.ok) throw { code: 'create_org', ...createOrgBody };

	process.env.TEST_ADMIN_ORGID = createOrgBody.id;
});

setup('create org and tables', async () => {
	const createOrgRes = await fetch(`${OWL_URL}/api/v2/organizations`, {
		method: 'POST',
		headers: {
			...headers,
			'x-user-id': process.env.TEST_USER_ID!,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			name: 'test-org',
			currency: 'USD'
		})
	});
	const createOrgBody = await createOrgRes.json();

	if (!createOrgRes.ok) throw { code: 'create_org', ...createOrgBody };

	const organizationId = createOrgBody.id;

	//stripe add payment method and subscribe plan
	const paymentMethod = await stripe.paymentMethods.create({
		type: 'card',
		card: {
			token: 'tok_visa'
		}
	});
	await stripe.paymentMethods.attach(paymentMethod.id, {
		customer: createOrgBody.stripe_id
	});
	await stripe.customers.update(createOrgBody.stripe_id, {
		invoice_settings: {
			default_payment_method: paymentMethod.id
		}
	});

	const changeOrgPlanRes = await fetch(
		`${OWL_URL}/api/v2/organizations/plan?${new URLSearchParams([
			['organization_id', organizationId],
			['price_plan_id', process.env.TEST_TEAM_PLAN_ID!]
		])}`,
		{
			method: 'PATCH',
			headers: {
				...headers,
				'x-user-id': process.env.TEST_USER_ID!
			}
		}
	);
	const changeOrgPlanBody = await changeOrgPlanRes.json();

	if (!changeOrgPlanRes.ok) throw { code: 'change_org_plan', ...changeOrgPlanBody };

	// await stripe.paymentIntents.confirm(changeOrgPlanBody.payment_intent_id);

	// Add credits
	const addCreditsRes = await fetch(`${OWL_URL}/api/v2/organizations`, {
		method: 'PATCH',
		headers: {
			...headers,
			'x-user-id': process.env.TEST_USER_ID!,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			id: organizationId,
			credit: 10000
		})
	});
	if (!addCreditsRes.ok) throw { code: 'add_org_credits', ...(await addCreditsRes.json()) };

	const createProjectRes = await fetch(`${OWL_URL}/api/v2/projects`, {
		method: 'POST',
		headers: {
			...headers,
			'x-user-id': process.env.TEST_USER_ID!,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			name: 'test-project',
			organization_id: organizationId
		})
	});
	const createProjectBody = await createProjectRes.json();
	if (!createProjectRes.ok) throw { code: 'create_project', ...createProjectBody };

	const projectId = createProjectBody.id;

	const models = JSON.parse(readFileSync(testDataFile, 'utf-8'));

	const createTestTables = await Promise.allSettled([
		createTable('action', 'test-action-table', [
			{
				id: 'Input',
				dtype: 'str',
				vlen: 0,
				index: true,
				gen_config: null
			},
			{
				id: 'Output',
				dtype: 'str',
				vlen: 0,
				index: true,
				gen_config: {
					object: 'gen_config.llm',
					model: models.chat_model.id,
					multi_turn: false
				}
			}
		]),
		createTable('action', 'test-action-table-file', [
			{
				id: 'Input',
				dtype: 'image',
				vlen: 0,
				index: true,
				gen_config: null
			},
			{
				id: 'Output',
				dtype: 'str',
				vlen: 0,
				index: true,
				gen_config: {
					object: 'gen_config.llm',
					model: models.chat_model.id,
					multi_turn: false
				}
			}
		]),
		createTable('action', 'test-action-table-cols', []),
		createTable('knowledge', 'test-knowledge-table', []),
		createTable('chat', 'test-chat-agent', [
			{
				id: 'User',
				dtype: 'str',
				vlen: 0,
				index: true,
				gen_config: null
			},
			{
				id: 'AI',
				dtype: 'str',
				vlen: 0,
				index: true,
				gen_config: {
					object: 'gen_config.llm',
					model: models.chat_model.id,
					multi_turn: true
				}
			}
		])
	]);

	if (createTestTables.some((val) => val.status === 'rejected')) {
		const rejected = await Promise.all(
			createTestTables.flatMap((val, index) =>
				val.status === 'rejected' ? { index, ...val.reason } : []
			)
		);
		throw { code: 'create_test_tables', rejected };
	}

	const createConvs = await Promise.allSettled([
		createConv('test-chat-agent', 'test-chat-conv')
		// createConv('test-chat-agent', 'test-chat-conv-file')
	]);

	if (createConvs.some((val) => val.status === 'rejected')) {
		const rejected = await Promise.all(
			createConvs.flatMap((val, index) =>
				val.status === 'rejected' ? { index, ...(val.reason ? val.reason : { reason: val }) } : []
			)
		);
		throw { code: 'create_test_convs', rejected };
	}

	async function createTable(
		tableType: 'action' | 'knowledge' | 'chat',
		tableName: string,
		cols: GenTableCol[]
	) {
		await new Promise((r) => setTimeout(r, Math.floor(Math.random() * 3000)));

		let embeddingModel;
		if (tableType === 'knowledge') {
			const modelsRes = await fetch(
				`${OWL_URL}/api/v2/organizations/models/catalogue?${new URLSearchParams([['organization_id', organizationId]])}`,
				{
					headers: {
						...headers,
						'x-user-id': process.env.TEST_USER_ID!
					}
				}
			);
			const modelsBody = await modelsRes.json();

			if (!modelsRes.ok) throw modelsBody;

			embeddingModel = (modelsBody.items as ModelConfig[]).find((m) =>
				m.capabilities.includes('embed')
			)?.id;
		}

		const response = await fetch(`${OWL_URL}/api/v2/gen_tables/${tableType}`, {
			method: 'POST',
			headers: {
				...headers,
				'Content-Type': 'application/json',
				'x-user-id': process.env.TEST_USER_ID!,
				'x-project-id': projectId
			},
			body: JSON.stringify({
				id: tableName,
				version: '0.5.0',
				cols,
				embedding_model: tableType === 'knowledge' ? embeddingModel : undefined
			})
		});
		const responseBody = await response.json();

		if (response.ok) {
			return responseBody;
		} else {
			throw responseBody;
		}
	}

	async function createConv(parent: string, name: string) {
		const response = await fetch(
			`${OWL_URL}/api/v2/gen_tables/chat/duplicate?${new URLSearchParams([
				['table_id_src', parent],
				['table_id_dst', name],
				['create_as_child', 'true']
			])}`,
			{
				method: 'POST',
				headers: {
					...headers,
					'x-user-id': process.env.TEST_USER_ID!,
					'x-project-id': projectId
				}
			}
		);
		const responseBody = await response.json();

		if (response.ok) {
			return responseBody;
		} else {
			throw responseBody;
		}
	}
});
