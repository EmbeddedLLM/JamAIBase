import { test as base, expect } from '@playwright/test';
import 'dotenv/config';
import { ProjectPage } from '../pages/project.page';
import { TablePage } from '../pages/table.page';
import { TableListPage } from '../pages/tableList.page';

const { OWL_URL, OWL_SERVICE_KEY } = process.env;
const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

const test = base.extend<{ tablePage: TablePage; fileTablePage: TablePage }>({
	tablePage: async ({ page }, use) => {
		const projectPage = new ProjectPage(page);
		await projectPage.goto();
		await projectPage.switchOrganization('test-org');
		await projectPage.gotoProject('test-project');
		const tableListPage = new TableListPage(page);
		await tableListPage.gotoMenu('Knowledge Table');
		await tableListPage.gotoTable('test-knowledge-table');
		await use(new TablePage(page));
	}
});

test.describe.configure({ mode: 'parallel', retries: 2 });

test.describe('Knowledge Table Page', () => {
	let projectId: string;
	test.describe.configure({ mode: 'serial' });

	test.beforeEach(async ({ tablePage }) => {
		projectId = /\/project\/([^\s/]+)\/[^\s/]+/.exec(tablePage.page.url())?.[1] ?? '';
	});

	test.describe('Basic table operations', () => {
		test('can upload new file (empty)', async ({ page, tablePage }) => {
			const [fileChooser] = await Promise.all([
				page.waitForEvent('filechooser'),
				page.getByRole('button', { name: 'Browse document' }).click()
			]);
			await fileChooser.setFiles('./tests/fixtures/sample-doc.txt');

			const uploadTab = page.locator('#upload-tab-global');
			await expect(uploadTab).toBeVisible();
			expect(await uploadTab.getByRole('listitem').count()).toBe(1);
			await expect(page.getByTestId('complete-upload-file')).toBeVisible({ timeout: 10000 });
			expect(await tablePage.rows.count()).toBeGreaterThan(0);

			await uploadTab.getByLabel('Close and cancel ongoing uploads').click();
			await expect(uploadTab).not.toBeVisible();
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

		test('can edit row cell', async ({ tablePage }) => {
			await tablePage.editCellValue(0, 3, 'Placeholder test value');
		});

		test('can delete previously created row', async ({ tablePage }) => {
			const previousRowCount = await tablePage.rows.count();
			await tablePage.rows
				.first()
				.locator('div[role="gridcell"]')
				.locator('button[role="checkbox"]')
				.click();
			await tablePage.deleteRows();

			//? Why
			await tablePage.page.reload();
			await tablePage.page.waitForURL(/.*\/project\/[^/]+\/knowledge-table\/test-knowledge-table/);

			expect(await tablePage.rows.count()).toBe(previousRowCount - 1);
		});

		test('can upload new file (title row)', async ({ page, tablePage }) => {
			const [fileChooser] = await Promise.all([
				page.waitForEvent('filechooser'),
				page.getByRole('button', { name: 'Upload' }).click()
			]);
			await fileChooser.setFiles('./tests/fixtures/sample-doc.txt');

			const uploadTab = page.locator('#upload-tab-global');
			await expect(uploadTab).toBeVisible();
			expect(await uploadTab.getByRole('listitem').count()).toBe(1);
			await expect(page.getByTestId('complete-upload-file')).toBeVisible({ timeout: 10000 });
			expect(await tablePage.rows.count()).toBeGreaterThan(0);
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
	});

	test.describe('Column create, reconfig, rename, reorder, delete', () => {
		test('validate embed column config', async ({ tablePage }) => {
			const embedCols = tablePage.tableHeader
				.getByRole('columnheader')
				.filter({ hasText: /float32/ });
			for (const embedCol of await embedCols.elementHandles()) {
				await embedCol.click();
				const columnSettings = tablePage.page.getByTestId('column-settings-area');
				await expect(columnSettings).toBeVisible();
				await expect(columnSettings.locator('span', { hasText: 'Embedding Model' })).toBeVisible();
				await expect(columnSettings.locator('span', { hasText: 'Source Column' })).toBeVisible();
				await columnSettings.getByRole('button', { name: 'Cancel' }).click();
			}
		});

		test('can add new input column', async ({ tablePage }) => {
			await tablePage.addColumn('input');
		});

		test('can add new output column', async ({ tablePage }) => {
			await tablePage.addColumn('output');
		});

		test('can update column config, and persist', async ({ tablePage }) => {
			await tablePage.updateColumnPrompt(-1, 'Input');
		});

		test('can rename column (dblclick)', async ({ page, tablePage }) => {
			await tablePage.renameColumnInline(
				tablePage.tableHeader
					.getByRole('columnheader')
					.filter({ has: page.getByText('transient-input-column', { exact: true }) }),
				'transient-input-col'
			);
		});

		test('can rename column (menu)', async ({ page, tablePage }) => {
			await tablePage.renameColumnMenu(
				tablePage.tableHeader
					.getByRole('columnheader')
					.filter({ has: page.getByText('transient-output-column', { exact: true }) }),
				'transient-output-col'
			);
		});

		test('can reorder columns', async ({ tablePage }) => {
			await tablePage.reorderColumns('transient-input-col', 'transient-output-col');
		});

		test('can delete columns', async ({ tablePage }) => {
			//* Delete input column
			await tablePage.deleteColumn('transient-input-col');
			//* Delete output column
			await tablePage.deleteColumn('transient-output-col');
		});
	});

	test.afterAll(async () => {
		const tableType = 'knowledge';
		const tableName = 'test-knowledge-table';

		const deleteTableRes = await fetch(`${OWL_URL}/api/v2/gen_tables/${tableType}/${tableName}`, {
			method: 'DELETE',
			headers: {
				...headers,
				'x-project-id': projectId
			}
		});

		if (!deleteTableRes.ok && deleteTableRes.status !== 404) {
			throw await deleteTableRes.json();
		}

		//* Get embedding model
		const modelsRes = await fetch(
			`${OWL_URL}/api/v2/models?${new URLSearchParams({
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

		if (!modelsRes.ok) {
			throw modelsBody;
		}

		const createTableRes = await fetch(`${OWL_URL}/api/v2/gen_tables/${tableType}`, {
			method: 'POST',
			headers: {
				...headers,
				'Content-Type': 'application/json',
				'x-project-id': projectId
			},
			body: JSON.stringify({
				id: tableName,
				version: '0.5.0',
				cols: [],
				embedding_model: modelsBody.data[0].id
			})
		});

		if (!createTableRes.ok) {
			throw await createTableRes.json();
		}
	});
});
