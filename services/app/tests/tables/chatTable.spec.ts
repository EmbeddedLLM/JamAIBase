import 'dotenv/config';
import { expect, test as base } from '@playwright/test';
import { faker } from '@faker-js/faker';
import { ProjectPage } from '../pages/project.page';
import { TableListPage } from '../pages/tableList.page';
import { TablePage } from '../pages/table.page';

const { JAMAI_URL, JAMAI_SERVICE_KEY } = process.env;
const headers = {
	Authorization: `Bearer ${JAMAI_SERVICE_KEY}`
};

const test = base.extend<{ tablePage: TablePage; agentTablePage: TablePage }>({
	tablePage: async ({ page }, use) => {
		const projectPage = new ProjectPage(page);
		await projectPage.goto();
		await projectPage.switchOrganization('test-org');
		await projectPage.gotoProject('test-project');
		const tableListPage = new TableListPage(page);
		await tableListPage.gotoMenu('Chat Table');
		await tableListPage.gotoTable('test-chat-conv');
		await use(new TablePage(page));
	},

	agentTablePage: async ({ page }, use) => {
		const projectPage = new ProjectPage(page);
		await projectPage.goto();
		await projectPage.switchOrganization('test-org');
		await projectPage.gotoProject('test-project');
		const tableListPage = new TableListPage(page);
		await tableListPage.gotoMenu('Chat Table');
		await tableListPage.gotoTable('test-chat-agent');
		await use(new TablePage(page));
	}
});

const inputText = `Tell me one compound that can be created from ${faker.science.chemicalElement().name} and ${faker.science.chemicalElement().name}.`;

test.describe.configure({ mode: 'parallel', retries: 2 });

