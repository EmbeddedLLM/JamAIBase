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

const test = base.extend<{ tablePage: TablePage; fileTablePage: TablePage }>({
	tablePage: async ({ page }, use) => {
		const projectPage = new ProjectPage(page);
		await projectPage.goto();
		await projectPage.switchOrganization('test-org');
		await projectPage.gotoProject('test-project');
		const tableListPage = new TableListPage(page);
		await tableListPage.gotoTable('test-action-table');
		await use(new TablePage(page));
	},

	fileTablePage: async ({ page }, use) => {
		const projectPage = new ProjectPage(page);
		await projectPage.goto();
		await projectPage.switchOrganization('test-org');
		await projectPage.gotoProject('test-project');
		const tableListPage = new TableListPage(page);
		await tableListPage.gotoTable('test-action-table-file');
		await use(new TablePage(page));
	}
});

test.describe.configure({ mode: 'parallel', retries: 2 });

test.describe('Action Table Page Basic', () => {
	let projectId: string;
	test.describe.configure({ mode: 'serial' });

	test.beforeEach(async ({ tablePage }) => {
		projectId = /\/project\/([^\s/]+)\/[^\s/]+/.exec(tablePage.page.url())?.[1] ?? '';
	});

	//TODO: Test streaming
	test('can add new row inline', async ({ tablePage }) => {
		await tablePage.addRow({
			type: 'str',
			value: `What is there to see in ${faker.location.country()}?`
		});
	});

	test('can regenerate row', async ({ tablePage }) => {
		const row = tablePage.rows.first();
		const originalRowText = await row.locator('div[role="gridcell"]').last().textContent();
		await row.locator('div[role="gridcell"]').locator('button[role="checkbox"]').click();
		await tablePage.generate();

		await expect(row).toHaveAttribute('data-streaming', 'true');
		await expect(row).not.toHaveAttribute('data-streaming');
		await expect(row).not.toHaveText(originalRowText ?? '');
	});

	test('can update column config, and persist', async ({ tablePage }) => {
		await tablePage.updateColumnPrompt(-1, '${Input}');
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
		const tableType = 'action';
		const tableName = 'test-action-table';

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
				]
			})
		});

		if (!createTableRes.ok) {
			throw await createTableRes.json();
		}
	});
});

test.describe('Action Table Page with File Col', () => {
	let projectId: string;
	test.describe.configure({ mode: 'serial' });

	test.beforeEach(async ({ tablePage }) => {
		projectId = /\/project\/([^\s/]+)\/[^\s/]+/.exec(tablePage.page.url())?.[1] ?? '';
	});

	test.describe('File column tests', () => {
		test('add new row image', async ({ fileTablePage }) => {
			await fileTablePage.addRow({ type: 'file', value: './tests/fixtures/sample-img.jpg' });
		});

		test('delete edited file', async ({ fileTablePage }) => {
			await fileTablePage.deleteFile(fileTablePage.rows.first().getByRole('gridcell').nth(3));
		});

		test('edit cell and upload file', async ({ fileTablePage }) => {
			await fileTablePage.editFileColCell(
				fileTablePage.rows.first().getByRole('gridcell').nth(3),
				'./tests/fixtures/sample-img.jpg'
			);
		});

		//TODO: Preview and download file

		test('preview and delete file', async ({ fileTablePage }) => {
			await fileTablePage.deleteFileInPreview(
				fileTablePage.rows.first().getByRole('gridcell').nth(3)
			);
		});
	});

	test.describe('Column create, rename, reorder, delete', () => {
		test('can add new input column', async ({ fileTablePage }) => {
			await fileTablePage.addColumn('input');
		});

		test('can add new output column', async ({ fileTablePage }) => {
			await fileTablePage.addColumn('output');
		});

		test('can rename column (dblclick)', async ({ page, fileTablePage }) => {
			await fileTablePage.renameColumnInline(
				fileTablePage.tableHeader
					.getByRole('columnheader')
					.filter({ has: page.getByText('transient-input-column', { exact: true }) }),
				'transient-input-col'
			);
		});

		test('can rename column (menu)', async ({ page, fileTablePage }) => {
			await fileTablePage.renameColumnMenu(
				fileTablePage.tableHeader
					.getByRole('columnheader')
					.filter({ has: page.getByText('transient-output-column', { exact: true }) }),
				'transient-output-col'
			);
		});

		test('can reorder columns', async ({ fileTablePage }) => {
			await fileTablePage.reorderColumns('transient-input-col', 'transient-output-col');
		});

		test('can delete columns', async ({ fileTablePage }) => {
			//* Delete input column
			await fileTablePage.deleteColumn('transient-input-col');
			//* Delete output column
			await fileTablePage.deleteColumn('transient-output-col');
		});
	});

	test.afterAll(async () => {
		const tableType = 'action';
		const tableName = 'test-action-table-file';

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
				]
			})
		});

		if (!createTableRes.ok) {
			throw await createTableRes.json();
		}
	});
});
