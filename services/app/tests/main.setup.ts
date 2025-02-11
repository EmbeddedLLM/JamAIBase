import 'dotenv/config';
import { test as setup } from '@playwright/test';
import type { AvailableModel, GenTableCol } from '$lib/types';

const { JAMAI_URL, JAMAI_SERVICE_KEY, TEST_ACC_USERID } = process.env;

setup('create org and tables', async () => {
	const headers = {
		Authorization: `Bearer ${JAMAI_SERVICE_KEY}`
	};

	const createOrgRes = await fetch(`${JAMAI_URL}/api/admin/backend/v1/organizations`, {
		method: 'POST',
		headers: {
			...headers,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			creator_user_id: TEST_ACC_USERID,
			name: 'test-org',
			tier: 'team'
		})
	});
	const createOrgBody = await createOrgRes.json();
	console.log(createOrgBody);
	if (!createOrgRes.ok) throw { code: 'create_org', ...createOrgBody };

	const organizationId = createOrgBody.id;

	const createProjectRes = await fetch(`${JAMAI_URL}/api/admin/org/v1/projects`, {
		method: 'POST',
		headers: {
			...headers,
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
					model: 'anthropic/claude-3-haiku-20240307',
					multi_turn: false
				}
			}
		]),
		createTable('action', 'test-action-table-file', [
			{
				id: 'Input',
				dtype: 'file',
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
					model: 'openai/gpt-4o',
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
					model: 'anthropic/claude-3-haiku-20240307',
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
				val.status === 'rejected' ? { index, ...val.reason } : []
			)
		);
		throw { code: 'create_test_convs', rejected };
	}

	async function createTable(
		tableType: 'action' | 'knowledge' | 'chat',
		tableName: string,
		cols: GenTableCol[]
	) {
		let embeddingModel;
		if (tableType === 'knowledge') {
			const modelsRes = await fetch(
				`${JAMAI_URL}/api/v1/models?${new URLSearchParams({
					capabilities: 'embed'
				})}`,
				{
					headers: {
						...headers,
						'x-project-id': projectId
					}
				}
			);
			const modelsBody = await modelsRes.json();

			if (!modelsRes.ok) throw { code: 'list_models', ...modelsBody };

			embeddingModel = (modelsBody.data as AvailableModel[])[0].id;
		}

		const response = await fetch(`${JAMAI_URL}/api/v1/gen_tables/${tableType}`, {
			method: 'POST',
			headers: {
				...headers,
				'Content-Type': 'application/json',
				'x-project-id': projectId
			},
			body: JSON.stringify({
				id: tableName,
				version: '0.3.0',
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
			`${JAMAI_URL}/api/v1/gen_tables/chat/duplicate/${parent}?${new URLSearchParams({
				create_as_child: 'true',
				table_id_dst: name
			})}`,
			{
				method: 'POST',
				headers: {
					...headers,
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