test.describe('Chat Table Page Basic', () => {
	let projectId: string;
	test.describe.configure({ mode: 'serial' });

	test.beforeEach(async ({ tablePage }) => {
		projectId = /\/project\/([^\s/]+)\/[^\s/]+/.exec(tablePage.page.url())?.[1] ?? '';
	});

	//TODO: Test streaming
	test('can add new row inline', async ({ tablePage }) => {
		test.setTimeout(60_000);
		await tablePage.addRow({
			type: 'str',
			value: inputText
		});
	});

	test('can regenerate row', async ({ tablePage }) => {
		test.setTimeout(60_000);
		const row = tablePage.rows.first();
		const originalRowText = await row.locator('div[role="gridcell"]').last().textContent();
		await row.locator('div[role="gridcell"]').locator('button[role="checkbox"]').click();
		await tablePage.generate();

		await expect(row).toHaveAttribute('data-streaming', 'true');
		await expect(row).not.toHaveAttribute('data-streaming');
		await expect(row).not.toHaveText(originalRowText ?? '');
	});

	test.describe('Chat mode', () => {
		let rowCount: number;
		let colCount: number;
		test.beforeEach(async ({ page, tablePage }) => {
			rowCount = await tablePage.rows.count();
			colCount = (await tablePage.tableHeader.getByRole('columnheader').count()) - 3;
			await tablePage.titleRow.getByRole('checkbox', { name: 'Switch to chat mode' }).click();
			await expect(tablePage.tableArea).not.toBeVisible();
			await expect(page.getByTestId('chat-window')).toBeVisible();
			await expect(page.getByTestId('loading-spinner')).toHaveCount(0);
		});

		test('verify chat messages', async ({ page }) => {
			const chatMessages = page.getByTestId('chat-message');
			expect(await chatMessages.count()).toEqual(rowCount * colCount);

			await expect(chatMessages.nth(-2)).toContainText(inputText);
		});

		test('can send chat message', async ({ page }) => {
			await page
				.getByPlaceholder('Enter message')
				.fill("Describe the compound's physical characteristics.");
			await page.getByRole('button', { name: 'Send message' }).click();

			const chatMessages = page.getByTestId('chat-message');
			expect(await chatMessages.count()).toBe(rowCount * colCount + 2);
			await expect(chatMessages.last()).toHaveAttribute('data-streaming', 'true');
			await expect(chatMessages.last()).not.toHaveAttribute('data-streaming');
		});

		test('can regenerate message', async ({ page }) => {
			const chatMessages = page.getByTestId('chat-message');
			// const originalText = await chatMessages.last().innerText();
			await page.getByTestId('stop-regen-btn').click();

			await expect(chatMessages.last()).toHaveAttribute('data-streaming', 'true');
			await expect(chatMessages.last()).not.toHaveAttribute('data-streaming');
			// await expect(chatMessages.last()).not.toHaveText(originalText ?? '');
		});
	});

	test('can update column config, and persist', async ({ tablePage }) => {
		await tablePage.updateColumnPrompt(-1, 'No input');
	});

	test('can edit row cell', async ({ tablePage }) => {
		await tablePage.editCellValue(0, 3, 'Placeholder test value');
	});

	test('can export rows', async ({ tablePage }) => {
		await tablePage.actionsBtn.click();

		const downloadPromise = tablePage.page.waitForEvent('download');
		await tablePage.page
			.getByTestId('table-actions-dropdown')
			.locator('div[role="menuitem"]', {
				has: tablePage.page.getByText(`Export rows (.csv)`, { exact: true })
			})
			.click();
		const download = await downloadPromise;
		await download.saveAs('./tests/fixtures/' + download.suggestedFilename());
	});

	test('can import rows', async ({ tablePage }) => {
		const previousRowCount = await tablePage.rows.count();
		await tablePage.actionsBtn.click();

		const [fileChooser] = await Promise.all([
			tablePage.page.waitForEvent('filechooser'),
			tablePage.page
				.getByTestId('table-actions-dropdown')
				.locator('div[role="menuitem"]', {
					has: tablePage.page.getByText(`Import rows`, { exact: true })
				})
				.click()
		]);
		await fileChooser.setFiles('./tests/fixtures/sample-csv.csv');

		const colMatchDialog = tablePage.page.getByTestId('column-match-dialog');
		await expect(colMatchDialog).toBeVisible();
		await colMatchDialog
			.locator('button', { has: tablePage.page.getByText('Import', { exact: true }) })
			.click();
		await expect(colMatchDialog).not.toBeVisible();

		await tablePage.page.waitForTimeout(2500);
		expect(await tablePage.rows.count()).toEqual(previousRowCount + 1);
	});

	test('can delete previously created row', async ({ tablePage }) => {
		const previousRowCount = await tablePage.rows.count();
		await tablePage.rows
			.first()
			.locator('div[role="gridcell"]')
			.locator('button[role="checkbox"]')
			.click();
		await tablePage.deleteRows();

		expect(await tablePage.rows.count()).toBe(previousRowCount - 1);
	});

	test.afterAll(async () => {
		const tableType = 'chat';
		const tableName = 'test-chat-conv';
		const tableParent = 'temp-chat-agent';

		const deleteTableRes = await fetch(`${JAMAI_URL}/api/v1/gen_tables/${tableType}/${tableName}`, {
			method: 'DELETE',
			headers: {
				...headers,
				'x-project-id': projectId
			}
		});

		if (!deleteTableRes.ok && deleteTableRes.status !== 404) {
			throw await deleteTableRes.json();
		}

		//* Temp chat agent in case original has been changed
		const createTempAgentRes = await fetch(`${JAMAI_URL}/api/v1/gen_tables/${tableType}`, {
			method: 'POST',
			headers: {
				...headers,
				'Content-Type': 'application/json',
				'x-project-id': projectId
			},
			body: JSON.stringify({
				id: tableParent,
				version: '0.3.0',
				cols: [
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
				]
			})
		});

		if (!createTempAgentRes.ok) {
			throw await createTempAgentRes.json();
		}

		//* Duplicate agent to chat conv
		const dupeTableRes = await fetch(
			`${JAMAI_URL}/api/v1/gen_tables/chat/duplicate/${tableParent}?${new URLSearchParams({
				create_as_child: 'true',
				table_id_dst: tableName
			})}`,
			{
				method: 'POST',
				headers: {
					...headers,
					'x-project-id': projectId
				}
			}
		);

		if (!dupeTableRes.ok) {
			throw await dupeTableRes.json();
		}

		const deleteTempAgentRes = await fetch(
			`${JAMAI_URL}/api/v1/gen_tables/${tableType}/${tableParent}`,
			{
				method: 'DELETE',
				headers: {
					...headers,
					'x-project-id': projectId
				}
			}
		);

		if (!deleteTempAgentRes.ok && deleteTempAgentRes.status !== 404) {
			throw await deleteTempAgentRes.json();
		}
	});
});

test.describe('Chat Table Page with File Col', () => {
	let projectId: string;
	test.describe.configure({ mode: 'serial' });

	test.beforeEach(async ({ tablePage }) => {
		projectId = /\/project\/([^\s/]+)\/[^\s/]+/.exec(tablePage.page.url())?.[1] ?? '';
	});

	test.describe('Column create, rename, reorder, delete', () => {
		test('can add new input column', async ({ agentTablePage }) => {
			await agentTablePage.addColumn('input', 'file');
		});

		test('can add new output column', async ({ agentTablePage }) => {
			await agentTablePage.addColumn('output');
		});

		test.describe('File column tests', () => {
			test('add new row image', async ({ agentTablePage }) => {
				await agentTablePage.addRow({ type: 'file', value: './tests/fixtures/sample-img.jpg' });
			});

			test('delete edited file', async ({ agentTablePage }) => {
				await agentTablePage.deleteFile(agentTablePage.rows.first().getByRole('gridcell').nth(5));
			});

			test('edit cell and upload file', async ({ agentTablePage }) => {
				await agentTablePage.editFileColCell(
					agentTablePage.rows.first().getByRole('gridcell').nth(5),
					'./tests/fixtures/sample-img.jpg'
				);
			});

			//TODO: Preview and download file

			test('preview and delete file', async ({ agentTablePage }) => {
				await agentTablePage.deleteFileInPreview(
					agentTablePage.rows.first().getByRole('gridcell').nth(5)
				);
			});
		});

		test('can rename column (dblclick)', async ({ page, agentTablePage }) => {
			await agentTablePage.renameColumnInline(
				agentTablePage.tableHeader
					.getByRole('columnheader')
					.filter({ has: page.getByText('transient-input-column', { exact: true }) }),
				'transient-input-col'
			);
		});

		test('can rename column (menu)', async ({ page, agentTablePage }) => {
			await agentTablePage.renameColumnMenu(
				agentTablePage.tableHeader
					.getByRole('columnheader')
					.filter({ has: page.getByText('transient-output-column', { exact: true }) }),
				'transient-output-col'
			);
		});

		test('can reorder columns', async ({ agentTablePage }) => {
			await agentTablePage.reorderColumns('transient-input-col', 'transient-output-col');
		});

		test('can delete columns', async ({ agentTablePage }) => {
			//* Delete input column
			await agentTablePage.deleteColumn('transient-input-col');
			//* Delete output column
			await agentTablePage.deleteColumn('transient-output-col');
		});
	});

	test.afterAll(async () => {
		const tableType = 'chat';
		const tableName = 'test-chat-agent';

		const deleteTableRes = await fetch(`${JAMAI_URL}/api/v1/gen_tables/${tableType}/${tableName}`, {
			method: 'DELETE',
			headers: {
				...headers,
				'x-project-id': projectId
			}
		});

		if (!deleteTableRes.ok && deleteTableRes.status !== 404) {
			throw await deleteTableRes.json();
		}

		const createTableRes = await fetch(`${JAMAI_URL}/api/v1/gen_tables/${tableType}`, {
			method: 'POST',
			headers: {
				...headers,
				'Content-Type': 'application/json',
				'x-project-id': projectId
			},
			body: JSON.stringify({
				id: tableName,
				version: '0.3.0',
				cols: [
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
				]
			})
		});

		if (!createTableRes.ok) {
			throw await createTableRes.json();
		}
	});
});
